"""MOSS-TTS engine: loaded once at startup, GPU access serialized by a lock.

The synthesis logic mirrors the reference implementation in
``videos/linux-fondamentaux/002-c-est-quoi-un-syscall/generate_voice_en.py``
(device/dtype/attention selection, language names, reference-audio cloning) so
the remote voice sounds exactly like the local ``moss`` engine. The win of this
server is operational: the ~8B model stays warm in VRAM between jobs instead of
being reloaded per video.
"""
from __future__ import annotations

import importlib.util
import logging
import threading
import wave
from pathlib import Path

from tts_server.config import Settings

logger = logging.getLogger(__name__)

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


def moss_language_name(language: str) -> str:
    language = (language or "").strip()
    code = language.lower().replace("_", "-").split("-", 1)[0]
    if code not in MOSS_LANGUAGE_NAMES:
        supported = ", ".join(sorted(MOSS_LANGUAGE_NAMES))
        raise ValueError(f"MOSS-TTS does not support language {language!r}. Supported codes: {supported}")
    return MOSS_LANGUAGE_NAMES[code]


class EngineNotReady(RuntimeError):
    pass


class BaseEngine:
    name = "base"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._load_error: str | None = None

    # -- lifecycle -----------------------------------------------------------
    def start_loading(self) -> None:
        thread = threading.Thread(target=self._load_safely, name="engine-load", daemon=True)
        thread.start()

    def _load_safely(self) -> None:
        try:
            self._load()
        except Exception as error:  # noqa: BLE001 - surfaced via state/ensure_ready
            self._load_error = f"{type(error).__name__}: {error}"
            logger.exception("engine.load.failed model=%s", self.settings.model_id)
        else:
            self._ready.set()
            logger.info("engine.ready engine=%s model=%s", self.name, self.settings.model_id)

    def _load(self) -> None:  # pragma: no cover - overridden
        pass

    @property
    def state(self) -> str:
        if self._load_error:
            return "error"
        return "ready" if self._ready.is_set() else "loading"

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def ensure_ready(self, timeout: float | None = None) -> None:
        """Block until the model is loaded; raise if loading failed/timed out."""
        import time

        deadline = None if timeout is None else time.monotonic() + timeout
        while not self._ready.wait(timeout=1.0):
            if self._load_error:
                raise EngineNotReady(f"model failed to load: {self._load_error}")
            if deadline is not None and time.monotonic() > deadline:
                raise EngineNotReady("timed out waiting for the model to load")
        if self._load_error:
            raise EngineNotReady(f"model failed to load: {self._load_error}")

    # -- synthesis -----------------------------------------------------------
    def synthesize(self, text: str, language: str, reference: Path | None, out_path: Path) -> None:
        self.ensure_ready()
        with self._lock:
            self._synthesize(text, language, reference, out_path)

    def _synthesize(self, text: str, language: str, reference: Path | None, out_path: Path) -> None:
        raise NotImplementedError

    def info(self) -> dict:
        return {"engine": self.name, "model": self.settings.model_id, "state": self.state}


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
    # The checkpoint is BF16; keeping it avoids materializing the 8B params as
    # fp32 (double the memory) on CPU and CUDA alike.
    return torch.bfloat16 if device in {"cpu", "cuda"} else torch.float32


def _resolve_attn_implementation(device: str, dtype) -> str:
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


class MossEngine(BaseEngine):
    name = "moss"

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._processor = None
        self._model = None
        self._device: str | None = None
        self._dtype_name: str | None = None

    def _load(self) -> None:
        import torch
        from transformers import AutoModel, AutoProcessor

        device = _select_torch_device(self.settings.device)
        if device == "cuda":
            torch.backends.cuda.enable_cudnn_sdp(False)
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            torch.backends.cuda.enable_math_sdp(True)
        dtype = _select_moss_dtype(self.settings.dtype, device)
        attn_implementation = _resolve_attn_implementation(device, dtype)
        logger.info(
            "engine.load.start model=%s device=%s dtype=%s attn=%s",
            self.settings.model_id,
            device,
            dtype,
            attn_implementation,
        )
        processor = AutoProcessor.from_pretrained(self.settings.model_id, trust_remote_code=True)
        processor.audio_tokenizer = processor.audio_tokenizer.to(device)
        model = AutoModel.from_pretrained(
            self.settings.model_id,
            trust_remote_code=True,
            attn_implementation=attn_implementation,
            torch_dtype=dtype,
            low_cpu_mem_usage=True,
        ).to(device)
        model.eval()
        self._processor = processor
        self._model = model
        self._device = device
        self._dtype_name = str(dtype)

    def _synthesize(self, text: str, language: str, reference: Path | None, out_path: Path) -> None:
        import soundfile as sf
        import torch

        processor, model = self._processor, self._model
        device = next(model.parameters()).device
        language_name = moss_language_name(language)
        reference_list = [str(reference)] if reference else None
        conversation = [
            processor.build_user_message(text=text, language=language_name, reference=reference_list)
        ]
        with torch.no_grad():
            batch = processor([conversation], mode="generation")
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            outputs = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=self.settings.max_new_tokens,
            )
            messages = [message for message in processor.decode(outputs) if message is not None]
            if not messages or not messages[0].audio_codes_list:
                raise RuntimeError("MOSS TTS returned no decoded audio.")
            audio = messages[0].audio_codes_list[0]
            # Written via soundfile, not torchaudio.save: torchaudio >= 2.9
            # delegates saving to the optional `torchcodec` package, absent from
            # the image. PCM16 keeps the WAV readable by the stdlib `wave`
            # duration probe and halves the size vs float32.
            sf.write(
                str(out_path),
                audio.to(torch.float32).cpu().numpy(),
                processor.model_config.sampling_rate,
                subtype="PCM_16",
            )

    def info(self) -> dict:
        data = super().info()
        data.update({"device": self._device, "dtype": self._dtype_name})
        try:
            import torch

            if torch.cuda.is_available():
                free, total = torch.cuda.mem_get_info()
                data["gpu"] = torch.cuda.get_device_name(0)
                data["vram_free_gb"] = round(free / 1024**3, 1)
                data["vram_total_gb"] = round(total / 1024**3, 1)
        except Exception:  # noqa: BLE001 - health info is best-effort
            pass
        return data


class FakeEngine(BaseEngine):
    """Deterministic stand-in for tests and GPU-less smoke runs.

    Writes silent PCM16 WAVs whose duration scales with the text length, and
    records every call (text, language, reference) for assertions.
    """

    name = "fake"
    sample_rate = 24000

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.calls: list[tuple[str, str, str]] = []

    def _load(self) -> None:
        return None

    def _synthesize(self, text: str, language: str, reference: Path | None, out_path: Path) -> None:
        moss_language_name(language)
        self.calls.append((text, language, str(reference) if reference else ""))
        seconds = max(0.3, len(text) / 15.0)
        frames = int(seconds * self.sample_rate)
        with wave.open(str(out_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.sample_rate)
            handle.writeframes(b"\x00\x00" * frames)


def create_engine(settings: Settings) -> BaseEngine:
    if settings.fake_engine:
        return FakeEngine(settings)
    return MossEngine(settings)
