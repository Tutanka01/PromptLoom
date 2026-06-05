# Video Boilerplate

Copy this boilerplate when starting a new video.

Documentation target:

```text
docs/videos/<theme>/<number-slug>/
```

Production target:

```text
videos/<theme>/<number-slug>/
```

Recommended command:

```bash
mkdir -p videos/<theme>/<number-slug>
mkdir -p docs/videos/<theme>/<number-slug>
cp -R docs/boilerplate/video/. videos/<theme>/<number-slug>/
cp -R docs/boilerplate/docs/. docs/videos/<theme>/<number-slug>/
```

Then rename:

```text
video_en.py      -> <slug>_en.py
video_style.py   -> <slug>_style.py
```

Update imports in `<slug>_en.py` after renaming the style file, and update `render_en.sh` so it renders the renamed Manim file and writes the final files with the chosen slug.

## Files

- `plan.md`: planning template.
- `script.md`: narration template.
- `video/segments_en.json`: TTS segment template.
- `video/beats_en.json`: narrative beat template.
- `video/video_en.py`: Manim v2 sync template.
- `video/video_style.py`: visual style template.
- `video/generate_voice_en.py`: placeholder explaining where to copy/adapt the generator.
- `video/render_en.sh`: render template.
- `video/assemble_en.sh`: assembly template.

## Rules

- Keep reusable documentation in `docs/`.
- Keep video-specific narrative docs in `docs/videos/...`.
- Keep production sources in `videos/...`.
- One segment means one Manim scene.
- `durations.json` gives total scene duration.
- `beats_en.json` gives internal visual timing.
- Verify with `ffprobe`, `freezedetect`, and snapshots before delivery.
