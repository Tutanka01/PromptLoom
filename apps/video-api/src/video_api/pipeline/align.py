"""Word-level forced alignment of the per-scene TTS WAVs (Remotion engine).

The narration text is known exactly (segments_en.json), so this is *forced
alignment* (CTC), not transcription: torchaudio's MMS_FA bundle aligns the
normalized transcript onto each ``audio/en/<SceneKey>.wav`` and persists
word-level timestamps to ``audio/en/alignment.json``::

    {"Scene2_WhatEN": {"fp": "ab12...", "words": [{"w": "the", "start": 0.12, "end": 0.21}, ...]}}

Downstream, ``pipeline/beats.py`` matches blueprint beat anchors against these
words to derive per-scene visual cue ratios (props.cues). A segment that fails
to align is simply omitted — non-fatal: its scene falls back to the default
hardcoded item timings.

Alignment is cached alongside the TTS cache (pipeline/voice.py): each entry
records the segment's voice-cache fingerprint (``fp``), so a repair attempt
that leaves a segment's audio untouched reuses its words without reloading the
model for it.

torch/torchaudio already ship in the worker image (Chatterbox); the MMS_FA
weights (~300 MB) download once into the torch hub cache on first use.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# (start_seconds, end_seconds) per word, same order as the words handed in.
WordSpans = list[tuple[float, float]]
Aligner = Callable[[Path, list[str]], WordSpans]

_DIGIT_NAMES = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def _spell_number(piece: str) -> str:
    try:
        from num2words import num2words

        return num2words(int(piece))
    except Exception:
        return " ".join(_DIGIT_NAMES[d] for d in piece)


def normalize_words(text: str) -> list[str]:
    """Lowercase + restrict to the charset MMS_FA can align (a-z, apostrophe).

    Digits are expanded to spoken words so "64-bit" aligns as "sixty four bit"
    and "ext4" as "ext four". Punctuation splits words; empty pieces are dropped.
    The SAME normalization must be applied to beat anchors (pipeline/beats.py)
    so anchor matching compares like with like.
    """
    words: list[str] = []
    for raw in re.split(r"\s+", text.strip()):
        for piece in re.findall(r"[a-zA-Z']+|\d+", raw):
            if piece.isdigit():
                spoken = _spell_number(piece)
                words.extend(re.findall(r"[a-z']+", spoken.lower()))
            else:
                cleaned = piece.lower().strip("'")
                if cleaned:
                    words.append(cleaned)
    return words


def _build_mms_aligner(device: str) -> Aligner:
    """Load MMS_FA once and return a (wav_path, words) -> spans callable."""
    import torch
    import torchaudio
    from torchaudio.pipelines import MMS_FA as bundle

    resolved = device
    if device == "auto":
        resolved = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("align.model.load bundle=MMS_FA device=%s", resolved)
    model = bundle.get_model(with_star=False).to(resolved)
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()

    def align_one(wav_path: Path, words: list[str]) -> WordSpans:
        waveform, sr = torchaudio.load(str(wav_path))
        if waveform.size(0) > 1:
            waveform = waveform.mean(0, keepdim=True)
        if sr != bundle.sample_rate:
            waveform = torchaudio.functional.resample(waveform, sr, bundle.sample_rate)
        with torch.inference_mode():
            emission, _ = model(waveform.to(resolved))
            token_spans = aligner(emission[0], tokenizer(words))
        frame_seconds = waveform.size(1) / bundle.sample_rate / emission.size(1)
        return [
            (spans[0].start * frame_seconds, spans[-1].end * frame_seconds)
            for spans in token_spans
        ]

    return align_one


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def align_segments(video_dir: Path, device: str = "auto", aligner: Aligner | None = None) -> dict:
    """Align every segment WAV and write ``audio/en/alignment.json``.

    Segments whose voice-cache fingerprint matches an existing alignment entry
    are reused as-is (no model load needed when nothing changed). Per-segment
    failures are logged and skipped (the scene just keeps its default timings);
    only a missing segments_en.json is a hard error.
    """
    audio_dir = video_dir / "audio" / "en"
    segments = json.loads((video_dir / "segments_en.json").read_text(encoding="utf-8"))["segments"]
    voice_cache = _load_json(audio_dir / "cache.json")
    previous = _load_json(audio_dir / "alignment.json")

    alignment: dict[str, dict] = {}
    reused = 0
    for segment in segments:
        key = segment["key"]
        wav_path = audio_dir / f"{key}.wav"
        fingerprint = voice_cache.get(key, "")
        cached = previous.get(key)
        if (
            cached
            and fingerprint
            and cached.get("fp") == fingerprint
            and cached.get("words")
        ):
            alignment[key] = cached
            reused += 1
            continue
        try:
            words = normalize_words(segment["text"])
            if not words or not wav_path.exists():
                logger.warning("align.segment_skipped key=%s wav_exists=%s", key, wav_path.exists())
                continue
            if aligner is None:
                aligner = _build_mms_aligner(device)
            spans = aligner(wav_path, words)
            alignment[key] = {
                "fp": fingerprint,
                "words": [
                    {"w": word, "start": round(start, 3), "end": round(end, 3)}
                    for word, (start, end) in zip(words, spans)
                ],
            }
        except Exception as exc:
            logger.warning("align.segment_failed key=%s error=%s", key, exc)

    out_path = audio_dir / "alignment.json"
    out_path.write_text(json.dumps(alignment, indent=2) + "\n", encoding="utf-8")
    logger.info(
        "align.done segments=%d aligned=%d reused=%d path=%s",
        len(segments),
        len(alignment),
        reused,
        out_path,
    )
    return alignment
