# What is the Linux kernel?

Final English video in the `linux-fondamentaux` series.

This folder contains the source files needed to regenerate the video and the final approved MP4. Intermediate Manim renders, generated voice segments, caches, and verification snapshots are intentionally not kept in the repository.

## Canonical Files

- `plan.md`: final 12-scene plan.
- `script_en.md`: English narration, one section per scene.
- `segments_en.json`: source of truth for TTS segments and scene keys.
- `kernel_intro_en.py`: Manim Community Edition scenes.
- `kernel_style.py`: shared colors and visual helpers.
- `generate_voice_en.py`: Chatterbox/Kokoro voice generation.
- `render_en.sh`: renders the 12 Manim scenes and creates the silent video.
- `assemble_en.sh`: muxes the silent video with the generated voiceover.
- `voice_models.md`: notes about the voice choice.
- `final/kernel-intro-en-final.mp4`: final approved English video.

## Generate Voice

Preferred final voice:

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

This recreates:

```text
audio/en/durations.json
audio/en/voiceover_en.wav
audio/en/voiceover_en.mp3
```

The `audio/` directory is generated and ignored by Git.

## Render

Low-quality iteration:

```bash
QUALITY=ql ./render_en.sh
```

Final render:

```bash
QUALITY=qh ./render_en.sh
```

This recreates:

```text
final/kernel-intro-en-silent.mp4
```

## Assemble

```bash
./assemble_en.sh
```

Final output:

```text
final/kernel-intro-en-final.mp4
```

## Verify

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/kernel-intro-en-final.mp4
```

Expected result:

- video stream present;
- audio stream present;
- 1920x1080;
- 60 fps;
- H.264 video;
- AAC mono audio;
- audio and video durations aligned.

Extract visual checks one timestamp at a time:

```bash
mkdir -p renders
ffmpeg -y -ss 00:00:10 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0010.png
ffmpeg -y -ss 00:01:35 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0135.png
ffmpeg -y -ss 00:03:20 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0320.png
ffmpeg -y -ss 00:04:20 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0420.png
```
