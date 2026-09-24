"""Uploaded PDF documents: extraction, storage, grounding and FigureScene."""
from __future__ import annotations

import dataclasses
import functools
import json
import os
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

import video_api.main as main_module
from video_api.config import get_settings
from video_api.db import SessionLocal
from video_api.documents import DocumentError, DocumentNotFound, DocumentStore, budget_sections, gc_documents
from video_api.models import VideoJob
from video_api.pipeline.assets import AssetResolver
from video_api.pipeline.document_figures import parse_regions
from video_api.pipeline.remotion_blueprint import (
    _items_count,
    fake_remotion_blueprint,
    normalize_remotion_blueprint,
    validate_scene_payload,
)
from video_api.pipeline.remotion_materialize import _scenes_map
from video_api.pipeline.research import ResearchDossier, ResearchSource, attach_document
from video_api.documents import FigureRegion
from video_api.schemas import ProductionOptions

_BODY = (
    "Residual pipelines split a hard mapping into an easy identity plus a small correction. "
    "Each stage only learns what the previous one missed, which keeps the optimisation well "
    "conditioned even when the network becomes very deep. "
)


@functools.cache
def make_paper_pdf() -> bytes:
    """A small two-page 'paper': headings, a vector figure, a raster figure,
    captions and a reference list that must not leak into the grounding text.
    Cached: PyMuPDF stamps a creation date, and the store is content-addressed."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 80), "Residual Pipelines for Testing", fontsize=20, fontname="hebo")
    page.insert_text((72, 120), "Abstract", fontsize=12, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(72, 128, 540, 215), _BODY * 2, fontsize=10, fontname="helv")
    page.insert_text((72, 235), "1 Introduction", fontsize=12, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(72, 243, 540, 335), _BODY * 2, fontsize=10, fontname="helv")
    # Vector figure: two boxes and an arrow, with labels inside the boxes.
    page.draw_rect(pymupdf.Rect(150, 350, 250, 410), color=(0, 0, 0), fill=(0.8, 0.9, 1.0))
    page.draw_rect(pymupdf.Rect(350, 350, 450, 410), color=(0, 0, 0), fill=(1.0, 0.9, 0.8))
    page.draw_line(pymupdf.Point(250, 380), pymupdf.Point(350, 380), color=(0, 0, 0), width=2)
    page.insert_text((170, 384), "ENC-BOX", fontsize=9, fontname="helv")
    page.insert_text((370, 384), "DEC-BOX", fontsize=9, fontname="helv")
    page.insert_textbox(
        pymupdf.Rect(72, 422, 540, 450),
        "Figure 1: A two-stage pipeline: the encoder compresses the input and the decoder rebuilds it.",
        fontsize=9,
        fontname="helv",
    )
    page.insert_textbox(pymupdf.Rect(72, 470, 540, 600), _BODY * 3, fontsize=10, fontname="helv")

    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 80), "2 Method", fontsize=12, fontname="hebo")
    page.insert_textbox(pymupdf.Rect(72, 88, 540, 200), _BODY * 3, fontsize=10, fontname="helv")
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 120), False)
    pixmap.set_rect(pixmap.irect, (40, 90, 200))
    pixmap.set_rect(pymupdf.IRect(20, 20, 120, 100), (230, 60, 60))
    page.insert_image(pymupdf.Rect(150, 220, 450, 400), pixmap=pixmap)
    page.insert_textbox(
        pymupdf.Rect(72, 410, 540, 440),
        "Figure 2: Measured error for each configuration of the residual pipeline.",
        fontsize=9,
        fontname="helv",
    )
    page.insert_text((72, 480), "References", fontsize=12, fontname="hebo")
    page.insert_textbox(
        pymupdf.Rect(72, 488, 540, 560),
        "[1] A. Author. A citation that must not be narrated. Journal of Tests, 2020.",
        fontsize=9,
        fontname="helv",
    )
    return doc.tobytes()


@pytest.fixture()
def store(tmp_path: Path) -> DocumentStore:
    return DocumentStore(tmp_path / "documents")


@pytest.fixture()
def paper(store: DocumentStore):
    return store.ingest(make_paper_pdf(), "paper.pdf", max_pages=60)


def test_extraction_finds_title_sections_and_figures(store: DocumentStore, paper) -> None:
    assert paper.title == "Residual Pipelines for Testing"
    assert paper.id.startswith("doc_") and len(paper.id) == 28
    headings = [section.heading for section in paper.sections]
    assert headings == ["Abstract", "1 Introduction", "2 Method"]
    assert paper.abstract.startswith("Residual pipelines split")
    text = " ".join(section.text for section in paper.sections)
    # Figure-internal labels, captions and the reference list stay out of the grounding text.
    assert "ENC-BOX" not in text and "DEC-BOX" not in text
    assert "Figure 1:" not in text
    assert "must not be narrated" not in text

    assert [figure.label for figure in paper.figures] == ["Figure 1", "Figure 2"]
    first, second = paper.figures
    assert first.caption.startswith("Figure 1: A two-stage pipeline")
    assert (first.page, second.page) == (1, 2)
    for figure in paper.figures:
        png = store.figure_file(paper.id, figure.id)
        assert png.is_file() and png.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        assert figure.width >= 1000  # rendered at high resolution for zooms
    # The vector figure is wide (two boxes side by side), tightly cropped.
    assert 3.0 < first.width / first.height < 7.0


def test_ingest_is_idempotent_and_ids_are_validated(store: DocumentStore, paper) -> None:
    again = store.ingest(make_paper_pdf(), "renamed.pdf", max_pages=60)
    assert again.id == paper.id and again.filename == "paper.pdf"
    assert store.exists(paper.id)
    assert not store.exists("doc_../../etc")
    with pytest.raises(DocumentNotFound):
        store.load("doc_000000000000000000000000")
    with pytest.raises(DocumentNotFound):
        store.figure_file(paper.id, "../source")


def test_unusable_pdfs_are_rejected(store: DocumentStore) -> None:
    blank = pymupdf.open()
    blank.new_page()
    with pytest.raises(DocumentError, match="no extractable text"):
        store.ingest(blank.tobytes(), "scan.pdf", max_pages=60)
    with pytest.raises(DocumentError, match="unreadable PDF"):
        store.ingest(b"%PDF-1.7 not really a pdf", "broken.pdf", max_pages=60)
    assert not any(store.root.iterdir())  # no half-written document left behind


def test_budget_keeps_short_sections_whole_and_truncates_long_ones(paper) -> None:
    sections = [
        paper.sections[0].model_copy(update={"text": "short. " * 10}),
        paper.sections[1].model_copy(update={"text": "A long sentence here. " * 400}),
    ]
    budgeted = budget_sections(sections, 2000)
    assert budgeted[0][1] == sections[0].text
    assert len(budgeted[1][1]) <= 2000 - len(sections[0].text) + 10
    assert budgeted[1][1].endswith("[…]")


def test_document_becomes_grounding_sources_and_figure_catalogue(paper) -> None:
    dossier = attach_document(None, paper, budget_chars=24000)
    assert dossier.provider == "document"
    assert [source.id for source in dossier.sources] == ["doc_01", "doc_02", "doc_03"]
    context = dossier.prompt_context()
    assert context["document"]["title"] == paper.title
    assert "FigureScene" in context["research_rules"]
    assert [figure["id"] for figure in context["figures"]] == ["fig_01", "fig_02"]
    # Manim never receives the figure catalogue.
    no_figures = dossier.prompt_context(include_figures=False)
    assert "figures" not in no_figures and "FigureScene" not in no_figures["research_rules"]

    web = ResearchDossier(
        query="q",
        provider="tavily",
        generated_at="now",
        sources=[ResearchSource(id="src_01", url="https://example.org", excerpt="x" * 5000, provider="tavily")],
    )
    merged = attach_document(web, paper, budget_chars=24000)
    assert merged.provider == "document+tavily"
    assert [source.id for source in merged.sources][-1] == "src_01"
    assert len(merged.prompt_context()["sources"][-1]["excerpt"]) == 1800  # web excerpts stay capped


def test_production_options_for_a_document() -> None:
    doc_id = "doc_" + "a" * 24
    options = ProductionOptions(document_id=doc_id)
    assert options.render_engine == "remotion"
    assert options.research.enabled is False
    explicit = ProductionOptions(mode="editorial", document_id=doc_id, research={"enabled": True})
    assert explicit.research.enabled is True
    with pytest.raises(ValueError):
        ProductionOptions(document_id="../../etc/passwd")


def test_vision_regions_are_validated() -> None:
    regions = parse_regions(
        [
            {"label": "Encoder stack", "box": [50, 100, 450, 900]},
            {"label": "whole figure", "box": [0, 0, 1000, 1000]},  # too large
            {"label": "inverted", "box": [500, 500, 400, 600]},
            {"label": "", "box": [0, 0, 100, 100]},
            "junk",
        ]
    )
    assert [(r.id, r.label) for r in regions] == [("r1", "Encoder stack")]
    assert regions[0].box == [0.05, 0.1, 0.4, 0.8]


def test_figure_scene_normalisation_and_strict_validation() -> None:
    data = normalize_remotion_blueprint(
        {
            "title": "t",
            "scenes": [
                {
                    "key": "Scene1_FigEN",
                    "title": "The pipeline",
                    "narration": "n",
                    "component": "figure",
                    "props": {
                        "figure_id": "fig_01",
                        "src": "https://evil.example/x.png",
                        "callouts": ["Encoder", {"label": "Decoder", "region": "r2", "box": [0, 0, 1, 1]}, {}],
                    },
                }
            ],
        },
        60,
    )
    scene = data["scenes"][0]
    assert scene["component"] == "FigureScene"
    assert scene["props"] == {
        "title": "The pipeline",
        "figure_id": "fig_01",
        "callouts": [{"label": "Encoder"}, {"label": "Decoder", "region": "r2"}],
    }
    assert _items_count("FigureScene", scene["props"]) == 2
    errors = validate_scene_payload(
        {"component": "FigureScene", "props": {"callouts": []}, "narration": "word " * 30, "beats": []}
    )
    assert any("figure_id" in e for e in errors) and any("callouts" in e for e in errors)


def test_figure_scene_resolves_the_stored_figure(tmp_path: Path, store: DocumentStore, paper) -> None:
    figure = paper.figures[0].model_copy(
        update={"regions": [FigureRegion(id="r1", label="Encoder", box=[0.0, 0.0, 0.4, 1.0])]}
    )
    paper = paper.model_copy(update={"figures": [figure, *paper.figures[1:]]})
    dossier = attach_document(None, paper, budget_chars=24000)
    settings = dataclasses.replace(get_settings(), documents_root=store.root)

    blueprint = fake_remotion_blueprint(
        "Explain the paper", research_context=dossier.prompt_context(), production_context={"mode": "editorial"}
    )
    figure_scene = blueprint.scenes[1]
    assert figure_scene.component == "FigureScene"
    blueprint.scenes[3].component = "FigureScene"
    blueprint.scenes[3].props = {"figure_id": "fig_99", "callouts": [{"label": "x"}]}

    workspace = tmp_path / "job"
    manifest = AssetResolver(settings).resolve(blueprint, workspace, allow_stock=False, max_assets=0, dossier=dossier)

    props = figure_scene.props
    assert props["src"] == f"assets/{figure_scene.key}-fig_01.png"
    assert (workspace / props["src"]).read_bytes() == store.figure_file(paper.id, "fig_01").read_bytes()
    assert props["aspect"] == pytest.approx(figure.width / figure.height, rel=1e-3)
    assert props["credit"] == f"Figure 1 · {paper.title}"
    assert props["callouts"][0]["box"] == [0.0, 0.0, 0.4, 1.0]
    assert all("box" not in c for c in props["callouts"][1:])
    # An unknown figure degrades to a deterministic diagram, never a blank frame.
    assert blueprint.scenes[3].component == "BulletScene"
    statuses = {record.scene_key: (record.status, record.provider) for record in manifest.assets}
    assert statuses[figure_scene.key] == ("acquired", "document")
    assert statuses[blueprint.scenes[3].key] == ("fallback", "document")

    scene_map = _scenes_map(blueprint, fps=30, entry_id="e1", caption_mode="off", transition_profile="minimal")
    mapped = next(s for s in scene_map["scenes"] if s["key"] == figure_scene.key)
    assert mapped["props"]["src"] == f"job-assets/e1/{figure_scene.key}-fig_01.png"


def test_gc_removes_documents_unused_for_ttl(store: DocumentStore, paper) -> None:
    manifest = store.path(paper.id) / "document.json"
    old = time.time() - 20 * 86400
    os.utime(manifest, (old, old))
    assert gc_documents(store.root, ttl_days=30) == 0
    assert gc_documents(store.root, ttl_days=15) == 1
    assert not store.exists(paper.id)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
class _StubTask:
    def delay(self, job_id: str):  # noqa: ARG002
        return type("Result", (), {"id": "stub-task-id"})()


@pytest.fixture()
def client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(main_module, "run_video_job", _StubTask())
    monkeypatch.setattr(
        main_module, "settings", dataclasses.replace(main_module.settings, documents_root=tmp_path / "documents")
    )
    with TestClient(main_module.app) as test_client:
        yield test_client


def test_upload_then_create_a_video_from_the_document(client: TestClient) -> None:
    response = client.post("/v1/documents", files={"file": ("paper.pdf", make_paper_pdf(), "application/pdf")})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Residual Pipelines for Testing"
    assert [s["heading"] for s in body["sections"]] == ["Abstract", "1 Introduction", "2 Method"]
    assert len(body["figures"]) == 2
    document_id = body["document_id"]

    assert client.get(f"/v1/documents/{document_id}").json()["document_id"] == document_id
    image = client.get(body["figures"][0]["image_url"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert client.get(f"/v1/documents/{document_id}/figures/fig_09").status_code == 404
    assert client.get("/v1/documents/doc_000000000000000000000000").status_code == 404

    created = client.post(
        "/v1/videos", json={"prompt": "Explain this paper to students", "document_id": document_id}
    )
    assert created.status_code == 202, created.text
    with SessionLocal() as session:
        job = session.get(VideoJob, created.json()["job_id"])
        config = json.loads(job.production_config)
    assert config["document_id"] == document_id
    assert config["render_engine"] == "remotion"
    assert config["research"]["enabled"] is False


def test_upload_and_create_validation(client: TestClient) -> None:
    not_pdf = client.post("/v1/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert not_pdf.status_code == 415
    blank = pymupdf.open()
    blank.new_page()
    scanned = client.post("/v1/documents", files={"file": ("scan.pdf", blank.tobytes(), "application/pdf")})
    assert scanned.status_code == 422 and "OCR" in scanned.json()["detail"]
    unknown = client.post(
        "/v1/videos", json={"prompt": "Explain this paper to students", "document_id": "doc_" + "0" * 24}
    )
    assert unknown.status_code == 422 and "POST /v1/documents" in unknown.json()["detail"]
    malformed = client.post("/v1/videos", json={"prompt": "Explain this paper to students", "document_id": "x"})
    assert malformed.status_code == 422


def test_worker_turns_the_document_into_the_job_dossier(tmp_path: Path, store: DocumentStore, paper, monkeypatch) -> None:
    from types import SimpleNamespace

    from video_api.pipeline.production import VideoPipeline

    settings = dataclasses.replace(get_settings(), documents_root=store.root, jobs_root=tmp_path / "jobs")
    pipeline = VideoPipeline(settings)
    pipeline._apply_production_config(ProductionOptions(document_id=paper.id).model_dump_json())
    steps: list[str] = []
    monkeypatch.setattr(pipeline, "_update", lambda _session, _job, _status, _progress, step, **_: steps.append(step))
    job = SimpleNamespace(id="job-1", prompt="Explain the paper", batch_id=None, is_primary=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    dossier = pipeline._prepare_research(None, job, workspace)

    assert steps == ["reading_document"]  # no web research unless requested
    assert pipeline.engine.name == "remotion"
    assert dossier.document.id == paper.id
    stored = json.loads((workspace / "research.json").read_text(encoding="utf-8"))
    assert [figure["id"] for figure in stored["figures"]] == ["fig_01", "fig_02"]
    assert "figures" in pipeline._research_context(dossier)
