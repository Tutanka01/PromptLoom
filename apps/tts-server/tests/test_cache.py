from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tts_server.cache import AudioCache


def _engine_profile() -> dict:
    return {
        "generator": {
            "name": "promptloom-moss-tts-server",
            "version": "0.1.0",
            "profile_version": 2,
        },
        "model": {
            "repo": "OpenMOSS-Team/MOSS-TTS-v1.5",
            "revision": "1" * 40,
            "remote_code_revision": "1" * 40,
            "codec_repo": "OpenMOSS-Team/MOSS-Audio-Tokenizer",
            "codec_revision": "2" * 40,
        },
        "image_digest": f"sha256:{'3' * 64}",
        "runtime": {
            "python": "3.11.13",
            "torch": "2.7.1",
            "transformers": "4.53.2",
        },
        "engine": "moss",
        "device": "cuda",
        "dtype": "torch.bfloat16",
        "attention": "sdpa",
        "generation": {
            "sampling": {
                "text_temperature": 1.5,
                "text_top_p": 1.0,
                "text_top_k": 50,
                "audio_temperature": 1.7,
                "audio_top_p": 0.8,
                "audio_top_k": 25,
                "audio_repetition_penalty": 1.0,
            },
            "batching": {
                "configured_batch_size": 1,
                "policy": "ordered-same-reference-v1",
            },
            "max_new_tokens_policy": {
                "ceiling": 4096,
                "floor": 256,
            },
        },
        "audio_format": {
            "container": "wav",
            "codec": "pcm_s16le",
            "sample_rate": 24000,
            "channels": 1,
        },
    }


def _identity(
    *,
    profile: dict | None = None,
    language: str = "en",
    text: str = "Exact message.",
    reference_hash: str | None = "4" * 64,
) -> tuple[str, str]:
    return AudioCache.identity(
        engine_profile=profile or _engine_profile(),
        language=language,
        text=text,
        reference_hash=reference_hash,
    )


def _replace(profile: dict, path: tuple[str, ...], value: object) -> dict:
    changed = copy.deepcopy(profile)
    target = changed
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return changed


def test_canonical_profile_is_stable_across_mapping_order() -> None:
    profile = _engine_profile()
    reordered = dict(reversed(list(profile.items())))
    reordered["model"] = dict(reversed(list(profile["model"].items())))

    assert _identity(profile=profile) == _identity(profile=reordered)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("model", "revision"), "a" * 40),
        (("model", "remote_code_revision"), "b" * 40),
        (("model", "codec_revision"), "c" * 40),
        (("image_digest",), f"sha256:{'d' * 64}"),
        (("runtime", "transformers"), "4.54.0"),
        (("dtype",), "torch.float16"),
        (("attention",), "flash_attention_2"),
        (("generation", "sampling", "text_temperature"), 1.4),
        (("generation", "sampling", "text_top_p"), 0.9),
        (("generation", "sampling", "text_top_k"), 40),
        (("generation", "sampling", "audio_temperature"), 1.6),
        (("generation", "sampling", "audio_top_p"), 0.7),
        (("generation", "sampling", "audio_top_k"), 20),
        (("generation", "sampling", "audio_repetition_penalty"), 1.1),
        (("generation", "batching", "configured_batch_size"), 2),
        (("generation", "max_new_tokens_policy", "ceiling"), 2048),
        (("audio_format", "sample_rate"), 48000),
        (("audio_format", "codec"), "pcm_f32le"),
    ],
)
def test_every_engine_dimension_invalidates_the_cache_key(
    path: tuple[str, ...],
    value: object,
) -> None:
    profile = _engine_profile()

    assert _identity(profile=profile) != _identity(
        profile=_replace(profile, path, value)
    )


def test_exact_text_language_and_reference_content_are_keyed(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path / "cache")
    first_reference = tmp_path / "one.wav"
    same_reference = tmp_path / "same.wav"
    changed_reference = tmp_path / "changed.wav"
    first_reference.write_bytes(b"same bytes")
    same_reference.write_bytes(b"same bytes")
    changed_reference.write_bytes(b"different bytes")

    baseline = _identity(
        text="First line.\nSecond line.",
        reference_hash=cache.file_hash(first_reference),
    )
    assert baseline == _identity(
        text="First line.\nSecond line.",
        reference_hash=cache.file_hash(same_reference),
    )
    assert baseline != _identity(
        text="First line. Second line.",
        reference_hash=cache.file_hash(first_reference),
    )
    assert baseline != _identity(
        language="fr",
        text="First line.\nSecond line.",
        reference_hash=cache.file_hash(first_reference),
    )
    assert baseline != _identity(
        text="First line.\nSecond line.",
        reference_hash=cache.file_hash(changed_reference),
    )
    assert baseline != _identity(
        text="First line.\nSecond line.",
        reference_hash=None,
    )


def test_profile_and_fingerprint_use_full_sha256() -> None:
    profile_id, fingerprint = _identity()

    assert len(profile_id) == 64
    assert len(fingerprint) == 64
    int(profile_id, 16)
    int(fingerprint, 16)


def test_cache_store_publishes_atomically_without_leaking_temp_files(tmp_path: Path) -> None:
    cache = AudioCache(tmp_path / "cache")
    source = tmp_path / "source.wav"
    source.write_bytes(b"RIFFpayload")

    target = cache.store("a" * 64, source)

    assert target.read_bytes() == source.read_bytes()
    assert list(cache.root.glob("*.tmp")) == []
    assert list(cache.root.glob(".*.tmp")) == []
