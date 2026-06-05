# manim-video-voice-generator

Production workflow for polished educational videos about Linux and low-level systems.

The repository now follows the v2 video standard: narration is split into scene segments, TTS audio provides real scene durations, and `beats_en.json` maps important spoken moments to visual actions inside each scene.

## References

Current videos:

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/final/syscall-intro-en-final.mp4
```

Reference roles:

- `001-c-est-quoi-le-kernel`: historical stable pipeline reference.
- `002-c-est-quoi-un-syscall`: v2 reference for beat-sync, visual focus, dimming, and `freezedetect` checks.

## Documentation

All reusable documentation lives at the repository root or in `docs/`.

Read in this order:

```text
AGENTS.md
PROCEDURE.md
docs/README.md
docs/VIDEO_PRODUCTION_STANDARD.md
docs/VOICE_AND_AUDIO.md
docs/VIDEOS.md
docs/boilerplate/README.md
```

Do not add README or operational documentation inside individual video folders. Video folders should contain production source files only.

## Video Folder Shape

Each video has two locations.

Narrative documentation lives under:

```text
docs/videos/<theme>/<number-slug>/
```

Video production files live under:

```text
videos/<theme>/<number-slug>/
```

Expected documentation files:

```text
plan.md
script.md or script_en.md
```

Expected production files:

```text
segments_en.json
beats_en.json
<slug>_en.py
<slug>_style.py
generate_voice_en.py
render_en.sh
assemble_en.sh
final/<slug>-en-final.mp4
```

Generated working artifacts such as `audio/`, `media/`, `renders/`, `concat*.txt`, and silent MP4 files are not source documentation.

## Core Workflow

1. Define the topic, audience, and teaching goal.
2. Write or update `docs/videos/<theme>/<slug>/plan.md`.
3. Write the narration in `docs/videos/<theme>/<slug>/script.md`.
4. Split narration into `segments_en.json`.
5. Add narrative beats in `beats_en.json`.
6. Build Manim scenes and a local style system.
7. Generate or reuse Chatterbox voice audio.
8. Render low quality with `QUALITY=ql ./render_en.sh`.
9. Assemble with `./assemble_en.sh`.
10. Verify with `ffprobe`, `freezedetect`, and snapshots.
11. Render final quality with `QUALITY=qh ./render_en.sh`.
12. Assemble and verify the final MP4.

The voice and the image must explain the same concept at the same time. A video is not final until the technical checks and visual snapshots have been inspected.

## Boilerplate

Use the templates in:

```text
docs/boilerplate/
```

They define both the documentation files to copy into `docs/videos/...` and the production files to copy into `videos/...`.

## Preferred Voice

Use Chatterbox main, non-turbo, unless the user explicitly asks for a change:

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

## Git Hygiene

Before finishing work:

```bash
git status --short
git diff --check
```

Commit source files, documentation in `docs/`, scripts, plans, segments, beats, Manim code, style files, and selected final MP4s. Do not commit generated working artifacts by default.
