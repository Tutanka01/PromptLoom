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


def _loudnorm_stderr(integrated: float, true_peak: float) -> str:
    # Mirrors the JSON block ffmpeg's `loudnorm=print_format=json` prints to stderr.
    return (
        "[Parsed_loudnorm_0 @ 0x0] \n"
        "{\n"
        f'\t"input_i" : "{integrated:.2f}",\n'
        f'\t"input_tp" : "{true_peak:.2f}",\n'
        '\t"input_lra" : "5.00",\n'
        '\t"input_thresh" : "-24.00",\n'
        '\t"output_i" : "-14.00",\n'
        '\t"normalization_type" : "dynamic",\n'
        '\t"target_offset" : "0.00"\n'
        "}\n"
    )


class FakeRunner:
    def __init__(
        self,
        duration: float,
        freeze_segments: list[tuple[float, float]] | None = None,
        audio: dict[str, float] | None = None,
    ):
        self.duration = duration
        self.freeze_segments = freeze_segments or []
        # Default to clean, on-target audio so freeze-focused tests don't trip the QC.
        self.audio = {"integrated": -14.0, "true_peak": -1.5} if audio is None else audio

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
        if args[0] == "ffmpeg" and "-af" in args:
            # Loudness measurement (`-af loudnorm=print_format=json ... -f null -`).
            # Output goes to stdout ("-"); it must NOT create a file.
            if not self.audio:
                return CompletedProcess(args, 0, stdout="", stderr="")
            stderr = _loudnorm_stderr(self.audio["integrated"], self.audio["true_peak"])
            return CompletedProcess(args, 0, stdout="", stderr=stderr)
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


def test_freeze_is_warning_not_failure_by_default(tmp_path: Path) -> None:
    # Default policy: a freeze does not fail the job. The MP4 is delivered and the
    # problem is surfaced in quality_warnings so the user can watch and judge.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    report = verify_mp4(
        video,
        FakeRunner(duration=120, freeze_segments=[(40.0, 25.0)]),
        final_quality=True,
        report_dir=tmp_path / "report",
        min_duration_seconds=30,
    )

    assert len(report["quality_warnings"]) == 1
    assert "single static stretch lasts 25" in report["quality_warnings"][0]


def test_single_dead_scene_is_rejected_when_fatal(tmp_path: Path) -> None:
    # With freeze_fatal=True the longest-stretch rule fails the job, naming the freeze.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    with pytest.raises(RuntimeError, match="single static stretch lasts 25"):
        verify_mp4(
            video,
            FakeRunner(duration=120, freeze_segments=[(40.0, 25.0)]),
            final_quality=True,
            report_dir=tmp_path / "report",
            min_duration_seconds=30,
            freeze_fatal=True,
        )


def test_cumulative_freeze_over_ratio_is_rejected_when_fatal(tmp_path: Path) -> None:
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
            freeze_fatal=True,
        )


# --------------------------------------------------------------------------- #
# Audio QC (loudness + true peak)
# --------------------------------------------------------------------------- #
def test_audio_qc_records_stats_for_clean_audio(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    report = verify_mp4(
        video,
        FakeRunner(duration=120, audio={"integrated": -14.0, "true_peak": -1.5}),
        final_quality=True,
        report_dir=tmp_path / "report",
        min_duration_seconds=30,
    )

    assert report["audio"]["integrated_lufs"] == -14.0
    assert report["audio"]["true_peak_dbtp"] == -1.5
    assert (tmp_path / "report" / "audio_stats.json").exists()
    assert report["quality_warnings"] == []


def test_audio_qc_warns_on_clipping_by_default(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    report = verify_mp4(
        video,
        FakeRunner(duration=120, audio={"integrated": -14.0, "true_peak": 0.8}),
        final_quality=True,
        report_dir=tmp_path / "report",
        min_duration_seconds=30,
    )

    assert any("clipping" in w for w in report["quality_warnings"])


def test_audio_qc_clipping_is_fatal_when_enabled(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    with pytest.raises(RuntimeError, match="clipping"):
        verify_mp4(
            video,
            FakeRunner(duration=120, audio={"integrated": -14.0, "true_peak": 0.8}),
            final_quality=True,
            report_dir=tmp_path / "report",
            min_duration_seconds=30,
            audio_qc_fatal=True,
        )


def test_audio_qc_warns_on_near_silence(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    report = verify_mp4(
        video,
        FakeRunner(duration=120, audio={"integrated": -60.0, "true_peak": -40.0}),
        final_quality=True,
        report_dir=tmp_path / "report",
        min_duration_seconds=30,
    )

    assert any("near-silence" in w for w in report["quality_warnings"])


def test_audio_qc_skipped_on_low_quality_pass(tmp_path: Path) -> None:
    # The low-quality verify is the cheap ffprobe contract only — no loudness pass,
    # so no audio_stats are produced and nothing writes to a "-" stdout sink.
    video = tmp_path / "video.mp4"
    video.write_bytes(b"mp4")

    report = verify_mp4(
        video,
        FakeRunner(duration=120),
        final_quality=False,
        report_dir=tmp_path / "report",
        min_duration_seconds=30,
    )

    assert report["audio"] is None
