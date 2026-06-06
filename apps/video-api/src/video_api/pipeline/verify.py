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


def verify_mp4(
    video_path: Path,
    runner: CommandRunner,
    final_quality: bool,
    report_dir: Path,
    min_duration_seconds: int | None = None,
) -> dict:
    report_dir.mkdir(parents=True, exist_ok=True)
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
    freeze_durations = [float(match) for match in re.findall(r"freeze_duration: ([0-9.]+)", freeze.stderr)]
    freeze_summary = {
        "count": len(freeze_durations),
        "total": round(sum(freeze_durations), 3),
        "average": round(sum(freeze_durations) / len(freeze_durations), 3) if freeze_durations else 0,
    }
    if final_quality and freeze_summary["total"] > max(30.0, duration * 0.25):
        raise RuntimeError("too much frozen video detected")
    logger.info(
        "verify.freezedetect.done video=%s freezes=%d freeze_total=%.3fs freeze_avg=%.3fs",
        video_path,
        freeze_summary["count"],
        freeze_summary["total"],
        freeze_summary["average"],
    )

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
                str(out),
            ],
            cwd=video_path.parent,
            log_name=f"snapshot-{video_path.stem}-{index}.log",
        )
        if not out.exists() or out.stat().st_size == 0:
            raise RuntimeError(f"snapshot extraction failed: {out}")
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
    }
    logger.info("verify.done video=%s snapshots=%d", video_path, len(snapshots))
    return report
