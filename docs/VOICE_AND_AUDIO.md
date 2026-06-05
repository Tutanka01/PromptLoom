# Voice And Audio

This project uses local TTS for final videos. The preferred voice is Chatterbox main, non-turbo.

## Preferred Command

Run from the video folder:

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

## Rules

- Do not use macOS `say` for a final video.
- Do not switch to Chatterbox Turbo without asking the user.
- Do not regenerate accepted voice files unless the segment text changes or the user asks for it.
- If only one segment changes, regenerate only what is necessary when the local script supports it.
- `audio/en/durations.json` is generated from real audio durations and drives Manim synchronization.
- The global voiceover must include the same end padding that Manim expects.

## Generated Files

Expected output:

```text
audio/en/durations.json
audio/en/voiceover_en.wav
audio/en/voiceover_en.mp3
```

`audio/` is a generated working directory and is ignored by Git.

## Fallback Engines

Fallbacks may exist in `generate_voice_en.py`:

- `--engine chatterbox-turbo`: faster, not the preferred final quality.
- `--engine kokoro`: lightweight fallback for quick tests.

Use fallbacks only for tests or after user approval.

## Verification

Check durations:

```bash
cat audio/en/durations.json
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 audio/en/voiceover_en.mp3
```

Expected:

- every scene key exists in `durations.json`;
- no duration is zero;
- the sum of scene durations is close to the global voiceover duration;
- final MP4 audio and video durations match after assembly.

Final MP4 check:

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<slug>-en-final.mp4
```

Expected final audio:

- AAC;
- mono is acceptable;
- duration aligned with video;
- no muted or abnormally short stream.
