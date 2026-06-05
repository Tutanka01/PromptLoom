#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VIDEO="${VIDEO:-final/syscall-intro-en-silent.mp4}"
AUDIO="${AUDIO:-audio/en/voiceover_en.mp3}"
OUTPUT="${OUTPUT:-final/syscall-intro-en-final.mp4}"

ffmpeg -y \
  -i "${VIDEO}" \
  -i "${AUDIO}" \
  -map 0:v:0 \
  -map 1:a:0 \
  -c:v copy \
  -c:a aac \
  -b:a 192k \
  -shortest \
  "${OUTPUT}"

echo "Wrote ${OUTPUT}"
