#!/usr/bin/env python3
"""Generate synchronized English scene voiceover files."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import shlex
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SEGMENTS_FILE = ROOT / "segments_en.json"
OUT_DIR = ROOT / "audio" / "en"


def bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


# Kokoro language code per spoken language. "a" = American English, "f" = French.
KOKORO_LANG_CODES = {"en": "a", "fr": "f"}


def generate_kokoro(segments: list[dict], voice: str, speed: float, lang: str, force: bool) -> None:
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    lang_code = KOKORO_LANG_CODES.get(lang.strip().lower(), "a")
    pipeline = KPipeline(lang_code=lang_code)
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


def write_openai_response(response, path: Path) -> None:
    if hasattr(response, "write_to_file"):
        response.write_to_file(path)
        return
    content = getattr(response, "content", None)
    if content is None and hasattr(response, "read"):
        content = response.read()
    if content is None:
        raise RuntimeError("OpenAI-compatible speech response did not expose bytes.")
    path.write_bytes(content)


def generate_openai(
    segments: list[dict],
    base_url: str | None,
    api_key: str | None,
    model: str,
    voice: str,
    response_format: str,
    speed: float,
    force: bool,
) -> None:
    from openai import OpenAI

    client = OpenAI(
        base_url=base_url or None,
        api_key=api_key or "not-needed",
    )
    for segment in segments:
        key = segment["key"]
        text = segment["text"]
        if should_skip_existing(key, force):
            continue
        wav_path = OUT_DIR / f"{key}.wav"
        mp3_path = OUT_DIR / f"{key}.mp3"
        source_path = wav_path if response_format == "wav" else OUT_DIR / f"{key}.openai.{response_format}"
        print(f"Generating OpenAI-compatible TTS segment {key} with model {model}")
        response = client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
            response_format=response_format,
            speed=speed,
        )
        write_openai_response(response, source_path)
        if response_format != "wav":
            if not shutil.which("ffmpeg"):
                raise SystemExit("ffmpeg is required to convert OpenAI-compatible TTS audio to WAV.")
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(source_path),
                    "-ar",
                    "24000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(wav_path),
                ]
            )
        write_mp3_from_wav(wav_path, mp3_path)


def _select_torch_device(requested: str) -> str:
    import torch

    requested = (requested or "auto").strip().lower()
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _select_moss_dtype(requested: str, device: str):
    import torch

    requested = (requested or "auto").strip().lower()
    if requested in {"float32", "fp32"}:
        return torch.float32
    if requested in {"float16", "fp16"}:
        return torch.float16
    if requested in {"bfloat16", "bf16"}:
        return torch.bfloat16
    # The checkpoint is BF16. On CPU this avoids materializing the 8B params as
    # fp32, which can double RAM usage and get the worker killed while loading.
    return torch.bfloat16 if device in {"cpu", "cuda"} else torch.float32


MOSS_LANGUAGE_NAMES = {
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
    "ja": "Japanese",
    "ko": "Korean",
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


def _moss_language_name(language: str) -> str:
    language = (language or "").strip()
    code = language.lower().replace("_", "-").split("-", 1)[0]
    if code not in MOSS_LANGUAGE_NAMES:
        supported = ", ".join(sorted(MOSS_LANGUAGE_NAMES))
        raise RuntimeError(f"MOSS-TTS does not support language {language!r}. Supported codes: {supported}")
    return MOSS_LANGUAGE_NAMES[code]


class _FormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _run_moss_command_template(
    template: str,
    *,
    key: str,
    text: str,
    language: str,
    model: str,
    wav_path: Path,
    reference_audio: str,
    reference_text: str,
) -> None:
    text_file = OUT_DIR / f"{key}.txt"
    text_file.write_text(text, encoding="utf-8")
    values = _FormatDict(
        key=key,
        text=text,
        text_json=json.dumps(text, ensure_ascii=False),
        text_file=str(text_file),
        language=language,
        model=model,
        output=str(wav_path),
        reference_audio=reference_audio,
        reference_text=reference_text,
    )
    command = shlex.split(template.format_map(values))
    run(command)
    if not wav_path.exists():
        raise RuntimeError(f"MOSS command did not write expected WAV: {wav_path}")


def _resolve_moss_attn_implementation(device: str, dtype) -> str:
    import torch

    if (
        device == "cuda"
        and importlib.util.find_spec("flash_attn") is not None
        and dtype in {torch.float16, torch.bfloat16}
    ):
        major, _ = torch.cuda.get_device_capability()
        if major >= 8:
            return "flash_attention_2"
    if device == "cuda":
        return "sdpa"
    return "eager"


def _load_moss_generator(model_id: str, device: str, dtype_name: str):
    import torch
    from transformers import AutoModel, AutoProcessor

    if device == "cuda":
        torch.backends.cuda.enable_cudnn_sdp(False)
        torch.backends.cuda.enable_flash_sdp(True)
        torch.backends.cuda.enable_mem_efficient_sdp(True)
        torch.backends.cuda.enable_math_sdp(True)
    dtype = _select_moss_dtype(dtype_name, device)
    attn_implementation = _resolve_moss_attn_implementation(device, dtype)
    print(f"[INFO] MOSS dtype={dtype} attn_implementation={attn_implementation}")
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    processor.audio_tokenizer = processor.audio_tokenizer.to(device)
    model = AutoModel.from_pretrained(
        model_id,
        trust_remote_code=True,
        attn_implementation=attn_implementation,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
    ).to(device)
    model.eval()
    return processor, model


def _generate_moss_audio(
    processor,
    model,
    text: str,
    language: str,
    reference_audio: str,
    wav_path: Path,
) -> None:
    import torch
    import torchaudio

    device = next(model.parameters()).device
    language_name = _moss_language_name(language)
    reference = [reference_audio] if reference_audio else None
    conversation = [processor.build_user_message(text=text, language=language_name, reference=reference)]
    with torch.no_grad():
        batch = processor([conversation], mode="generation")
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=4096,
        )
        messages = [message for message in processor.decode(outputs) if message is not None]
        if not messages or not messages[0].audio_codes_list:
            raise RuntimeError("MOSS TTS returned no decoded audio.")
        audio = messages[0].audio_codes_list[0]
        torchaudio.save(str(wav_path), audio.unsqueeze(0), processor.model_config.sampling_rate)


def generate_moss(
    segments: list[dict],
    model_id: str,
    language: str,
    voice: str,
    reference_audio: str,
    reference_text: str,
    device: str,
    dtype: str,
    command_template: str,
    force: bool,
    consistent_voice: bool,
) -> None:
    resolved_device = _select_torch_device(device)
    generator = None
    if not command_template:
        print(f"Loading MOSS TTS model {model_id} on {resolved_device}")
        generator = _load_moss_generator(model_id, resolved_device, dtype)

    anchor_reference_audio = reference_audio
    if consistent_voice and anchor_reference_audio:
        print(f"Using configured MOSS voice reference: {anchor_reference_audio}")
    if consistent_voice and command_template and "{reference_audio}" not in command_template:
        print(
            "Warning: --moss-command does not include {reference_audio}; "
            "automatic MOSS voice anchoring may have no effect."
        )

    for segment in segments:
        key = segment["key"]
        text = segment["text"]
        wav_path = OUT_DIR / f"{key}.wav"
        if should_skip_existing(key, force):
            if consistent_voice and not anchor_reference_audio and wav_path.exists():
                anchor_reference_audio = str(wav_path.resolve())
                print(f"Using existing {key} audio as MOSS voice reference for following segments")
            continue
        mp3_path = OUT_DIR / f"{key}.mp3"
        print(f"Generating MOSS TTS segment {key} language={language} model={model_id}")
        if command_template:
            _run_moss_command_template(
                command_template,
                key=key,
                text=text,
                language=language,
                model=model_id,
                wav_path=wav_path,
                reference_audio=anchor_reference_audio,
                reference_text=reference_text,
            )
        else:
            processor, model = generator
            if voice:
                print("Warning: --moss-voice is not used by the native MOSS-TTS generator.")
            if reference_text:
                print("Warning: --moss-reference-text is not used by the native MOSS-TTS generator.")
            _generate_moss_audio(processor, model, text, language, anchor_reference_audio, wav_path)
        write_mp3_from_wav(wav_path, mp3_path)
        if consistent_voice and not anchor_reference_audio:
            anchor_reference_audio = str(wav_path.resolve())
            print(f"Using generated {key} audio as MOSS voice reference for following segments")


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
    parser.add_argument("--engine", choices=["kokoro", "chatterbox", "chatterbox-turbo", "openai", "moss"], default="chatterbox")
    parser.add_argument("--kokoro-voice", default="af_bella")
    parser.add_argument("--kokoro-speed", type=float, default=0.92)
    parser.add_argument("--kokoro-lang", default="en", help="Spoken language for Kokoro: en or fr.")
    parser.add_argument("--exaggeration", type=float, default=0.45)
    parser.add_argument("--cfg-weight", type=float, default=0.55)
    parser.add_argument("--temperature", type=float, default=0.55)
    parser.add_argument("--tail-padding", type=float, default=0.45)
    parser.add_argument(
        "--moss-model",
        default=os.getenv("VIDEO_API_MOSS_TTS_MODEL", "OpenMOSS-Team/MOSS-TTS-v1.5"),
    )
    parser.add_argument("--moss-language", default=os.getenv("VIDEO_API_MOSS_TTS_LANGUAGE", "en"))
    parser.add_argument("--moss-voice", default=os.getenv("VIDEO_API_MOSS_TTS_VOICE", ""))
    parser.add_argument("--moss-reference-audio", default=os.getenv("VIDEO_API_MOSS_TTS_REFERENCE_AUDIO", ""))
    parser.add_argument("--moss-reference-text", default=os.getenv("VIDEO_API_MOSS_TTS_REFERENCE_TEXT", ""))
    parser.set_defaults(moss_consistent_voice=bool_env("VIDEO_API_MOSS_TTS_CONSISTENT_VOICE", True))
    parser.add_argument(
        "--moss-consistent-voice",
        dest="moss_consistent_voice",
        action="store_true",
        help="Use the first generated/reused MOSS segment as a voice reference for later segments.",
    )
    parser.add_argument(
        "--no-moss-consistent-voice",
        dest="moss_consistent_voice",
        action="store_false",
        help="Disable automatic MOSS voice anchoring between segments.",
    )
    parser.add_argument("--moss-device", default=os.getenv("VIDEO_API_MOSS_TTS_DEVICE", "auto"))
    parser.add_argument("--moss-dtype", default=os.getenv("VIDEO_API_MOSS_TTS_DTYPE", "auto"))
    parser.add_argument(
        "--moss-command",
        default=os.getenv("VIDEO_API_MOSS_TTS_COMMAND", ""),
        help=(
            "Optional per-segment command template. Placeholders: {text_file}, "
            "{text_json}, {output}, {language}, {model}, {reference_audio}, {reference_text}."
        ),
    )
    parser.add_argument("--openai-base-url", default=os.getenv("OPENAI_BASE_URL", ""))
    parser.add_argument("--openai-api-key", default=os.getenv("OPENAI_API_KEY", ""))
    parser.add_argument(
        "--openai-tts-model",
        default=os.getenv("VIDEO_API_OPENAI_TTS_MODEL") or os.getenv("OPENAI_TTS_MODEL") or "tts-1",
    )
    parser.add_argument(
        "--openai-tts-voice",
        default=os.getenv("VIDEO_API_OPENAI_TTS_VOICE") or os.getenv("OPENAI_TTS_VOICE") or "alloy",
    )
    parser.add_argument(
        "--openai-tts-format",
        choices=["wav", "mp3", "opus", "aac", "flac", "pcm"],
        default=os.getenv("VIDEO_API_OPENAI_TTS_FORMAT", "wav"),
    )
    parser.add_argument(
        "--openai-tts-speed",
        type=float,
        default=float(os.getenv("VIDEO_API_OPENAI_TTS_SPEED", "1.0")),
    )
    parser.add_argument("--force", action="store_true", help="Regenerate audio even when a segment WAV already exists.")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    segments = json.loads(SEGMENTS_FILE.read_text(encoding="utf-8"))["segments"]

    if args.engine == "kokoro":
        generate_kokoro(segments, args.kokoro_voice, args.kokoro_speed, args.kokoro_lang, args.force)
    elif args.engine == "chatterbox":
        generate_chatterbox(segments, args.exaggeration, args.cfg_weight, args.temperature, args.force)
    elif args.engine == "chatterbox-turbo":
        generate_chatterbox_turbo(segments, args.exaggeration, args.cfg_weight, args.temperature, args.force)
    elif args.engine == "openai":
        generate_openai(
            segments,
            args.openai_base_url,
            args.openai_api_key,
            args.openai_tts_model,
            args.openai_tts_voice,
            args.openai_tts_format,
            args.openai_tts_speed,
            args.force,
        )
    else:
        generate_moss(
            segments,
            args.moss_model,
            args.moss_language,
            args.moss_voice,
            args.moss_reference_audio,
            args.moss_reference_text,
            args.moss_device,
            args.moss_dtype,
            args.moss_command,
            args.force,
            args.moss_consistent_voice,
        )

    write_duration_files(segments, args.tail_padding)
    print(f"Wrote {OUT_DIR / 'voiceover_en.mp3'}")


if __name__ == "__main__":
    main()
