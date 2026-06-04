#!/usr/bin/env python3
"""Generate local voiceover audio for the kernel video."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEXT_FILE = ROOT / "voiceover.txt"
AUDIO_DIR = ROOT / "audio"


def run(command: list[str]) -> None:
    print("+", " ".join(command))
    subprocess.run(command, check=True)


def generate_macos(voice: str, rate: int) -> Path:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    aiff_path = AUDIO_DIR / "voiceover.aiff"
    mp3_path = AUDIO_DIR / "voiceover.mp3"

    run(["say", "-v", voice, "-r", str(rate), "-f", str(TEXT_FILE), "-o", str(aiff_path)])
    if aiff_path.stat().st_size <= 4096:
        raise SystemExit(
            "macOS generated an empty audio file. "
            "Run this command outside the sandbox or use --engine piper."
        )

    if shutil.which("ffmpeg"):
        run(["ffmpeg", "-y", "-i", str(aiff_path), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3_path)])
        return mp3_path

    if shutil.which("afconvert"):
        try:
            run(["afconvert", str(aiff_path), str(mp3_path), "-f", "MPG3", "-d", ".mp3"])
            return mp3_path
        except subprocess.CalledProcessError:
            print("MP3 conversion failed with afconvert; keeping AIFF output.")

    return aiff_path


def generate_piper(model: str, output_format: str) -> Path:
    if not shutil.which("piper"):
        raise SystemExit("piper is not installed or not on PATH.")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    wav_path = AUDIO_DIR / "voiceover.wav"
    mp3_path = AUDIO_DIR / "voiceover.mp3"

    text = TEXT_FILE.read_text(encoding="utf-8")
    command = ["piper", "--model", model, "--output_file", str(wav_path)]
    print("+", " ".join(command))
    subprocess.run(command, input=text, text=True, check=True)

    if output_format == "wav":
        return wav_path

    if shutil.which("ffmpeg"):
        run(["ffmpeg", "-y", "-i", str(wav_path), "-codec:a", "libmp3lame", "-q:a", "2", str(mp3_path)])
        return mp3_path

    if shutil.which("afconvert"):
        run(["afconvert", str(wav_path), str(mp3_path), "-f", "MPG3", "-d", ".mp3"])
        return mp3_path

    print("No MP3 encoder found; keeping WAV output.")
    return wav_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["macos", "piper"], default="macos")
    parser.add_argument("--voice", default="Thomas")
    parser.add_argument("--rate", type=int, default=155)
    parser.add_argument("--piper-model", default="")
    parser.add_argument("--output-format", choices=["mp3", "wav"], default="mp3")
    args = parser.parse_args()

    if args.engine == "macos":
        output = generate_macos(args.voice, args.rate)
    else:
        if not args.piper_model:
            raise SystemExit("--piper-model is required for --engine piper")
        output = generate_piper(args.piper_model, args.output_format)

    print(f"Voiceover written to {output}")


if __name__ == "__main__":
    main()
