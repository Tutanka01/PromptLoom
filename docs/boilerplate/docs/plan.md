# <Video Title>

## Overview

- **Topic**: <what this video explains>
- **Audience**: <who this is for>
- **Prerequisites**: <what the viewer should already know>
- **Estimated length**: <target length>
- **Core insight**: <the main aha moment>
- **Format**: English narration, 16:9, Manim Community Edition, final 1080p60.

## Narrative Arc

<Explain the journey from the opening hook to the final mental model.>

## Scene Breakdown

1. **Scene 1 title**
   - Purpose: <what this scene teaches>
   - Visual: <what appears on screen>
   - Beat idea: <how the image changes with the narration>

2. **Scene 2 title**
   - Purpose: <what this scene teaches>
   - Visual: <what appears on screen>
   - Beat idea: <how the image changes with the narration>

## Visual Rules

- One active concept at a time.
- Use progressive disclosure.
- Keep labels short and inside stable boxes.
- Use focus/dim/flow markers instead of repeated decorative outlines.
- Make the visual match the narration at each beat.
- Avoid long static tails.

## Verification Standard

- Render low quality first: `QUALITY=ql ./render_en.sh`.
- Assemble before judging timing: `./assemble_en.sh`.
- Run `ffprobe` on the final MP4.
- Run `freezedetect`.
- Extract and inspect snapshots.
- Render final quality only after the low-quality pass is clean.
