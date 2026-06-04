# Voice Notes

The final English video uses the main Chatterbox model, not Chatterbox Turbo.

Preferred command:

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

Notes:

- Chatterbox main is slower than Turbo, but it produced the preferred voice quality for the final version.
- Do not regenerate accepted voice files unless the segment text changes.
- If only one segment changes, regenerate only what is necessary when possible.
- `audio/en/durations.json` is generated from the real audio durations and drives Manim synchronization.
- `audio/` is not committed; it is regenerated from `segments_en.json`.

Fallbacks available in `generate_voice_en.py`:

- `--engine chatterbox-turbo`: faster, lower preferred quality.
- `--engine kokoro`: lightweight fallback for quick tests.
