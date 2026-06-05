#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

QUALITY="${QUALITY:-qm}"
SCENES=(
  Scene1_HookEN
  Scene2_ConceptEN
  Scene3_RecapEN
)

uv run --with manim python -m manim "-${QUALITY}" video_en.py "${SCENES[@]}"

QUALITY_DIR="720p30"
if [[ "${QUALITY}" == "ql" ]]; then
  QUALITY_DIR="480p15"
elif [[ "${QUALITY}" == "qh" ]]; then
  QUALITY_DIR="1080p60"
fi

cat > concat_en.txt <<EOF
file 'media/videos/video_en/${QUALITY_DIR}/Scene1_HookEN.mp4'
file 'media/videos/video_en/${QUALITY_DIR}/Scene2_ConceptEN.mp4'
file 'media/videos/video_en/${QUALITY_DIR}/Scene3_RecapEN.mp4'
EOF

mkdir -p final
ffmpeg -y -f concat -safe 0 -i concat_en.txt -c copy final/video-en-silent.mp4
