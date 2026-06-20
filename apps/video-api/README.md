# Academic Video API

Dockerized API for turning an academic STEM prompt into a sourced Manim or
Remotion video through a queued worker pipeline.

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

```bash
cd apps/video-api
cp .env.example .env
docker compose up --build
```

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
