"""Caller-supplied course content and outline (request `source_material` / `outline`).

Two jobs:

* ``build_source_context`` turns the raw material into the block the blueprint
  LLM reads next to ``research_context``. Material longer than
  ``source_context_max_chars`` is condensed first (map-reduce: chunks on
  paragraph boundaries, one digest call per chunk, concatenated in order) so a
  small-context model still sees the whole course rather than its first pages.
* ``assign_section_ids`` makes the scene -> outline-section mapping reliable
  whatever the model returned: valid ids are kept, the order is forced to
  follow the outline, and when the model ignored the outline the scenes are
  spread over the sections by planned duration. ``timeline.json`` relies on it.
"""
from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from video_api.config import Settings

logger = logging.getLogger(__name__)

SOURCE_RULES = (
    "source_material is the caller's own course content and the PRIMARY source of truth. "
    "Teach what it says, with its definitions, notation, examples and order; do not contradict it "
    "and do not add claims it does not support. Stay within the requested duration: select and "
    "simplify, never pad."
)

OUTLINE_RULES = (
    "outline is the imposed structure. Follow its sections in order; each section is taught by one "
    "or more consecutive scenes and every section gets at least one scene. Set `section_id` on every "
    "scene to the id of the section it teaches (copied exactly). Cover each section's key_points; "
    "when a section has target_seconds, the durations of its scenes should add up to about that. "
    "Scene titles may be more specific than section titles."
)


