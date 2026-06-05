# Documentation

This directory is the single home for reusable project documentation.

Do not put operational documentation inside `videos/...` folders. Video folders contain production sources only.

## Reading Order

1. `../AGENTS.md`  
   Rules for agents working in the repository.

2. `../PROCEDURE.md`  
   Operational checklist for producing or updating a video.

3. `VIDEO_PRODUCTION_STANDARD.md`  
   Detailed v2 standard: beat-sync, Manim helpers, design system, verification, acceptance criteria.

4. `VOICE_AND_AUDIO.md`  
   Voice model policy, Chatterbox command, regeneration rules, audio duration checks.

5. `VIDEOS.md`  
   Central registry of current videos and their status.

6. `boilerplate/README.md`  
   Files to copy when starting a new video.

## Current Standard

The current standard is v2:

- one segment per Manim scene;
- `audio/en/durations.json` for total scene duration;
- `beats_en.json` for internal visual beats;
- local style system per video;
- low-quality iteration before final render;
- `ffprobe`, `freezedetect`, and snapshots before delivery.

## Documentation Policy

Allowed at repository root:

- `README.md`
- `AGENTS.md`
- `PROCEDURE.md`

Allowed in `docs/`:

- reusable workflow documentation;
- boilerplate files;
- project-wide voice/audio notes;
- central video registry.

Allowed in `videos/...`:

- `segments_en.json`;
- `beats_en.json`;
- Manim code;
- style code;
- TTS/render/assemble scripts;
- selected final MP4s.

Not allowed in `videos/...`:

- README files;
- plan/script documentation;
- general workflow documentation;
- duplicated voice model notes;
- obsolete notes about previous production methods.

Video-specific narrative docs live in:

```text
docs/videos/<theme>/<slug>/
```
