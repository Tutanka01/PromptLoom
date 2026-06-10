"""Test environment defaults, applied BEFORE any video_api import.

The Docker test service sets these explicitly (compose.yaml); these
setdefault() calls make the suite runnable locally too (sqlite in-memory via a
shared StaticPool — see db._engine_kwargs — and the deterministic fake LLM).
"""
import os

os.environ.setdefault("VIDEO_API_DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("VIDEO_API_FAKE_LLM", "1")
os.environ.setdefault("VIDEO_API_JOBS_ROOT", "/tmp/video-api-test-jobs")
