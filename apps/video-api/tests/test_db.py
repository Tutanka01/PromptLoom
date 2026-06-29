from __future__ import annotations

import pytest

from video_api import db


def test_init_db_retries_transient_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    def flaky_create_all(*, bind) -> None:  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary failure")

    monkeypatch.setattr(db.Base.metadata, "create_all", flaky_create_all)
    monkeypatch.setattr(db, "_ensure_compat_columns", lambda: None)
    monkeypatch.setattr(db.time, "sleep", lambda _: None)

    db.init_db(max_attempts=2, delay_seconds=0.0)

    assert calls["count"] == 2