def parse_outline(raw: str | None) -> list[dict[str, Any]]:
    """Persisted outline column (JSON list) -> list of section dicts."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("source.outline.invalid_json")
        return []
    return [section for section in data if isinstance(section, dict) and section.get("id")]


def split_chunks(text: str, max_chars: int) -> list[str]:
    """Split on paragraph boundaries into chunks of at most *max_chars*
    (a single oversized paragraph is hard-split)."""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        while len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:max_chars])
            paragraph = paragraph[max_chars:]
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def condense(
    material: str,
    settings: Settings,
    llm: Any,
    outline: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (material fitting the context budget, digest report)."""
    budget = settings.source_context_max_chars
    report: dict[str, Any] = {"input_chars": len(material), "method": "verbatim", "chunks": 0}
    if len(material) <= budget:
        report["output_chars"] = len(material)
        return material, report

    chunks = split_chunks(material, settings.source_digest_chunk_chars)
    # Each digest is capped at its share (separators included) so the joined
    # result fits the budget and the last chunk is never cut off.
    per_chunk = max(1, (budget - 2 * (len(chunks) - 1)) // len(chunks))
    titles = [str(section.get("title") or "") for section in outline or []]
    failures: list[str] = []

    def digest(item: tuple[int, str]) -> str:
        index, chunk = item
        try:
            return llm.digest_source_chunk(
                chunk, per_chunk, part=index + 1, parts=len(chunks), outline_titles=titles
            )
        except Exception as exc:  # one bad chunk must not lose the others
            failures.append(f"part {index + 1}: {exc}")
            logger.warning("source.digest.chunk_failed part=%d error=%s", index + 1, exc)
            return chunk[:per_chunk]

    with ThreadPoolExecutor(max_workers=settings.llm_parallel) as pool:
        digests = list(pool.map(digest, enumerate(chunks)))
    condensed = "\n\n".join(
        part.strip()[:per_chunk] for part in digests if part.strip()
    )[:budget]
    report.update(
        method="digest",
        chunks=len(chunks),
        output_chars=len(condensed),
        truncated_chunks=len(failures),
    )
    if failures:
        report["errors"] = failures[:5]
    logger.info(
        "source.digest.done input_chars=%d chunks=%d output_chars=%d failed_chunks=%d",
        len(material),
        len(chunks),
        len(condensed),
        len(failures),
    )
    return condensed, report


def build_source_context(
    material: str | None,
    outline: list[dict[str, Any]],
    settings: Settings,
    llm: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (prompt context block, report). Both empty when the job has
    neither source material nor outline."""
    context: dict[str, Any] = {}
    report: dict[str, Any] = {}
    if material:
        condensed, digest_report = condense(material, settings, llm, outline)
        context["source_rules"] = SOURCE_RULES
        context["source_material"] = condensed
        report["source_material"] = digest_report
    if outline:
        context["outline_rules"] = OUTLINE_RULES
        context["outline"] = outline
        report["outline"] = {"sections": len(outline)}
    return context, report


def merge_contexts(research: dict[str, Any] | None, source: dict[str, Any]) -> dict[str, Any] | None:
    """One grounding block for the blueprint prompts (keys never overlap)."""
    if not research and not source:
        return None
    return {**(research or {}), **source}


def _proportional_ids(durations: list[float], outline: list[dict[str, Any]]) -> list[str]:
    """Spread scenes over sections by planned time: a scene belongs to the
    section containing its midpoint, sections weighted by target_seconds
    (equal weights when absent)."""
    weights = [float(section.get("target_seconds") or 0) for section in outline]
    if not all(weights):
        weights = [1.0] * len(outline)
    total_scene = sum(durations) or 1.0
    total_weight = sum(weights)
    bounds: list[float] = []
    acc = 0.0
    for weight in weights:
        acc += weight / total_weight
        bounds.append(acc)
    ids: list[str] = []
    elapsed = 0.0
    for duration in durations:
        midpoint = (elapsed + duration / 2) / total_scene
        elapsed += duration
        index = next((i for i, bound in enumerate(bounds) if midpoint <= bound), len(outline) - 1)
        ids.append(str(outline[index]["id"]))
    return ids


def assign_section_ids(blueprint: Any, outline: list[dict[str, Any]]) -> dict[str, Any]:
    """Set ``scene.section_id`` on every scene, in outline order. Returns a
    report: how the mapping was obtained and which sections got no scene."""
    scenes = list(blueprint.scenes)
    if not outline or not scenes:
        return {}
    order = {str(section["id"]): index for index, section in enumerate(outline)}
    proposed = [getattr(scene, "section_id", None) for scene in scenes]
    valid = [order.get(str(value)) if value is not None else None for value in proposed]
    valid_count = sum(1 for index in valid if index is not None)

    if valid_count == len(scenes) and valid == sorted(valid):  # type: ignore[type-var]
        method = "llm"
        ids = [str(value) for value in proposed]
    elif valid_count >= math.ceil(len(scenes) / 2):
        # Mostly right: fill the gaps from the previous scene and forbid going
        # back to an earlier section (the video plays the outline in order).
        method = "repaired"
        indices: list[int] = []
        for index in valid:
            previous = indices[-1] if indices else 0
            indices.append(previous if index is None else max(index, previous))
        ids = [str(outline[index]["id"]) for index in indices]
    else:
        method = "proportional"
        ids = _proportional_ids([float(scene.duration_seconds) for scene in scenes], outline)

    for scene, section_id in zip(scenes, ids, strict=True):
        scene.section_id = section_id
    covered = set(ids)
    uncovered = [str(section["id"]) for section in outline if str(section["id"]) not in covered]
    if method != "llm" or uncovered:
        logger.warning(
            "source.section_ids method=%s proposed_valid=%d/%d uncovered=%s",
            method,
            valid_count,
            len(scenes),
            ",".join(uncovered) or "-",
        )
    return {"method": method, "uncovered_sections": uncovered}


def copy_section_ids(blueprint: Any, master: dict[str, Any]) -> bool:
    """Secondary batch language: reuse the master's mapping scene by scene.
    Returns False when the master carries no complete mapping."""
    by_key = {
        scene.get("key"): scene.get("section_id")
        for scene in master.get("scenes") or []
        if isinstance(scene, dict)
    }
    ids = [by_key.get(scene.key) for scene in blueprint.scenes]
    if not ids or any(value is None for value in ids):
        return False
    for scene, section_id in zip(blueprint.scenes, ids, strict=True):
        scene.section_id = section_id
    return True
