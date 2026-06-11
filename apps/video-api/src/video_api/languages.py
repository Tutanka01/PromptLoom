from __future__ import annotations

import re


# ISO-ish language codes for European deployment. The list intentionally covers
# EU languages plus common European non-EU languages so the API can accept a
# broad "spoken in Europe" request while still rejecting typos early.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "de": "German",
    "nl": "Dutch",
    "ro": "Romanian",
    "pl": "Polish",
    "cs": "Czech",
    "sk": "Slovak",
    "sl": "Slovenian",
    "hr": "Croatian",
    "hu": "Hungarian",
    "bg": "Bulgarian",
    "el": "Greek",
    "da": "Danish",
    "sv": "Swedish",
    "no": "Norwegian",
    "nb": "Norwegian Bokmal",
    "nn": "Norwegian Nynorsk",
    "fi": "Finnish",
    "et": "Estonian",
    "lv": "Latvian",
    "lt": "Lithuanian",
    "ga": "Irish",
    "mt": "Maltese",
    "is": "Icelandic",
    "sq": "Albanian",
    "mk": "Macedonian",
    "sr": "Serbian",
    "bs": "Bosnian",
    "uk": "Ukrainian",
    "ru": "Russian",
    "ca": "Catalan",
    "eu": "Basque",
    "gl": "Galician",
    "cy": "Welsh",
    "tr": "Turkish",
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
    "ukrainian": "uk",
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
    if code in {"nor"}:
        code = "no"
    if code not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise ValueError(f"unsupported language {value!r}; supported codes: {supported}")
    return code


def language_name(code: str | None) -> str:
    normalized = normalize_language(code)
    return SUPPORTED_LANGUAGES[normalized]
