"""HTTP contracts of the TTS server."""
from __future__ import annotations

from pydantic import BaseModel, Field

# Keys become file names (<key>.wav) inside the job directory: the pattern is
# the path-traversal guard for the download endpoint.
KEY_PATTERN = r"^[A-Za-z0-9_.-]{1,80}$"


class BatchSegment(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    text: str = Field(min_length=1)


class BatchRequest(BaseModel):
    segments: list[BatchSegment] = Field(min_length=1)
    language: str = "en"
    # Optional sanity check: if set, must match the model the server loaded.
    model: str | None = None
    consistent_voice: bool = True
    # Base64 WAV used as the voice-cloning reference for every segment. When
    # absent and consistent_voice=true, the first generated segment anchors
    # the rest server-side.
    reference_audio_b64: str | None = None
    # Accepted for parity with the local engine's CLI; the native MOSS
    # generator does not consume it.
    reference_text: str | None = None


class SyncRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str = "en"
    model: str | None = None
    reference_audio_b64: str | None = None


class JobCreated(BaseModel):
    job_id: str
    status: str
    status_url: str
