"""Request source_material / outline, scene section_id and timeline.json."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.test_api import _StubTask
from tests.test_pipeline_flow import _pipeline
from video_api.capabilities import capabilities_payload
from video_api.config import Settings
from video_api.db import SessionLocal
from video_api.models import VideoJob
from video_api.pipeline.llm import LLMClient, fake_blueprint
from video_api.pipeline.source_material import (
    assign_section_ids,
    build_source_context,
    copy_section_ids,
    split_chunks,
)
from video_api.pipeline.timeline import build_timeline
from video_api.schemas import SOURCE_MATERIAL_MAX_CHARS, VideoCreateRequest

OUTLINE = [
    {"id": "s1", "title": "Pourquoi", "key_points": ["motivation"], "target_seconds": 60},
    {"id": "s2", "title": "Comment", "key_points": ["mécanisme"], "target_seconds": 120},
    {"id": "s3", "title": "Bilan", "key_points": [], "target_seconds": 60},
]


# --------------------------------------------------------------------- schema


def test_outline_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError, match="unique"):
        VideoCreateRequest(prompt="Explain the topic", outline=[OUTLINE[0], OUTLINE[0]])


def test_source_material_is_bounded() -> None:
    with pytest.raises(ValidationError):
        VideoCreateRequest(prompt="Explain the topic", source_material="x" * (SOURCE_MATERIAL_MAX_CHARS + 1))


def test_timed_outline_sets_missing_target_duration() -> None:
    request = VideoCreateRequest(prompt="Explain the topic", outline=OUTLINE)
    assert request.target_duration_seconds == 240
    explicit = VideoCreateRequest(prompt="Explain the topic", outline=OUTLINE, target_duration_seconds=300)
    assert explicit.target_duration_seconds == 300


def test_source_material_turns_research_off_unless_requested() -> None:
    request = VideoCreateRequest(
        prompt="Explain the topic", production_mode="editorial", source_material="Course text"
    )
    assert request.production_options().research.enabled is False
    forced = VideoCreateRequest(
        prompt="Explain the topic",
        production_mode="editorial",
        source_material="Course text",
        research={"enabled": True, "required": False},
    )
    assert forced.production_options().research.enabled is True
    plain = VideoCreateRequest(prompt="Explain the topic", production_mode="editorial")
    assert plain.production_options().research.enabled is True


def test_capabilities_advertise_source_features() -> None:
    payload = capabilities_payload(Settings())
    assert payload["limits"]["source_material_max_chars"] == SOURCE_MATERIAL_MAX_CHARS
    assert payload["limits"]["outline_max_sections"] == 12
    for feature in ("source_material", "outline", "timeline"):
        assert payload["features"][feature]["available"] is True


# ------------------------------------------------------------------------ API


def test_create_and_relaunch_keep_source_and_outline(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    import video_api.main as main_module

    monkeypatch.setattr(main_module, "run_video_job", _StubTask())
    with TestClient(main_module.app) as client:
        response = client.post(
            "/v1/videos",
            json={"prompt": "Explain the course", "source_material": "  Le cours.  ", "outline": OUTLINE},
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["job_id"]
        with SessionLocal() as session:
            job = session.get(VideoJob, job_id)
            job.status = "failed_render"
            session.commit()
        relaunched = client.post(f"/v1/videos/{job_id}/relaunch")
        assert relaunched.status_code == 202, relaunched.text
        new_id = relaunched.json()["job_id"]
    with SessionLocal() as session:
        for jid in (job_id, new_id):
            job = session.get(VideoJob, jid)
            assert job.source_material == "Le cours."
            assert [s["id"] for s in json.loads(job.outline)] == ["s1", "s2", "s3"]
            assert job.target_duration_seconds == 240


# ----------------------------------------------------------- source context


def test_split_chunks_respects_paragraphs_and_limit() -> None:
    text = "\n\n".join(["a" * 40, "b" * 40, "c" * 130, "d" * 10])
    chunks = split_chunks(text, 100)
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")
    assert chunks[0] == "a" * 40 + "\n\n" + "b" * 40


def test_short_material_is_passed_verbatim() -> None:
    settings = dataclasses.replace(Settings(), fake_llm=True)
    context, report = build_source_context("Petit cours.", OUTLINE, settings, LLMClient(settings))
    assert context["source_material"] == "Petit cours."
    assert context["outline"] == OUTLINE
    assert "section_id" in context["outline_rules"]
    assert report["source_material"]["method"] == "verbatim"


def test_long_material_is_digested_per_chunk() -> None:
    settings = dataclasses.replace(
        Settings(), fake_llm=True, source_context_max_chars=3000, source_digest_chunk_chars=2000
    )
    material = "\n\n".join(f"Paragraphe {i} " + "x" * 900 for i in range(10))

    class _Recorder(LLMClient):
        def __init__(self, settings: Settings) -> None:
            super().__init__(settings)
            self.calls: list[tuple[int, int]] = []

        def digest_source_chunk(self, chunk, budget_chars, *, part, parts, outline_titles=None):
            self.calls.append((part, parts))
            assert outline_titles == ["Pourquoi", "Comment", "Bilan"]
            return f"[digest {part}] " + chunk[:50]

    llm = _Recorder(settings)
    context, report = build_source_context(material, OUTLINE, settings, llm)
    digest = report["source_material"]
    assert digest["method"] == "digest"
    assert digest["chunks"] == len(llm.calls) >= 5
    assert len(context["source_material"]) <= 3000
    assert context["source_material"].startswith("[digest 1]")


def test_overlong_digests_keep_the_last_chunk() -> None:
    settings = dataclasses.replace(
        Settings(), fake_llm=True, source_context_max_chars=3000, source_digest_chunk_chars=2000
    )
    material = "\n\n".join(f"Paragraphe {i} " + "x" * 900 for i in range(10))

    class _Verbose(LLMClient):
        def digest_source_chunk(self, chunk, budget_chars, *, part, parts, outline_titles=None):
            # Overshoots its budget like a real model may (up to +20%).
            return f"[digest {part}] " + "z" * (budget_chars + budget_chars // 5)

    context, report = build_source_context(material, [], settings, _Verbose(settings))
    parts = report["source_material"]["chunks"]
    assert len(context["source_material"]) <= 3000
    assert f"[digest {parts}]" in context["source_material"]


def test_failed_digest_chunk_falls_back_to_excerpt() -> None:
    settings = dataclasses.replace(
        Settings(), fake_llm=True, source_context_max_chars=2000, source_digest_chunk_chars=2000
    )

    class _Broken(LLMClient):
        def digest_source_chunk(self, *args, **kwargs):
            raise RuntimeError("boom")

    context, report = build_source_context("y" * 5000, [], settings, _Broken(settings))
    assert report["source_material"]["truncated_chunks"] == 3
    assert context["source_material"]
    assert "outline" not in context


# ------------------------------------------------------------ section mapping


def _blueprint(section_ids):
    blueprint = fake_blueprint("Explain derivatives", "math", 240)
    for scene, section_id in zip(blueprint.scenes, section_ids):
        scene.section_id = section_id
    return blueprint


def test_valid_llm_mapping_is_kept() -> None:
    blueprint = _blueprint(["s1", "s1", "s2", "s2", "s2", "s2", "s3", "s3"])
    report = assign_section_ids(blueprint, OUTLINE)
    assert report == {"method": "llm", "uncovered_sections": []}


def test_partial_mapping_is_repaired_in_order() -> None:
    blueprint = _blueprint([None, "s2", "s1", "bogus", "s2", "s3", "s3", "s3"])
    report = assign_section_ids(blueprint, OUTLINE)
    assert report["method"] == "repaired"
    assert [s.section_id for s in blueprint.scenes] == ["s1", "s2", "s2", "s2", "s2", "s3", "s3", "s3"]


def test_ignored_outline_is_spread_by_duration() -> None:
    blueprint = _blueprint([None] * 8)
    report = assign_section_ids(blueprint, OUTLINE)
    assert report["method"] == "proportional"
    ids = [s.section_id for s in blueprint.scenes]
    assert ids == sorted(ids)
    assert set(ids) == {"s1", "s2", "s3"}
    assert ids.count("s2") > ids.count("s1")


def test_secondary_language_copies_master_mapping() -> None:
    master = _blueprint(["s1", "s1", "s2", "s2", "s2", "s2", "s3", "s3"]).model_dump()
    translated = _blueprint([None] * 8)
    assert copy_section_ids(translated, master)
    assert [s.section_id for s in translated.scenes] == [s["section_id"] for s in master["scenes"]]


# ------------------------------------------------------------------ timeline


def test_timeline_uses_voiceover_and_stretches_last_scene() -> None:
    blueprint = _blueprint(["s1", "s1", "s2", "s2", "s2", "s2", "s3", "s3"])
    durations = {scene.key: 10.0 for scene in blueprint.scenes}
    timeline = build_timeline(blueprint, durations, 81.5, "fr")
    assert timeline["timing_source"] == "voiceover"
    assert timeline["duration_seconds"] == 81.5
    assert (timeline["scenes"][1]["start"], timeline["scenes"][1]["end"]) == (10.0, 20.0)
    assert timeline["scenes"][-1]["end"] == 81.5
    assert [(s["section_id"], s["start"], s["end"]) for s in timeline["sections"]] == [
        ("s1", 0.0, 20.0),
        ("s2", 20.0, 60.0),
        ("s3", 60.0, 81.5),
    ]


def test_timeline_falls_back_to_planned_durations() -> None:
    blueprint = _blueprint([None] * 8)
    timeline = build_timeline(blueprint, {}, None, "en")
    assert timeline["timing_source"] == "planned"
    assert timeline["sections"] == []
    assert timeline["duration_seconds"] == sum(s.duration_seconds for s in blueprint.scenes)


# ------------------------------------------------------------ pipeline flow


def test_pipeline_grounds_blueprint_and_writes_timeline(tmp_path: Path, monkeypatch) -> None:
    pipeline, runner, job_id, _ = _pipeline(
        tmp_path, monkeypatch, review_passes=True, max_repairs=0, job_id="job-source-flow"
    )
    video_dir = pipeline.engine.materialize.return_value
    blueprint = pipeline.engine.generate_blueprint.return_value
    (video_dir / "audio" / "en").mkdir(parents=True)
    (video_dir / "audio" / "en" / "durations.json").write_text(
        json.dumps({scene.key: 12.5 for scene in blueprint.scenes}), encoding="utf-8"
    )
    workspace = Path(pipeline.settings.jobs_root) / job_id
    workspace.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        job.source_material = "Le cours complet."
        job.outline = json.dumps(OUTLINE)
        session.commit()
        source = pipeline._prepare_source(session, job, workspace)
        pipeline._run_with_repairs(session, job, workspace, runner, workspace / "reports", None, source)
        assert job.status == "completed"

    grounding = pipeline.engine.generate_blueprint.call_args.args[5]
    assert grounding["source_material"] == "Le cours complet."
    assert grounding["outline"][0]["id"] == "s1"
    saved = json.loads((workspace / "blueprint.json").read_text(encoding="utf-8"))
    assert all(scene["section_id"] in {"s1", "s2", "s3"} for scene in saved["scenes"])
    report = json.loads((workspace / "reports" / "report.json").read_text(encoding="utf-8"))
    assert report["source"]["section_mapping"]["method"] == "proportional"
    timeline = json.loads((workspace / report["timeline"]).read_text(encoding="utf-8"))
    assert timeline["scenes"][0]["end"] == 12.5
    assert [s["section_id"] for s in timeline["sections"]] == ["s1", "s2", "s3"]
