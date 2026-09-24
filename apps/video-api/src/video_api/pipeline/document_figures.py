"""Optional vision pass over the figures of an uploaded document.

The layout extractor knows where a figure is and what its caption says, not
what it contains. When a vision model is configured (VIDEO_API_VISION_MODEL),
each figure gets a short description and a handful of named regions with
boxes. The blueprint LLM then cites region ids in FigureScene callouts and the
renderer zooms onto them. Results are cached in document.json, so a document
is analysed once per model, whatever the number of videos made from it.

Every failure is non-fatal: a figure without regions still renders, with its
callouts listed beside it instead of pointing into it.
"""
from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from video_api import llm_usage
from video_api.config import Settings
from video_api.documents import Document, DocumentFigure, DocumentStore, FigureRegion


logger = logging.getLogger(__name__)

_MAX_FIGURES = 12
_MAX_REGIONS = 6
_VLM_MAX_SIDE = 1400

_SYSTEM_PROMPT = """You analyse one figure cropped from a scientific or technical document, so a
narrated explainer video can point at its parts. Return ONLY a JSON object:
{
  "description": "2-3 sentences: what the figure shows and how to read it",
  "regions": [
    {"label": "2-6 word name of one meaningful part", "box": [x0, y0, x1, y1]}
  ]
}
- 2 to 6 regions: the parts an explanation would walk through (blocks of a diagram, a panel of
  a multi-panel figure, a curve or its legend, an axis, an annotated area). Never one region per
  tiny glyph, never the whole figure.
- box: integers from 0 to 1000, relative to the image width (x) and height (y), top-left origin;
  x0 < x1 and y0 < y1. Boxes may be generous but must contain the whole part.
- Labels use the figure's own words when it has them."""


def _image_data_url(path: Any) -> str:
    import pymupdf

    pixmap = pymupdf.Pixmap(str(path))
    while max(pixmap.width, pixmap.height) > _VLM_MAX_SIDE:
        pixmap.shrink(1)
    return "data:image/png;base64," + base64.b64encode(pixmap.tobytes("png")).decode("ascii")


def parse_regions(raw: Any) -> list[FigureRegion]:
    """Validate the model's boxes (0..1000, x0<x1, y0<y1, sane area) into
    normalised [x, y, w, h] regions r1..rN."""
    regions: list[FigureRegion] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label") or "").split())[:48]
        box = item.get("box")
        if not label or not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        try:
            x0, y0, x1, y1 = (max(0.0, min(1000.0, float(v))) / 1000.0 for v in box)
        except (TypeError, ValueError):
            continue
        width, height = x1 - x0, y1 - y0
        if width <= 0.02 or height <= 0.02 or width * height > 0.9:
            continue
        regions.append(
            FigureRegion(
                id=f"r{len(regions) + 1}",
                label=label,
                box=[round(x0, 4), round(y0, 4), round(width, 4), round(height, 4)],
            )
        )
        if len(regions) >= _MAX_REGIONS:
            break
    return regions


def analyze_document_figures(document: Document, store: DocumentStore, settings: Settings) -> Document:
    """Describe and segment the document's figures once per vision model."""
    model = settings.visual_review_model
    if not model or not settings.document_figure_analysis or settings.fake_llm or not document.figures:
        return document
    if document.figures_analyzed_by == model:
        return document
    if not settings.openai_api_key:
        return document
    from openai import OpenAI

    from video_api.pipeline.llm import _extract_json_object

    client = OpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        timeout=settings.llm_timeout_seconds,
    )

    def analyze(figure: DocumentFigure) -> tuple[DocumentFigure, bool]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{figure.label}. Caption: {figure.caption or '(none)'}"},
                            {"type": "image_url", "image_url": {"url": _image_data_url(store.figure_file(document.id, figure.id))}},
                        ],
                    },
                ],
                response_format={"type": "json_object"},
                max_tokens=900,
            )
            llm_usage.record("document_figures", model, response)
            data = _extract_json_object(response.choices[0].message.content or "")
        except Exception as exc:
            logger.warning("document.figure.analysis_failed document=%s figure=%s error=%s", document.id, figure.id, exc)
            return figure, False
        description = " ".join(str(data.get("description") or "").split())[:500]
        regions = parse_regions(data.get("regions"))
        logger.info(
            "document.figure.analyzed document=%s figure=%s regions=%d", document.id, figure.id, len(regions)
        )
        return figure.model_copy(update={"description": description, "regions": regions}), True

    head = document.figures[:_MAX_FIGURES]
    with ThreadPoolExecutor(max_workers=max(1, min(4, settings.llm_parallel))) as pool:
        results = list(pool.map(analyze, head))
    if not any(ok for _, ok in results):
        # Model unreachable or not multimodal: do not cache the failure, the
        # next job retries. Figures still render without regions.
        return document
    analyzed = [figure for figure, _ in results]
    updated = document.model_copy(
        update={"figures": [*analyzed, *document.figures[_MAX_FIGURES:]], "figures_analyzed_by": model}
    )
    store.save(updated)
    return updated
