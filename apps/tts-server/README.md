# MOSS TTS Server

Optional GPU microservice for PromptLoom. It serves
[OpenMOSS-Team/MOSS-TTS-v1.5](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5)
over HTTP in one Docker container, with one model **loaded once and kept warm in
VRAM**. The primary `apps/video-api` application consumes it through the
`moss-remote` voice engine.

Why it exists: the video worker used to load the ~8B MOSS checkpoint in-process, per job, on CPU. Moving synthesis to a dedicated GPU box removes both costs — model reload time and CPU inference — and adds a server-side audio cache so repair attempts only re-synthesize what changed.

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/healthz` | Engine state (`loading`/`ready`/`error`), model, GPU/VRAM, queue depth. `200` when ready, `503` otherwise. No auth. |
| `POST` | `/v1/tts/batch` | Submit all segments of a video in one call. Returns `202` with a `job_id`. |
| `GET` | `/v1/jobs/{job_id}` | Per-segment progress + download URLs when done. |
| `GET` | `/v1/jobs/{job_id}/audio/{key}.wav` | Download the canonical PCM16 segment WAV. |
| `GET` | `/v1/jobs/{job_id}/audio/{key}.mp3` | Compatibility download; encodes the MP3 atomically on first request. |
| `POST` | `/v1/tts` | Synchronous single-segment synthesis (testing); returns WAV bytes. |

All `/v1/*` endpoints require `Authorization: Bearer <key>` (or `X-API-Key: <key>`) when `TTS_SERVER_API_KEYS` is set.

### Batch request

```json
{
  "language": "en",
  "model": "OpenMOSS-Team/MOSS-TTS-v1.5",
  "consistent_voice": true,
  "reference_audio_b64": null,
  "segments": [
    {"key": "Scene1_IntroEN", "text": "The kernel sits between hardware and programs."},
    {"key": "Scene2_SyscallEN", "text": "A system call crosses that boundary."}
  ]
}
```

- `model` is an optional sanity check: mismatch with the loaded model returns `409`.
- `consistent_voice`: segments are synthesized in order; the first WAV (uploaded reference, else first generated segment) becomes the voice-cloning reference for the rest — same behavior as the local `moss` engine.
- `reference_audio_b64`: optional base64 WAV forced as the reference for every segment. The video worker sends its first locally cached segment here, so a repair run keeps the same timbre.

### Job status response (excerpt)

```json
{
  "job_id": "8c1f…",
  "status": "completed",
  "segments": [
    {"key": "Scene1_IntroEN", "status": "done", "cached": false,
     "duration_seconds": 6.42, "wav_url": "/v1/jobs/8c1f…/audio/Scene1_IntroEN.wav",
     "mp3_url": "/v1/jobs/8c1f…/audio/Scene1_IntroEN.mp3"}
  ]
}
```

Statuses: job `queued | running | completed | failed`; segment `pending | running | done | failed`. `cached: true` means the WAV came from the content-addressed cache (model + language + normalized text + reference hash) without touching the GPU.
`mp3_url` remains present for compatibility, but no MP3 is produced during
synthesis. The first request to that URL derives it from the canonical WAV;
PromptLoom's video pipeline consumes only WAV and encodes AAC once in the final
MP4.

## Deploy on the GPU server

Prerequisites: NVIDIA driver, Docker, [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), ≥ 24 GB VRAM (the BF16 checkpoint needs ~16-18 GB).

```bash
cd apps/tts-server
cp .env.example .env        # set TTS_SERVER_API_KEYS
docker compose up --build -d
docker compose logs -f tts  # watch the model download/load
```

First boot downloads the checkpoint into the `tts_data` volume (`/data/hf-cache`); the healthcheck allows 30 minutes for that. Then:

```bash
curl http://localhost:8100/healthz
```

Smoke test a real synthesis:

```bash
curl -s -X POST http://localhost:8100/v1/tts \
  -H 'Authorization: Bearer <key>' -H 'Content-Type: application/json' \
  -d '{"text":"GPU synthesis is up.","language":"en"}' -o /tmp/test.wav
ffprobe /tmp/test.wav
```

## Wire video-api to it

In the repository root `.env` on the machine running the worker:

```bash
VIDEO_API_VOICE_ENGINE=moss-remote
VIDEO_API_TTS_SERVER_URL=http://<gpu-host>:8100
VIDEO_API_TTS_SERVER_API_KEY=<key>
```

If the server is unreachable or the job fails, the video job **fails with a clear error** in `logs/voice.log` — there is no silent fallback to another voice.

## Configuration

See `.env.example`. Key variables:

| Variable | Default | Role |
| --- | --- | --- |
| `TTS_SERVER_API_KEYS` | empty (auth off) | Comma-separated keys. Empty is for trusted LAN only. |
| `TTS_SERVER_MODEL` | `OpenMOSS-Team/MOSS-TTS-v1.5` | Model loaded at startup. |
| `TTS_SERVER_DEVICE` / `TTS_SERVER_DTYPE` | `auto` / `auto` | `auto` = CUDA + BF16 on the GPU box. |
| `TTS_SERVER_MAX_NEW_TOKENS` | `4096` | Hard token ceiling. The server also derives a per-segment cap from the text length, bounding runaway generations that never emit an end token. |
| `TTS_SERVER_BATCH_SIZE` | `1` | Same-reference segments generated per batched pass. `1` = sequential. Higher values speed up bandwidth-bound GPUs (DGX Spark / GB10) by reading the weights once for several segments; raise carefully and validate audio. |
| `TTS_SERVER_JOB_TTL_HOURS` | `48` | Terminal jobs (audio included) are purged after this. |
| `TTS_SERVER_CACHE_TTL_DAYS` | `30` | WAV cache retention (`0` = keep forever). |
| `TTS_SERVER_FAKE_ENGINE` | `0` | `1` = silent-WAV fake engine, runs without GPU/torch (tests). |

## Tests

```bash
cd apps/tts-server
docker compose run --rm test
```

Or locally without Docker (no GPU needed, the suite uses the fake engine):

```bash
uv venv && uv pip install -e '.[test]' && uv run pytest -q
```

## Operational notes

- The GPU is serialized: one synthesis at a time (queue + lock). `VIDEO_API_WORKER_CONCURRENCY=1` on the video side matches this; if you ever raise it, jobs just queue up here.
- Jobs interrupted by a server restart are marked `failed: interrupted by server restart`; the video worker's retry then mostly hits the cache.
- MOSS sampling is stochastic: the cache is also what keeps a voice take stable across repair attempts — don't disable it casually.
- `flash-attn` is optional; when absent the engine falls back to PyTorch SDPA, which is fine. Install it in the image only if you need the extra speed.
