"""Multi-language batch: one prompt -> several videos, identical content, only
the spoken language translated. The primary language generates the master
blueprint; secondaries translate it after the primary completes."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import video_api.main as main_module
from video_api.db import SessionLocal, init_db
from video_api.models import VideoJob
from video_api.schemas import VideoCreateRequest


class _StubAsyncResult:
    def __init__(self, job_id: str) -> None:
        self.id = f"task-{job_id}"


class _RecordingTask:
    """Stub Celery task that records which job ids were enqueued."""

    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def delay(self, job_id: str) -> _StubAsyncResult:
        self.enqueued.append(job_id)
        return _StubAsyncResult(job_id)


@pytest.fixture()
def stub_task(monkeypatch) -> _RecordingTask:
    task = _RecordingTask()
    monkeypatch.setattr(main_module, "run_video_job", task)
    return task


@pytest.fixture()
def client(stub_task: _RecordingTask) -> TestClient:
    with TestClient(main_module.app) as test_client:
        yield test_client


def _payload(**overrides) -> dict:
    return {
        "prompt": "Explain how virtual memory and page tables work together",
        "theme": "linux-fondamentaux",
        **overrides,
    }


# --------------------------------------------------------------------------- schema
def test_resolved_languages_dedupes_and_normalises() -> None:
    req = VideoCreateRequest(prompt="x" * 20, languages=["francais", "fr", "EN", "en"])
    assert req.resolved_languages() == ["fr", "en"]


def test_resolved_languages_single_defaults_to_language() -> None:
    req = VideoCreateRequest(prompt="x" * 20, language="es")
    assert req.resolved_languages() == ["es"]


# --------------------------------------------------------------------------- creation
def test_single_language_is_not_a_batch(client: TestClient, stub_task: _RecordingTask) -> None:
    body = client.post("/v1/videos", json=_payload(language="fr")).json()
    assert body["batch_id"] is None
    assert body.get("jobs") is None
    assert stub_task.enqueued == [body["job_id"]]
    status = client.get(f"/v1/videos/{body['job_id']}").json()
    assert status["language"] == "fr"
    assert status["batch_id"] is None


def test_multi_language_creates_batch(client: TestClient, stub_task: _RecordingTask) -> None:
    response = client.post("/v1/videos", json=_payload(languages=["en", "fr", "es"]))
    assert response.status_code == 202, response.text
    body = response.json()
    batch_id = body["batch_id"]
    assert batch_id is not None
    assert [job["language"] for job in body["jobs"]] == ["en", "fr", "es"]

    # Only the primary (first language) is enqueued at creation time.
    primary = next(job for job in body["jobs"] if job["is_primary"])
    assert primary["language"] == "en"
    assert stub_task.enqueued == [primary["job_id"]]

    # Secondaries persist as queued, waiting for the master blueprint.
    with SessionLocal() as session:
        rows = session.query(VideoJob).filter(VideoJob.batch_id == batch_id).all()
        by_lang = {row.language: row for row in rows}
    assert by_lang["en"].is_primary is True
    assert by_lang["en"].current_step == "queued"
    assert by_lang["fr"].is_primary is False
    assert by_lang["fr"].current_step == "waiting_for_master"
    assert by_lang["es"].current_step == "waiting_for_master"


def test_batch_status_endpoint(client: TestClient) -> None:
    batch_id = client.post("/v1/videos", json=_payload(languages=["en", "fr"])).json()["batch_id"]
    body = client.get(f"/v1/batches/{batch_id}").json()
    assert body["batch_id"] == batch_id
    assert sorted(body["languages"]) == ["en", "fr"]
    assert len(body["jobs"]) == 2


def test_batch_status_not_found(client: TestClient) -> None:
    assert client.get("/v1/batches/does-not-exist").status_code == 404


# --------------------------------------------------------------------------- fan-out
def test_fan_out_enqueues_secondaries_once(monkeypatch) -> None:
    import video_api.tasks as tasks_module

    init_db()
    task = _RecordingTask()
    monkeypatch.setattr(tasks_module, "run_video_job", task)

    batch_id = "batch-fanout"
    with SessionLocal() as session:
        session.add(
            VideoJob(
                id="primary-1", prompt="p", language="en", batch_id=batch_id,
                is_primary=True, status="completed", progress=100,
                current_step="completed", artifact_dir="/tmp/primary-1",
            )
        )
        for jid, lang in (("sec-fr", "fr"), ("sec-es", "es")):
            session.add(
                VideoJob(
                    id=jid, prompt="p", language=lang, batch_id=batch_id,
                    is_primary=False, status="queued",
                    current_step="waiting_for_master", artifact_dir=f"/tmp/{jid}",
                )
            )
        session.commit()

    tasks_module._fan_out_batch("primary-1")
    assert sorted(task.enqueued) == ["sec-es", "sec-fr"]

    # Idempotent: a second call does not re-enqueue (they left waiting_for_master).
    task.enqueued.clear()
    tasks_module._fan_out_batch("primary-1")
    assert task.enqueued == []


def test_abort_marks_waiting_secondaries_failed(monkeypatch) -> None:
    import video_api.tasks as tasks_module

    init_db()
    monkeypatch.setattr(tasks_module, "run_video_job", _RecordingTask())

    batch_id = "batch-abort"
    with SessionLocal() as session:
        session.add(
            VideoJob(
                id="primary-2", prompt="p", language="en", batch_id=batch_id,
                is_primary=True, status="failed_generation", progress=10,
                current_step="planning", artifact_dir="/tmp/primary-2",
            )
        )
        session.add(
            VideoJob(
                id="sec-de", prompt="p", language="de", batch_id=batch_id,
                is_primary=False, status="queued",
                current_step="waiting_for_master", artifact_dir="/tmp/sec-de",
            )
        )
        session.commit()

    tasks_module._abort_batch_secondaries("primary-2", "failed_generation")
    with SessionLocal() as session:
        sec = session.get(VideoJob, "sec-de")
        assert sec.status == "failed_generation"
        assert "did not complete" in (sec.error_message or "")


# --------------------------------------------------------------------------- translation
def test_translate_blueprint_fake_round_trips_master() -> None:
    from video_api.config import Settings
    from video_api.pipeline.llm import LLMClient, fake_blueprint

    master = fake_blueprint("Explain derivatives", "math").model_dump()
    translated = LLMClient(Settings(fake_llm=True)).translate_blueprint(master, "fr")
    # Same structure (slug, scene keys, durations) — fake mode keeps content verbatim.
    assert translated.slug == master["slug"]
    assert [s.key for s in translated.scenes] == [s["key"] for s in master["scenes"]]


def test_translate_remotion_blueprint_fake_round_trips_master() -> None:
    from video_api.config import Settings
    from video_api.pipeline.llm import LLMClient
    from video_api.pipeline.remotion_blueprint import fake_remotion_blueprint

    master = fake_remotion_blueprint("Explain derivatives", "math").model_dump()
    translated = LLMClient(Settings(fake_llm=True)).translate_remotion_blueprint(master, "es")
    assert translated.slug == master["slug"]
    assert [s.key for s in translated.scenes] == [s["key"] for s in master["scenes"]]
