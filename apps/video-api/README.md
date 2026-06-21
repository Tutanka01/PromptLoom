# PromptLoom Video API

Primary application of the repository. It turns an educational prompt into a
sourced Manim or Remotion video through a queued worker pipeline. The current
editorial contract is optimized for STEM content.

New to the repository? Start with the root
[onboarding guide](../../docs/START_HERE.md) and the
[first-video tutorial](../../docs/FIRST_VIDEO.md).

## Documentation

Start here:

- [docs/README.md](docs/README.md): documentation index.
- [docs/quickstart.md](docs/quickstart.md): user-friendly curl workflow.
- [docs/architecture.md](docs/architecture.md): system architecture and job lifecycle.
- [docs/developer-guide.md](docs/developer-guide.md): developer workflow and extension points.
- [docs/operations.md](docs/operations.md): Docker, environment variables, testing, and troubleshooting.
- [docs/remotion-engine.md](docs/remotion-engine.md): Remotion render engine (`VIDEO_API_RENDER_ENGINE=remotion`), an alternative to Manim sharing the same TTS/assemble/verify.
- [docs/advanced-production.md](docs/advanced-production.md): per-request research, media, motion-first rendering, captions, sound bridges, and anti-slideshow gates.

## Run Locally

From the repository root:

```bash
cp apps/video-api/.env.example .env
docker compose up --build
```

The local `cd apps/video-api && docker compose up --build` workflow remains
supported for component-level development.

Submit a job:

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Make a short video explaining derivatives intuitively","theme":"math","language":"en"}'
```

Submit a sourced motion-first job (requires a configured Tavily or Exa key):

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain the Linux syscall boundary","theme":"linux-fondamentaux","production_mode":"cinematic"}'
```

Poll:

```bash
curl http://localhost:8080/v1/videos/<job_id>
```

Download when completed:

```bash
curl -L http://localhost:8080/v1/videos/<job_id>/download -o video.mp4
```

## LLM Configuration

Any OpenAI-compatible endpoint is configured with environment variables:

```text
OPENAI_BASE_URL=http://your-server/v1
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

For local smoke tests without an LLM:

```text
VIDEO_API_FAKE_LLM=1
```

## Architecture

- `api`: FastAPI service for job creation, status, reports, and MP4 download.
- `worker`: Celery worker that owns LLM generation, file materialization, Chatterbox voice, Manim render, ffmpeg assembly, verification, and repair.
- `redis`: broker.
- `postgres`: job metadata.
- `video_jobs`: shared artifact volume.

The generated job workspace is separate from the repository's tracked `videos/` tree.
