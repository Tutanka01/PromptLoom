from __future__ import annotations

import re


# ISO-ish language codes supported by MOSS-TTS v1.5. The video API can receive a
# prompt in any language, but the requested output language must be one the TTS
# engine can actually speak reliably.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "zh": "Chinese",
    "yue": "Cantonese",
    "en": "English",
    "ar": "Arabic",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "nl": "Dutch",
    "es": "Spanish",
    "fr": "French",
    "fi": "Finnish",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "hu": "Hungarian",
    "it": "Italian",
    "mk": "Macedonian",
    "ms": "Malay",
    "fa": "Persian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sw": "Swahili",
    "sv": "Swedish",
    "tl": "Tagalog",
    "th": "Thai",
    "tr": "Turkish",
    "vi": "Vietnamese",
}

# Languages written right-to-left. Their on-screen text must be laid out RTL:
# browsers/React default to LTR, which reverses the word order of a sentence
# split into several elements (word-by-word reveals, captions, label rows).
RTL_LANGUAGES: frozenset[str] = frozenset({"ar", "he", "fa"})

LANGUAGE_ALIASES = {
    "english": "en",
    "anglais": "en",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "spanish": "es",
    "espagnol": "es",
    "italian": "it",
    "italien": "it",
    "romanian": "ro",
    "roumain": "ro",
    "portuguese": "pt",
    "portugais": "pt",
    "german": "de",
    "allemand": "de",
    "dutch": "nl",
    "polish": "pl",
    "greek": "el",
    "swedish": "sv",
    "czech": "cs",
    "turkish": "tr",
}


def normalize_language(value: str | None) -> str:
    raw = (value or "en").strip()
    if not raw:
        return "en"
    lower = raw.lower().replace("_", "-")
    alias_key = re.sub(r"\s+", " ", lower).strip()
    if alias_key in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[alias_key]
    code = lower.split("-", 1)[0]
    if code not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise ValueError(f"unsupported language {value!r}; supported codes: {supported}")
    return code


def language_name(code: str | None) -> str:
    normalized = normalize_language(code)
    return SUPPORTED_LANGUAGES[normalized]


def text_direction(code: str | None) -> str:
    """CSS `dir` value ("ltr"/"rtl") for a language code.

    Drives the Remotion renderer's root direction so Arabic/Hebrew/Persian text
    keeps its reading order. Unknown codes degrade to "ltr" instead of raising:
    direction is a cosmetic hint, never a reason to fail a render.
    """
    try:
        normalized = normalize_language(code)
    except ValueError:
        return "ltr"
    return "rtl" if normalized in RTL_LANGUAGES else "ltr"
