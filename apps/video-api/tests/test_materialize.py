from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from video_api.config import Settings
from video_api.pipeline.llm import fake_blueprint
from video_api.pipeline.materialize import Materializer
from video_api.pipeline.materialize import _assemble_script
from video_api.pipeline.materialize import slugify


def test_assemble_script_two_pass_loudnorm() -> None:
    script = _assemble_script(fake_blueprint("Explain derivatives", "math"))

    # Two-pass apply filter: measured_* values fed back with linear gain.
    for token in (
        "measured_I=",
        "measured_TP=",
        "measured_LRA=",
        "measured_thresh=",
        "offset=",
        "linear=true",
    ):
        assert token in script, token
    # Measure pass emits a JSON report parsed by python3 (jq is not guaranteed).
    assert "print_format=json" in script
    assert "parse_loudnorm" in script
    assert "python3 -c" in script
    # Robust fallback to the single-pass filter on any measure/parse failure.
    assert "LOUDNORM_SINGLE=" in script
    assert "using single-pass" in script
    # apad/-shortest freezedetect rationale preserved.
    assert "apad" in script
    assert "-shortest" in script


def test_assemble_script_masters_voice_before_loudnorm() -> None:
    script = _assemble_script(fake_blueprint("Explain derivatives", "math"))

    # The broadcast chain (high-pass, de-esser, gentle compression) is on by
    # default and overridable for manual tuning.
    assert 'VOICE_MASTERING_ENABLED="${VOICE_MASTERING_ENABLED:-1}"' in script
    for stage in ("highpass=f=80", "deesser=", "acompressor="):
        assert stage in script, stage
    # The mastering prefix feeds BOTH the loudnorm measure pass and the final
    # graph, so the measurement matches what ships.
    assert '-af "${MASTER_PREFIX}${LOUDNORM_SINGLE}:print_format=json"' in script
    assert 'VOICE_CHAIN="${MASTER_PREFIX}${MEASURED},apad"' in script
    assert 'VOICE_CHAIN="${MASTER_PREFIX}${LOUDNORM_SINGLE},apad"' in script


def test_assemble_script_is_voice_only() -> None:
    # The soundtrack is voice-only by design (user decision, 2026-07): no music
    # bed, no ducking, no SFX inputs.
    script = _assemble_script(fake_blueprint("Explain derivatives", "math"))
    for forbidden in ("MUSIC", "sidechaincompress", "amix", "-stream_loop"):
        assert forbidden not in script, forbidden


def test_assemble_script_is_valid_bash() -> None:
    if shutil.which("bash") is None:  # pragma: no cover - bash always present in CI
        pytest.skip("bash not available")
    script = _assemble_script(fake_blueprint("Explain derivatives", "math"))
    result = subprocess.run(
        ["bash", "-n"],
        input=script,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_slugify_returns_kebab_case() -> None:
    assert slugify("Math / Derivatives!") == "math-derivatives"
    assert slugify("Biology: Cell Energy!") == "biology-cell-energy"


def test_materialized_style_connect_accepts_points(tmp_path) -> None:
    settings = Settings(repo_root=Path(__file__).resolve().parents[3])
    video_dir = Materializer(settings).materialize(
        fake_blueprint("Explain Markov chains", "markov-chains", target_duration_seconds=75),
        tmp_path,
    )

    style_text = next(video_dir.glob("*_style.py")).read_text(encoding="utf-8")

    assert "def _anchor_point" in style_text
    assert "hasattr(value, \"get_boundary_point\")" in style_text
