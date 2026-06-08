from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from video_api.pipeline.verify import verify_mp4


def _freeze_stderr(segments: list[tuple[float, float]]) -> str:
    lines = []
    for start, duration in segments:
        lines.append(f"[freezedetect @ 0x0] lavfi.freezedetect.freeze_start: {start}")
        lines.append(f"[freezedetect @ 0x0] lavfi.freezedetect.freeze_duration: {duration}")
        lines.append(f"[freezedetect @ 0x0] lavfi.freezedetect.freeze_end: {start + duration}")
    return "\n".join(lines)


class FakeRunner:
    def __init__(self, duration: float, freeze_segments: list[tuple[float, float]] | None = None):
        self.duration = duration
        self.freeze_segments = freeze_segments or []

    def run(self, args: list[str], cwd: Path, log_name: str, env: dict[str, str] | None = None):
        if args[0] == "ffprobe":
            return CompletedProcess(
                args,
                0,
                stdout=json.dumps(
                    {
                        "format": {"duration": str(self.duration), "size": "12345"},
                        "streams": [
                            {
                                "codec_type": "video",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "60/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                    }
                ),
                stderr="",
            )
        if args[0] == "ffmpeg" and "-vf" in args:
            return CompletedProcess(args, 0, stdout="", stderr=_freeze_stderr(self.freeze_segments))
        if args[0] == "ffmpeg":
            Path(args[-1]).write_bytes(b"png")
            return CompletedProcess(args, 0, stdout="", stderr="")
        raise AssertionError(args)


def test_final_verification_rejects_video_below_minimum_duration(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    with pytest.raises(RuntimeError, match="video is too short"):
        verify_mp4(
            video,
            FakeRunner(duration=120),
            final_quality=True,
            report_dir=tmp_path / "report",
            min_duration_seconds=180,
        )


def test_final_verification_records_minimum_duration(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    report = verify_mp4(
        video,
        FakeRunner(duration=181),
        final_quality=True,
        report_dir=tmp_path / "report",
        min_duration_seconds=180,
    )

    assert report["minimum_duration"] == 180
    assert len(report["snapshots"]) == 5


def test_held_formulas_pass_under_cumulative_tolerance(tmp_path: Path) -> None:
    # Six legitimate ~6s formula holds (36s total) in a 120s video: total < 50% and no
    # single stretch over the 12s cap -> the video passes.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")
    segments = [(float(i * 18), 6.0) for i in range(6)]

    report = verify_mp4(
        video,
        FakeRunner(duration=120, freeze_segments=segments),
        final_quality=True,
        report_dir=tmp_path / "report",
        min_duration_seconds=30,
    )

    assert report["freezedetect"]["count"] == 6
    assert report["freezedetect"]["longest"] == 6.0
    assert (tmp_path / "report" / "freeze.json").exists()


def test_single_dead_scene_is_rejected_with_details(tmp_path: Path) -> None:
    # One 25s dead stretch: under cumulative tolerance but a clear dead scene -> reject,
    # and the error must name the longest freeze so the failure is diagnosable.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    with pytest.raises(RuntimeError, match="single static stretch lasts 25"):
        verify_mp4(
            video,
            FakeRunner(duration=120, freeze_segments=[(40.0, 25.0)]),
            final_quality=True,
            report_dir=tmp_path / "report",
            min_duration_seconds=30,
        )


def test_cumulative_freeze_over_ratio_is_rejected(tmp_path: Path) -> None:
    # Many short holds (each under the single cap) that together exceed the ratio.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")
    segments = [(float(i * 11), 11.0) for i in range(8)]  # 88s of 120s

    with pytest.raises(RuntimeError, match="cumulative frozen time"):
        verify_mp4(
            video,
            FakeRunner(duration=120, freeze_segments=segments),
            final_quality=True,
            report_dir=tmp_path / "report",
            min_duration_seconds=30,
            max_single_freeze_seconds=12.0,
        )
