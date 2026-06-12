from __future__ import annotations

import base64
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tts_server.config import Settings
from tts_server.main import create_app

AUTH = {"Authorization": "Bearer test-key"}


@pytest.fixture()
def client(tmp_path: Path):
    settings = Settings(
        api_keys=("test-key",),
        fake_engine=True,
        data_dir=tmp_path / "data",
        model_id="OpenMOSS-Team/MOSS-TTS-v1.5",
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        _wait_for_ready(test_client)
        yield test_client


def _wait_for_ready(test_client: TestClient, deadline_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if test_client.get("/healthz").status_code == 200:
            return
        time.sleep(0.05)
    raise AssertionError("engine never became ready")


def _wait_for_job(test_client: TestClient, job_id: str, deadline_seconds: float = 30.0) -> dict:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        response = test_client.get(f"/v1/jobs/{job_id}", headers=AUTH)
        assert response.status_code == 200
        state = response.json()
        if state["status"] in {"completed", "failed"}:
            return state
        time.sleep(0.05)
    raise AssertionError("job never reached a terminal state")


def _batch_payload(**overrides) -> dict:
    payload = {
        "language": "en",
        "consistent_voice": True,
        "segments": [
            {"key": "Scene1_IntroEN", "text": "The kernel sits between hardware and programs."},
            {"key": "Scene2_SyscallEN", "text": "A system call crosses that boundary."},
        ],
    }
    payload.update(overrides)
    return payload


def test_healthz_reports_engine_without_auth(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "fake"
    assert body["state"] == "ready"
    assert body["auth"] is True


def test_endpoints_require_api_key(client: TestClient) -> None:
    assert client.post("/v1/tts/batch", json=_batch_payload()).status_code == 401
    assert client.get("/v1/jobs/whatever").status_code == 401
    assert client.post("/v1/tts", json={"text": "hi"}).status_code == 401
    wrong = {"Authorization": "Bearer nope"}
    assert client.post("/v1/tts/batch", json=_batch_payload(), headers=wrong).status_code == 401


def test_batch_job_completes_and_serves_wav(client: TestClient) -> None:
    response = client.post("/v1/tts/batch", json=_batch_payload(), headers=AUTH)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    state = _wait_for_job(client, job_id)
    assert state["status"] == "completed"
    assert [segment["status"] for segment in state["segments"]] == ["done", "done"]
    assert all(segment["duration_seconds"] > 0 for segment in state["segments"])

    wav = client.get(state["segments"][0]["wav_url"], headers=AUTH)
    assert wav.status_code == 200
    assert wav.headers["content-type"].startswith("audio/wav")
    assert wav.content[:4] == b"RIFF"


def test_consistent_voice_anchors_following_segments(client: TestClient) -> None:
    response = client.post("/v1/tts/batch", json=_batch_payload(), headers=AUTH)
    job_id = response.json()["job_id"]
    _wait_for_job(client, job_id)

    calls = client.app.state.engine.calls
    assert calls[0][2] == ""  # first segment has no reference
    assert calls[1][2].endswith("Scene1_IntroEN.wav")  # second is anchored to it


def test_uploaded_reference_is_used_for_all_segments(client: TestClient) -> None:
    reference = base64.b64encode(b"RIFFfake-reference").decode("ascii")
    payload = _batch_payload(reference_audio_b64=reference)
    response = client.post("/v1/tts/batch", json=payload, headers=AUTH)
    job_id = response.json()["job_id"]
    _wait_for_job(client, job_id)

    calls = client.app.state.engine.calls
    assert all(call[2].endswith("reference.wav") for call in calls[-2:])


def test_second_identical_batch_hits_the_cache(client: TestClient) -> None:
    first = client.post("/v1/tts/batch", json=_batch_payload(), headers=AUTH)
    _wait_for_job(client, first.json()["job_id"])
    synth_calls = len(client.app.state.engine.calls)

    second = client.post("/v1/tts/batch", json=_batch_payload(), headers=AUTH)
    state = _wait_for_job(client, second.json()["job_id"])

    assert state["status"] == "completed"
    assert all(segment["cached"] for segment in state["segments"])
    assert len(client.app.state.engine.calls) == synth_calls  # no new synthesis


def test_sync_endpoint_returns_wav_bytes(client: TestClient) -> None:
    response = client.post(
        "/v1/tts", json={"text": "Hello kernel.", "language": "en"}, headers=AUTH
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content[:4] == b"RIFF"


def test_model_mismatch_is_rejected(client: TestClient) -> None:
    payload = _batch_payload(model="some-other/model")
    response = client.post("/v1/tts/batch", json=payload, headers=AUTH)
    assert response.status_code == 409


def test_unsupported_language_is_rejected(client: TestClient) -> None:
    payload = _batch_payload(language="xx")
    response = client.post("/v1/tts/batch", json=payload, headers=AUTH)
    assert response.status_code == 422


def test_duplicate_segment_keys_are_rejected(client: TestClient) -> None:
    payload = _batch_payload(
        segments=[{"key": "Scene1", "text": "a"}, {"key": "Scene1", "text": "b"}]
    )
    response = client.post("/v1/tts/batch", json=payload, headers=AUTH)
    assert response.status_code == 422


def test_invalid_reference_base64_is_rejected(client: TestClient) -> None:
    payload = _batch_payload(reference_audio_b64="not!!base64")
    response = client.post("/v1/tts/batch", json=payload, headers=AUTH)
    assert response.status_code == 422


def test_traversal_filenames_are_rejected(client: TestClient) -> None:
    response = client.post("/v1/tts/batch", json=_batch_payload(), headers=AUTH)
    job_id = response.json()["job_id"]
    _wait_for_job(client, job_id)
    assert client.get(f"/v1/jobs/{job_id}/audio/job.json", headers=AUTH).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/audio/..%2Fjob.json", headers=AUTH).status_code == 404
