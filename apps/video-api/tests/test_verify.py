from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from video_api.pipeline.verify import verify_mp4


class FakeRunner:
    def __init__(self, duration: float):
        self.duration = duration

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
            return CompletedProcess(args, 0, stdout="", stderr="")
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
