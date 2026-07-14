from __future__ import annotations

from tts_server.engine import estimate_new_tokens


def test_short_text_gets_the_floor() -> None:
    assert estimate_new_tokens("Hi.", ceiling=4096) == 256


def test_estimate_scales_with_length_and_stays_below_ceiling() -> None:
    short = estimate_new_tokens("word " * 20, ceiling=4096)
    long = estimate_new_tokens("word " * 200, ceiling=4096)
    assert 256 < short < long <= 4096


def test_estimate_is_capped_by_the_ceiling() -> None:
    # A very long segment can never exceed the configured hard cap.
    assert estimate_new_tokens("x" * 100_000, ceiling=1024) == 1024


def test_short_text_never_exceeds_a_low_ceiling() -> None:
    # The floor must not override an explicitly lower hard cap.
    assert estimate_new_tokens("Hi.", ceiling=128) == 128
