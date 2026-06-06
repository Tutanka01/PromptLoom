from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from video_api.config import get_settings
from video_api.models import Base


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_compat_columns()


def _ensure_compat_columns() -> None:
    inspector = inspect(engine)
    if "video_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("video_jobs")}
    if "target_duration_seconds" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE video_jobs ADD COLUMN target_duration_seconds INTEGER"))


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
