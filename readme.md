# manim-video-voice-generator

Create polished explainer videos from a structured script, synchronized TTS voiceover, Manim animations, and an `ffmpeg` final assembly step.

This repository is built around a simple idea: a good technical video is not just code that renders. The narration, the audio timing, and the visual explanation must move together scene by scene. If the voice explains the scheduler, the animation shows scheduling. If the voice explains virtual memory, the animation shows virtual addresses, page tables, and RAM.

The current showcase topic is Linux internals, starting with a first final video: **What is the Linux kernel?**

## Demo

First generated video, English version, rendered in 1080p60 with the preferred full Chatterbox voice:

<video src="videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4" controls width="100%"></video>

Direct file:

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4
```

## What This Project Provides

- A repeatable structure for educational videos.
- One narration segment per Manim scene.
- TTS generation driven by JSON segments.
- Real audio durations exported to `durations.json`.
- Manim scenes synchronized to the generated voice.
- Final audio/video muxing with `ffmpeg`.
- Technical checks with `ffprobe`.
- Visual snapshot checks before accepting a render.

The goal is a production workflow, not a throwaway animation prototype.

## Repository Strategy

The repository keeps:

- source scripts;
- video plans and narration;
- segment metadata;
- Manim scene code;
- TTS generation scripts;
- render and assembly scripts;
- documentation;
- selected final approved videos.

The repository does not keep generated working files:

- raw generated voice segments;
- Manim cache/output directories;
- silent intermediate videos;
- render snapshots;
- concat temp files;
- secrets.

This keeps the project reproducible without turning Git into a storage dump.

## Current Video

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/
```

Canonical files:

```text
plan.md
script_en.md
segments_en.json
kernel_intro_en.py
kernel_style.py
generate_voice_en.py
render_en.sh
assemble_en.sh
voice_models.md
final/kernel-intro-en-final.mp4
```

The final video is kept because it is the first accepted reference output. Intermediate audio, Manim media, caches, and silent renders are ignored.

## Workflow

For each new video:

1. Define the topic, audience, and teaching goal.
2. Write `plan.md`.
3. Write the narration script.
4. Split the script into `segments_<lang>.json`.
5. Create one Manim scene per segment.
6. Generate the TTS voiceover.
7. Export real audio durations.
8. Synchronize Manim animation timing to those durations.
9. Render a low-quality pass.
10. Fix timing, layout, and visual clarity.
11. Render the final 1080p60 version.
12. Assemble audio and video.
13. Verify with `ffprobe`.
14. Extract and inspect snapshots.
15. Keep only source files and selected final outputs.

## Generate Voice

Preferred final English voice:

```text
Chatterbox main model, non-turbo
```

From the video folder:

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

This creates:

```text
audio/en/durations.json
audio/en/voiceover_en.wav
audio/en/voiceover_en.mp3
```

`audio/` is generated and ignored by Git.

## Render And Assemble

Low-quality iteration:

```bash
QUALITY=ql ./render_en.sh
```

Final render:

```bash
QUALITY=qh ./render_en.sh
```

Assemble:

```bash
./assemble_en.sh
```

Final output:

```text
final/kernel-intro-en-final.mp4
```

## Verify

Run:

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/kernel-intro-en-final.mp4
```

Expected:

- video stream present;
- audio stream present;
- 1920x1080;
- 60 fps;
- H.264 video;
- AAC audio;
- audio and video durations aligned.

Extract visual checks one timestamp at a time:

```bash
mkdir -p renders
ffmpeg -y -ss 00:00:10 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0010.png
ffmpeg -y -ss 00:01:35 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0135.png
ffmpeg -y -ss 00:03:20 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0320.png
ffmpeg -y -ss 00:04:20 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0420.png
```

Check for:

- clipped text;
- labels outside the frame;
- incoherent overlaps;
- blank screens;
- long static scenes;
- mismatch between narration and visuals.

## Documentation For Agents

Before changing or generating a video, read:

```text
AGENTS.md
PROCEDURE.md
```

`AGENTS.md` defines quality rules and project standards.

`PROCEDURE.md` defines the operational pipeline and known pitfalls.

## Dependencies

- Python 3.11.
- `uv`.
- Manim Community Edition.
- `ffmpeg` and `ffprobe`.
- Chatterbox TTS.
- Optional: Darijat TTS API for Arabic/Moroccan voice tests.

## Git Checklist

Before committing:

```bash
git status --short --ignored
git ls-files --others --exclude-standard
```

Commit only source files, documentation, and selected final videos.
