"""Content-addressed WAV cache shared by batch jobs and the sync endpoint.

A fingerprint covers everything that shapes the audio: model id, language,
normalized text and the *content hash* of the voice reference. MOSS sampling is
stochastic, so the cache is also what keeps a video's voice stable across
repair attempts: a re-run with the same text and the same anchor reuses the
exact same WAV instead of resampling a new take.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path


class AudioCache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def file_hash(path: Path | None) -> str:
        if path is None:
            return "none"
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def fingerprint(self, *, model_id: str, language: str, text: str, reference_hash: str) -> str:
        payload = "\x00".join(
            [model_id, language.strip().lower(), " ".join(text.split()), reference_hash]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def lookup(self, fingerprint: str) -> Path | None:
        path = self.root / f"{fingerprint}.wav"
        if path.exists():
            # Refresh mtime so TTL pruning keeps frequently reused entries.
            os.utime(path)
            return path
        return None

    def store(self, fingerprint: str, wav_path: Path) -> Path:
        target = self.root / f"{fingerprint}.wav"
        tmp = self.root / f"{fingerprint}.tmp"
        shutil.copyfile(wav_path, tmp)
        os.replace(tmp, target)
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
