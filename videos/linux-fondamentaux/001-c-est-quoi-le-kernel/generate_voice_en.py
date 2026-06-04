#!/usr/bin/env python3
"""Generate synchronized English scene voiceover files."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SEGMENTS_FILE = ROOT / "segments_en.json"
OUT_DIR = ROOT / "audio" / "en"


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            str(path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def write_mp3_from_wav(wav_path: Path, mp3_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg is required to encode MP3.")
    run(["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3_path)])


def should_skip_existing(key: str, force: bool) -> bool:
    wav_path = OUT_DIR / f"{key}.wav"
    mp3_path = OUT_DIR / f"{key}.mp3"
    if force or not wav_path.exists():
        return False
    if not mp3_path.exists():
        write_mp3_from_wav(wav_path, mp3_path)
    print(f"Reusing existing audio for {key}")
    return True


def generate_kokoro(segments: list[dict], voice: str, speed: float, force: bool) -> None:
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code="a")
    for segment in segments:
        key = segment["key"]
        text = segment["text"]
        if should_skip_existing(key, force):
            continue
        wav_path = OUT_DIR / f"{key}.wav"
        mp3_path = OUT_DIR / f"{key}.mp3"
        print(f"Generating Kokoro segment {key}")
        chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed, split_pattern=r"\n+"):
            chunks.append(audio)
        if not chunks:
            raise RuntimeError(f"No audio generated for {key}")
        audio = np.concatenate(chunks)
        sf.write(str(wav_path), audio, 24000)
        write_mp3_from_wav(wav_path, mp3_path)


def generate_chatterbox_turbo(segments: list[dict], exaggeration: float, cfg_weight: float, temperature: float, force: bool) -> None:
    import torch
    import torchaudio as ta
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading Chatterbox Turbo on {device}")
    model = ChatterboxTurboTTS.from_pretrained(device=device)
    for segment in segments:
        key = segment["key"]
        text = segment["text"]
        if should_skip_existing(key, force):
            continue
        wav_path = OUT_DIR / f"{key}.wav"
        mp3_path = OUT_DIR / f"{key}.mp3"
        print(f"Generating Chatterbox Turbo segment {key}")
        wav = model.generate(
            text,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
        )
        ta.save(str(wav_path), wav, model.sr)
        write_mp3_from_wav(wav_path, mp3_path)


def generate_chatterbox(segments: list[dict], exaggeration: float, cfg_weight: float, temperature: float, force: bool) -> None:
    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"Loading Chatterbox on {device}")
    model = ChatterboxTTS.from_pretrained(device=device)
    for segment in segments:
        key = segment["key"]
        text = segment["text"]
        if should_skip_existing(key, force):
            continue
        wav_path = OUT_DIR / f"{key}.wav"
        mp3_path = OUT_DIR / f"{key}.mp3"
        print(f"Generating Chatterbox segment {key}")
        wav = model.generate(
            text,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
        )
        ta.save(str(wav_path), wav, model.sr)
        write_mp3_from_wav(wav_path, mp3_path)


def write_duration_files(segments: list[dict], tail_padding: float) -> None:
    durations = {}
    concat_lines = []
    for segment in segments:
        key = segment["key"]
        wav_path = OUT_DIR / f"{key}.wav"
        mp3_path = OUT_DIR / f"{key}.mp3"
        padded_wav_path = OUT_DIR / f"{key}.padded.wav"
        if not wav_path.exists():
            raise FileNotFoundError(wav_path)
        if not mp3_path.exists():
            write_mp3_from_wav(wav_path, mp3_path)
        target_duration = round(ffprobe_duration(wav_path) + tail_padding, 3)
        durations[key] = target_duration
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(wav_path),
                "-af",
                "apad",
                "-t",
                f"{target_duration:.3f}",
                "-ar",
                "24000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(padded_wav_path),
            ]
        )
        concat_lines.append(f"file '{padded_wav_path.resolve()}'")

    (OUT_DIR / "durations.json").write_text(json.dumps(durations, indent=2) + "\n", encoding="utf-8")
    (OUT_DIR / "audio_concat.txt").write_text("\n".join(concat_lines) + "\n", encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(OUT_DIR / "audio_concat.txt"),
            "-c:a",
            "pcm_s16le",
            str(OUT_DIR / "voiceover_en.wav"),
        ]
    )
    write_mp3_from_wav(OUT_DIR / "voiceover_en.wav", OUT_DIR / "voiceover_en.mp3")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["kokoro", "chatterbox", "chatterbox-turbo"], default="chatterbox")
    parser.add_argument("--kokoro-voice", default="af_bella")
    parser.add_argument("--kokoro-speed", type=float, default=0.92)
    parser.add_argument("--exaggeration", type=float, default=0.45)
    parser.add_argument("--cfg-weight", type=float, default=0.55)
    parser.add_argument("--temperature", type=float, default=0.55)
    parser.add_argument("--tail-padding", type=float, default=0.35)
    parser.add_argument("--force", action="store_true", help="Regenerate audio even when a segment WAV already exists.")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = json.loads(SEGMENTS_FILE.read_text(encoding="utf-8"))["segments"]

    if args.engine == "kokoro":
        generate_kokoro(segments, args.kokoro_voice, args.kokoro_speed, args.force)
    elif args.engine == "chatterbox":
        generate_chatterbox(segments, args.exaggeration, args.cfg_weight, args.temperature, args.force)
    else:
        generate_chatterbox_turbo(segments, args.exaggeration, args.cfg_weight, args.temperature, args.force)

    write_duration_files(segments, args.tail_padding)
    print(f"Wrote {OUT_DIR / 'voiceover_en.mp3'}")


if __name__ == "__main__":
    main()
