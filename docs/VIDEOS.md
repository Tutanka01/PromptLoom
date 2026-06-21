# Video Registry

Historical registry for the hand-produced Linux videos that inspired the
platform. API-generated jobs live in `/data/jobs` and are not listed here.

Detailed production docs stay here, not inside the video folders.

## PromptLoom Showcase

Videos exposed at the top of the repository README:

```text
videos/examples/français-exemple.mp4
videos/examples/espagnol-exemple.mp4
```

Both are 1920x1080 at 30 fps with H.264 video and AAC audio. The French example
runs for 4 min 27; the Spanish example runs for 5 min 30. Their README preview
images live in `docs/assets/examples/`.

## Linux Fondamentaux 001: What Is The Linux Kernel?

Folder:

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/
```

Narrative docs:

```text
docs/videos/linux-fondamentaux/001-c-est-quoi-le-kernel/plan.md
docs/videos/linux-fondamentaux/001-c-est-quoi-le-kernel/script_en.md
```

Final MP4:

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4
```

Status:

- accepted historical reference;
- uses Chatterbox main non-turbo;
- uses real audio durations;
- predates the full `beats_en.json` v2 workflow.

Notes:

- keep as pipeline reference;
- do not use its old documentation layout as a model;
- future updates should migrate it to `beats_en.json` if the video is reworked.

## Linux Fondamentaux 002: What Is A Syscall?

Folder:

```text
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/
```

Narrative docs:

```text
docs/videos/linux-fondamentaux/002-c-est-quoi-un-syscall/plan.md
docs/videos/linux-fondamentaux/002-c-est-quoi-un-syscall/script.md
```

Final MP4:

```text
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/final/syscall-intro-en-final.mp4
```

Status:

- first v2 reference;
- `beats_en.json` exists;
- scenes 1 and 2 are visual/timing pilots;
- scenes 3-12 have improved beat-spread timing but are not fully redesigned yet.

Last known final verification:

```text
1920x1080, 60 fps, H.264 video, AAC mono audio
video duration: 296.833333 s
audio duration: 296.832000 s
freezedetect summary: freezes=17 total=74.32 avg=4.37
```

Next polish target:

- extend `beats_en.json` to scenes 3-12;
- bring scenes 3-12 up to the visual standard of scenes 1 and 2.
