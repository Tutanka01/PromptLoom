from __future__ import annotations

import importlib.util
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
_VOICE_SCRIPT = (
    _REPO_ROOT
    / "videos"
    / "linux-fondamentaux"
    / "002-c-est-quoi-un-syscall"
    / "generate_voice_en.py"
)


def _load_voice_module():
    spec = importlib.util.spec_from_file_location("reference_generate_voice_en", _VOICE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_moss_generation_anchors_later_segments_to_first_wav(monkeypatch, tmp_path: Path) -> None:
    module = _load_voice_module()
    audio_dir = tmp_path / "audio" / "en"
    calls: list[tuple[str, str]] = []

    def fake_run_moss_command_template(
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
        calls.append((key, reference_audio))
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.write_bytes(b"RIFF")

    def fake_write_mp3_from_wav(wav_path: Path, mp3_path: Path) -> None:
        mp3_path.write_bytes(b"ID3")

    monkeypatch.setattr(module, "OUT_DIR", audio_dir)
    monkeypatch.setattr(module, "_select_torch_device", lambda requested: "cpu")
    monkeypatch.setattr(module, "_run_moss_command_template", fake_run_moss_command_template)
    monkeypatch.setattr(module, "write_mp3_from_wav", fake_write_mp3_from_wav)

    module.generate_moss(
        [
            {"key": "Scene1", "text": "Premier segment."},
            {"key": "Scene2", "text": "Deuxieme segment."},
        ],
        model_id="OpenMOSS-Team/MOSS-TTS-v1.5",
        language="fr",
        voice="",
        reference_audio="",
        reference_text="",
        device="cpu",
        dtype="auto",
        command_template="fake {output}",
        force=False,
        consistent_voice=True,
    )

    assert calls == [
        ("Scene1", ""),
        ("Scene2", str((audio_dir / "Scene1.wav").resolve())),
    ]
