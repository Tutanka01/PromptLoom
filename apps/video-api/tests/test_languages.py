from __future__ import annotations

import pytest

from video_api.languages import normalize_language, text_direction


@pytest.mark.parametrize("code", ["ar", "AR", "ar-SA", "he", "fa"])
def test_text_direction_is_rtl_for_rtl_languages(code: str) -> None:
    assert text_direction(code) == "rtl"


@pytest.mark.parametrize("code", ["en", "fr", "de", "zh", "ru", None, "", "not-a-language"])
def test_text_direction_is_ltr_for_everything_else(code: str | None) -> None:
    # Unknown codes must not raise: direction is a rendering hint.
    assert text_direction(code) == "ltr"


def test_normalize_language_still_rejects_unknown_codes() -> None:
    with pytest.raises(ValueError):
        normalize_language("not-a-language")
