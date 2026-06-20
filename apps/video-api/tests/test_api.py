from __future__ import annotations

import dataclasses
import json
import uuid

import pytest
from fastapi.testclient import TestClient

import video_api.main as main_module
from video_api.db import SessionLocal, init_db
from video_api.models import VideoJob


class _StubAsyncResult:
    id = "stub-task-id"


class _StubTask:
    def delay(self, job_id: str) -> _StubAsyncResult:  # noqa: ARG002
        return _StubAsyncResult()


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(main_module, "run_video_job", _StubTask())
    with TestClient(main_module.app) as test_client:
        yield test_client


def _create_job(client: TestClient, **overrides) -> str:
    payload = {
        "prompt": "Explain how virtual memory and page tables work together",
        "theme": "linux-fondamentaux",
        **overrides,
    }
    response = client.post("/v1/videos", json=payload)
    assert response.status_code == 202, response.text
    return response.json()["job_id"]


def test_create_then_status(client: TestClient) -> None:
    job_id = _create_job(client, quality_profile="draft")
    response = client.get(f"/v1/videos/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["quality_profile"] == "draft"
    assert body["download_url"] is None


def test_cinematic_options_are_persisted_per_job(client: TestClient) -> None:
    job_id = _create_job(
        client,
        production_mode="cinematic",
        research={"enabled": True, "required": False, "max_sources": 8},
        visuals={"strategy": "motion_first", "allow_stock": True, "max_assets": 3},
        captions="full",
    )
    response = client.get(f"/v1/videos/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["render_engine"] == "remotion"
    assert body["production_mode"] == "cinematic"
    with SessionLocal() as session:
        job = session.get(VideoJob, job_id)
        config = json.loads(job.production_config)
    assert config["visuals"]["max_assets"] == 3
    assert config["captions"] == "full"


def test_cinematic_manim_is_rejected_as_request_validation(client: TestClient) -> None:
    response = client.post(
        "/v1/videos",
        json={
            "prompt": "Explain how virtual memory and page tables work together",
            "production_mode": "cinematic",
            "render_engine": "manim",
        },
    )
    assert response.status_code == 422
    assert "requires render_engine='remotion'" in response.text


def test_status_not_found(client: TestClient) -> None:
    assert client.get(f"/v1/videos/{uuid.uuid4()}").status_code == 404


def test_list_videos(client: TestClient) -> None:
    job_id = _create_job(client)
    body = client.get("/v1/videos", params={"limit": 10}).json()
    assert any(job["job_id"] == job_id for job in body["jobs"])
    filtered = client.get("/v1/videos", params={"status": "queued"}).json()
    assert all(job["status"] == "queued" for job in filtered["jobs"])


def test_cancel_job(client: TestClient) -> None:
    job_id = _create_job(client)
    response = client.delete(f"/v1/videos/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    # A second cancel is a conflict: the job is already terminal.
    assert client.delete(f"/v1/videos/{job_id}").status_code == 409


def test_download_not_ready(client: TestClient) -> None:
    job_id = _create_job(client)
    assert client.get(f"/v1/videos/{job_id}/download").status_code == 409


def test_artifact_not_found(client: TestClient) -> None:
    job_id = _create_job(client)
    assert client.get(f"/v1/videos/{job_id}/artifacts/logs/render-low.log").status_code == 404


def test_artifact_path_traversal_rejected(client: TestClient) -> None:
    job_id = _create_job(client)
    response = client.get(f"/v1/videos/{job_id}/artifacts/../../../etc/passwd")
    assert response.status_code in (400, 404)


def test_healthz_reports_checks(client: TestClient) -> None:
    response = client.get("/healthz")
    body = response.json()
    assert "checks" in body
    assert body["checks"]["database"] == "ok"
    # Redis is not reachable in the unit-test environment: degraded, not a 500.
    assert response.status_code in (200, 503)


def test_api_key_enforced_when_configured(client: TestClient, monkeypatch) -> None:
    secured = dataclasses.replace(main_module.settings, api_keys=("sesame",))
    monkeypatch.setattr(main_module, "settings", secured)
    assert client.get("/v1/videos").status_code == 401
    assert client.get("/v1/videos", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/v1/videos", headers={"X-API-Key": "sesame"}).status_code == 200
    # healthz stays open (probes have no key)
    assert client.get("/healthz").status_code in (200, 503)


def test_cooperative_cancel_aborts_pipeline() -> None:
    from video_api.config import Settings
    from video_api.pipeline.production import JobCancelled, VideoPipeline

    init_db()
    job_id = str(uuid.uuid4())
    with SessionLocal() as session:
        job = VideoJob(
            id=job_id,
            prompt="cancel me",
            language="en",
            status="cancelled",
            progress=10,
            current_step="planning",
            artifact_dir=f"/tmp/video-api-test-jobs/{job_id}",
        )
        session.add(job)
        session.commit()

        pipeline = VideoPipeline(Settings(fake_llm=True))
        with pytest.raises(JobCancelled):
            pipeline._update(session, job, "voice_generation", 40, "voice_generation")


def test_webhook_signature_and_retry(monkeypatch) -> None:
    import hashlib
    import hmac as hmac_lib

    import httpx

    from video_api.config import Settings
    from video_api.webhooks import notify_job_terminal

    calls: list[dict] = []

    class _Response:
        def __init__(self, status_code: int):
            self.status_code = status_code

    def fake_post(url, content=None, headers=None, timeout=None):  # noqa: ARG001
        calls.append({"url": url, "content": content, "headers": headers})
        # first attempt fails, second succeeds
        return _Response(500 if len(calls) == 1 else 200)

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("video_api.webhooks._BACKOFF_SECONDS", (0.0, 0.0, 0.0))

    job = VideoJob(
        id="wh-1",
        prompt="x",
        language="en",
        status="completed",
        progress=100,
        current_step="completed",
        artifact_dir="/tmp/x",
        callback_url="https://example.test/hook",
        report_path="/tmp/x/report.json",
    )
    settings = Settings(fake_llm=True, webhook_secret="s3cret")
    assert notify_job_terminal(job, settings) is True
    assert len(calls) == 2
    body = calls[-1]["content"]
    expected = hmac_lib.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert calls[-1]["headers"]["X-Video-API-Signature"] == f"sha256={expected}"


def test_webhook_skipped_without_url() -> None:
    from video_api.config import Settings
    from video_api.webhooks import notify_job_terminal

    job = VideoJob(
        id="wh-2",
        prompt="x",
        language="en",
        status="completed",
        progress=100,
        current_step="completed",
        artifact_dir="/tmp/x",
    )
    assert notify_job_terminal(job, Settings(fake_llm=True)) is False
