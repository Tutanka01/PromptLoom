"""Per-job LLM token accounting, surfaced as ``llm_usage`` in report.json.

A Celery worker process runs one job at a time, so a process-wide accumulator
reset at job start is enough; the lock covers the scene coders' thread pools.
"""
from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_stages: dict[str, dict[str, Any]] = {}


def reset() -> None:
    with _lock:
        _stages.clear()


def record(stage: str, model: str, response: Any) -> None:
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    with _lock:
        entry = _stages.setdefault(
            stage,
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "models": []},
        )
        entry["calls"] += 1
        entry["prompt_tokens"] += prompt_tokens
        entry["completion_tokens"] += completion_tokens
        if model and model not in entry["models"]:
            entry["models"].append(model)


def snapshot() -> dict[str, Any]:
    with _lock:
        stages = {name: {**entry, "models": list(entry["models"])} for name, entry in _stages.items()}
    return {
        "calls": sum(entry["calls"] for entry in stages.values()),
        "prompt_tokens": sum(entry["prompt_tokens"] for entry in stages.values()),
        "completion_tokens": sum(entry["completion_tokens"] for entry in stages.values()),
        "by_stage": stages,
    }
