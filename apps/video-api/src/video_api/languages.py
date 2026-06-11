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
