from __future__ import annotations

from pathlib import Path


def ensure_within(path: Path, root: Path) -> Path:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    if resolved_path != resolved_root and resolved_root not in resolved_path.parents:
        raise ValueError(f"{resolved_path} is outside {resolved_root}")
    return resolved_path


def job_root(jobs_root: Path, job_id: str) -> Path:
    return ensure_within(jobs_root / job_id, jobs_root)
