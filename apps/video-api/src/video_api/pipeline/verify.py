from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from video_api.pipeline.commands import CommandRunner


logger = logging.getLogger(__name__)


def _frame_rate(value: str) -> float:
    if "/" in value:
        num, den = value.split("/", 1)
        return float(num) / float(den)
    return float(value)


def extract_frame(
    runner: CommandRunner,
    video_path: Path,
    timestamp: float,
    out_path: Path,
) -> Path:
    """Extract a single frame from *video_path* at *timestamp* seconds into *out_path*.

    Raises RuntimeError if the output file is missing or empty after extraction.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    runner.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(out_path),
        ],
        cwd=video_path.parent,
        log_name=f"snapshot-{video_path.stem}-{out_path.stem}.log",
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"snapshot extraction failed: {out_path}")
    return out_path


def verify_mp4(
    video_path: Path,
    runner: CommandRunner,
    final_quality: bool,
    report_dir: Path,
    min_duration_seconds: int | None = None,
    max_freeze_ratio: float = 0.5,
    freeze_floor_seconds: float = 30.0,
    max_single_freeze_seconds: float = 12.0,
    freeze_fatal: bool = False,
) -> dict:
    report_dir.mkdir(parents=True, exist_ok=True)
    quality_warnings: list[str] = []
    logger.info("verify.start video=%s final_quality=%s report_dir=%s", video_path, final_quality, report_dir)
    ffprobe = runner.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_streams",
            "-of",
            "json",
            str(video_path),
        ],
        cwd=video_path.parent,
        log_name=f"ffprobe-{video_path.stem}.log",
    )
    probe = json.loads(ffprobe.stdout)
    streams = probe.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        raise RuntimeError("ffprobe found no video stream")
    if not audio_streams:
        raise RuntimeError("ffprobe found no audio stream")
    video = video_streams[0]
    duration = float(probe.get("format", {}).get("duration", 0))
    minimum_duration = min_duration_seconds if min_duration_seconds is not None else 20
    if duration < minimum_duration:
        raise RuntimeError(f"video is too short: {duration:.1f}s below minimum {minimum_duration}s")
    if final_quality:
        if video.get("width") != 1920 or video.get("height") != 1080:
            raise RuntimeError("final video must be 1920x1080")
        fps = _frame_rate(video.get("r_frame_rate", "0/1"))
        if abs(fps - 60.0) > 0.01:
            raise RuntimeError("final video must be 60 fps")
    logger.info(
        "verify.probe.done video=%s duration=%.3fs width=%s height=%s fps=%s audio_codec=%s",
        video_path,
        duration,
        video.get("width"),
        video.get("height"),
        video.get("r_frame_rate"),
        audio_streams[0].get("codec_name"),
    )

    freeze = runner.run(
        ["ffmpeg", "-i", str(video_path), "-vf", "freezedetect=n=-60dB:d=3", "-an", "-f", "null", "-"],
        cwd=video_path.parent,
        log_name=f"freezedetect-{video_path.stem}.log",
    )
    freeze_starts = [float(match) for match in re.findall(r"freeze_start: ([0-9.]+)", freeze.stderr)]
    freeze_durations = [float(match) for match in re.findall(r"freeze_duration: ([0-9.]+)", freeze.stderr)]
    segments = [
        {"start": round(start, 3), "duration": round(dur, 3)}
        for start, dur in zip(freeze_starts, freeze_durations)
    ]
    longest = max(freeze_durations) if freeze_durations else 0.0
    freeze_summary = {
        "count": len(freeze_durations),
        "total": round(sum(freeze_durations), 3),
        "average": round(sum(freeze_durations) / len(freeze_durations), 3) if freeze_durations else 0,
        "longest": round(longest, 3),
        "segments": segments,
    }
    # Persist the breakdown before the gate so a failed job still exposes *why*.
    (report_dir / "freeze.json").write_text(json.dumps(freeze_summary, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "verify.freezedetect.done video=%s freezes=%d freeze_total=%.3fs freeze_avg=%.3fs freeze_longest=%.3fs",
        video_path,
        freeze_summary["count"],
        freeze_summary["total"],
        freeze_summary["average"],
        freeze_summary["longest"],
    )
    if final_quality:
        total_allowed = max(freeze_floor_seconds, duration * max_freeze_ratio)
        reasons: list[str] = []
        if freeze_summary["total"] > total_allowed:
            reasons.append(
                f"cumulative frozen time {freeze_summary['total']:.1f}s exceeds "
                f"{total_allowed:.1f}s allowed (ratio={max_freeze_ratio}, floor={freeze_floor_seconds:.0f}s)"
            )
        if longest > max_single_freeze_seconds:
            where = next((s["start"] for s in segments if s["duration"] == round(longest, 3)), None)
            at = f" starting near {where:.1f}s" if where is not None else ""
            reasons.append(
                f"a single static stretch lasts {longest:.1f}s{at}, over the "
                f"{max_single_freeze_seconds:.0f}s cap — likely a dead scene, not a held formula"
            )
        if reasons:
            message = (
                "too much frozen video detected: "
                + "; ".join(reasons)
                + f" [freezes={freeze_summary['count']}, total={freeze_summary['total']:.1f}s, "
                f"longest={longest:.1f}s, duration={duration:.1f}s; see freeze.json]"
            )
            if freeze_fatal:
                raise RuntimeError(message)
            quality_warnings.append(message)
            logger.warning("verify.freeze.warning video=%s %s", video_path, message)

    snapshot_dir = report_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    timestamps = sorted(
        set(
            [
                10.0,
                max(1.0, duration * 0.25),
                max(1.0, duration * 0.5),
                max(1.0, duration * 0.75),
                max(1.0, duration * 0.9),
            ]
        )
    )
    snapshots: list[str] = []
    for index, timestamp in enumerate(timestamps, start=1):
        if timestamp >= duration:
            continue
        out = snapshot_dir / f"check_{index:02d}_{int(timestamp):04d}.png"
        extract_frame(runner, video_path, timestamp, out)
        snapshots.append(str(out))
        logger.info("verify.snapshot.done video=%s timestamp=%.3fs path=%s", video_path, timestamp, out)

    report = {
        "video": str(video_path),
        "duration": duration,
        "minimum_duration": minimum_duration,
        "format": probe.get("format", {}),
        "video_stream": video_streams[0],
        "audio_stream": audio_streams[0],
        "freezedetect": freeze_summary,
        "snapshots": snapshots,
        "quality_warnings": quality_warnings,
    }
    logger.info(
        "verify.done video=%s snapshots=%d quality_warnings=%d",
        video_path,
        len(snapshots),
        len(quality_warnings),
    )
    return report
