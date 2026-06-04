#!/usr/bin/env python3
"""Generate a short Darijat TTS sample at the repository root."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_TEXT_FILE = ROOT / "darijat_sample_text.txt"
DEFAULT_OUTPUT = ROOT / "darijat_sample.mp3"
EXTERNAL_API_URL = "https://tts.darijat.com/api/v1/external/generate-audio"
SYNTHESIZE_API_URL = "https://tts.darijat.com/api/v1/tts/synthesize"
VOICES_URL = "https://tts.darijat.com/api/v1/voices"
DEFAULT_VOICE = "صوت دارجة مغربي لليوتيوب بالذكاء الاصطناعي"
DEFAULT_STYLE = (
    "اقرأ النص بالعربية الفصحى الواضحة، بصوت يوتيوبر تقني محترف، مع لمسة مغربية خفيفة في الأداء فقط. "
    "النبرة حماسية في البداية، ثم تعليمية وهادئة، مع ابتسامة خفيفة، "
    "وقفات قصيرة بعد الجمل المهمة، وتأكيد بسيط على كلمات: نواة لينكس، المعالج، الذاكرة، العتاد."
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


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


def extract_audio_url(data: dict) -> str:
    candidates = [
        data.get("url"),
        data.get("audio"),
        data.get("audio_url"),
        data.get("audioUrl"),
        data.get("file"),
        data.get("download_url"),
    ]
    nested_data = data.get("data")
    if isinstance(nested_data, dict):
        candidates.extend(
            [
                nested_data.get("url"),
                nested_data.get("audio"),
                nested_data.get("audio_url"),
                nested_data.get("audioUrl"),
                nested_data.get("file"),
                nested_data.get("download_url"),
            ]
        )
    for candidate in candidates:
        if candidate:
            return str(candidate)
    raise SystemExit(f"Darijat API response has no audio URL: {json.dumps(data, ensure_ascii=False)}")


def post_json(token: str, url: str, payload: dict, retries: int, retry_delay: float) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 503 and attempt < retries:
                print(f"Darijat API is busy; retrying in {retry_delay:.1f}s...")
                time.sleep(retry_delay)
                continue
            raise SystemExit(f"Darijat API returned HTTP {exc.code}: {body}") from exc

    if not data.get("success"):
        raise SystemExit(f"Darijat API did not return success: {json.dumps(data, ensure_ascii=False)}")
    return data


def request_external_audio_url(
    token: str,
    text: str,
    voice: str,
    style: str,
    human_simulation: bool,
    retries: int,
    retry_delay: float,
) -> str:
    data = post_json(
        token,
        EXTERNAL_API_URL,
        {
            "text": text,
            "voice_name": voice,
            "human_simulation": human_simulation,
            "style_instruction": style,
        },
        retries,
        retry_delay,
    )
    return extract_audio_url(data)


def request_synthesize_audio_url(token: str, text: str, voice: str, speed: float, retries: int, retry_delay: float) -> str:
    data = post_json(
        token,
        SYNTHESIZE_API_URL,
        {
            "text": text,
            "voice": voice,
            "speed": speed,
        },
        retries,
        retry_delay,
    )
    return extract_audio_url(data)


def list_voices(token: str) -> None:
    request = urllib.request.Request(
        VOICES_URL,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Darijat API returned HTTP {exc.code}: {body}") from exc

    voices = data.get("voices", [])
    if not voices:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    for voice in voices:
        voice_id = voice.get("id", "")
        name = voice.get("name", "")
        voice_type = voice.get("type", "")
        print(f"{voice_id}\t{name}\t{voice_type}")


def download_audio(audio_url: str, output: Path) -> None:
    with urllib.request.urlopen(audio_url, timeout=180) as response:
        output.write_bytes(response.read())


def trim_to_duration(source: Path, output: Path, duration: float) -> None:
    tmp_output = output.with_suffix(".trimmed.mp3")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(tmp_output),
        ]
    )
    tmp_output.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-file", type=Path, default=DEFAULT_TEXT_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Darijat voice name or Voice ID.")
    parser.add_argument("--style-instruction", default=DEFAULT_STYLE)
    parser.add_argument("--api-mode", choices=["external", "synthesize"], default="external")
    parser.add_argument("--no-human-simulation", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--target-duration", type=float, default=20.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-delay", type=float, default=20.0)
    parser.add_argument("--list-voices", action="store_true", help="List account voices and exit.")
    args = parser.parse_args()

    load_env_file(ROOT / ".env")
    token = os.environ.get("DARIJAT_API_TOKEN")
    if not token:
        raise SystemExit("Missing DARIJAT_API_TOKEN in the environment.")

    if args.list_voices:
        list_voices(token)
        return

    text = args.text_file.read_text(encoding="utf-8").strip()
    if args.api_mode == "external":
        audio_url = request_external_audio_url(
            token,
            text,
            args.voice,
            args.style_instruction,
            not args.no_human_simulation,
            args.retries,
            args.retry_delay,
        )
    else:
        audio_url = request_synthesize_audio_url(token, text, args.voice, args.speed, args.retries, args.retry_delay)
    download_audio(audio_url, args.output)

    duration = ffprobe_duration(args.output)
    if duration > args.target_duration + 0.25:
        trim_to_duration(args.output, args.output, args.target_duration)
        duration = ffprobe_duration(args.output)

    print(f"Wrote {args.output}")
    print(f"Duration: {duration:.3f}s")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
