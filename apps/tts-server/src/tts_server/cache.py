"""Versioned content-addressed WAV cache shared by every TTS endpoint.

The cache key is fail-closed: an immutable synthesis profile captures the exact
model/code revisions, image identity, runtime, dtype, attention backend,
generation policy and output format. A per-request synthesis profile then adds
the language, exact text and SHA-256 of the voice anchor. The final fingerprint
namespaces that profile for the WAV cache. Text is never whitespace-normalized,
because line breaks can change MOSS prosody.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from collections.abc import Mapping
from pathlib import Path

PROFILE_SCHEMA = "promptloom-moss-synthesis-profile-v2"
CACHE_KEY_SCHEMA = "promptloom-moss-wav-cache-v2"


def _canonical_json(payload: Mapping) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class AudioCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def file_hash(path: Path | None) -> str | None:
        if path is None:
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def engine_profile_id(engine_profile: Mapping) -> str:
        payload = {
            "schema": PROFILE_SCHEMA,
            "engine_profile": engine_profile,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    @staticmethod
    def synthesis_profile_id(
        *,
        engine_profile: Mapping,
        language: str,
        text: str,
        reference_hash: str | None,
    ) -> str:
        payload = {
            "schema": PROFILE_SCHEMA,
            "engine_profile": engine_profile,
            "request": {
                "language": language.strip().lower(),
                "text": text,
            },
            "reference_sha256": reference_hash,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    @staticmethod
    def fingerprint(*, synthesis_profile_id: str) -> str:
        payload = {
            "schema": CACHE_KEY_SCHEMA,
            "synthesis_profile_id": synthesis_profile_id,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()

    @classmethod
    def identity(
        cls,
        *,
        engine_profile: Mapping,
        language: str,
        text: str,
        reference_hash: str | None,
    ) -> tuple[str, str]:
        profile_id = cls.synthesis_profile_id(
            engine_profile=engine_profile,
            language=language,
            text=text,
            reference_hash=reference_hash,
        )
        return profile_id, cls.fingerprint(
            synthesis_profile_id=profile_id,
        )

    def lookup(self, fingerprint: str) -> Path | None:
        path = self.root / f"{fingerprint}.wav"
        if path.exists():
            # Refresh mtime so TTL pruning keeps frequently reused entries.
            os.utime(path)
            return path
        return None

    def store(self, fingerprint: str, wav_path: Path) -> Path:
        target = self.root / f"{fingerprint}.wav"
        tmp = self.root / f".{fingerprint}.{uuid.uuid4().hex}.tmp"
        try:
            shutil.copyfile(wav_path, tmp)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return target

    def prune(self, ttl_days: float) -> int:
        if ttl_days <= 0:
            return 0
        cutoff = time.time() - ttl_days * 86400
        removed = 0
        for path in self.root.glob("*.wav"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
                    removed += 1
            except OSError:
                continue
        return removed
