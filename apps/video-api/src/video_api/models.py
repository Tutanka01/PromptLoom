from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    theme: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language: Mapped[str] = mapped_column(String(12), nullable=False, default="en")
    # Multi-language batches: sibling jobs that share one prompt produce the same
    # video translated into several languages. They share a batch_id; exactly one
    # job per batch is the primary (it generates the master blueprint). The
    # secondaries translate that master into their own language. NULL batch_id =
    # an ordinary single-language job.
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_profile: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Versioned JSON (stored as text for SQLite/Postgres portability) containing
    # per-job render engine, research, asset, caption and delivery policy.
    production_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Repair loop visibility. `attempt_number` is 0 for the first run, then
    # increments each time the pipeline retries after a MotionQualityError /
    # VisualReviewError / render failure. `max_attempts` is the ceiling (see
    # settings.max_repair_attempts + 1). `last_repair_reason` is populated on
    # the second and subsequent attempts with the human-readable message from
    # the exception that triggered the retry — surfaced to the Studio so a user
    # who sees a job take a strange path knows why.
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_repair_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_dir: Mapped[str] = mapped_column(Text, nullable=False)
    final_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
