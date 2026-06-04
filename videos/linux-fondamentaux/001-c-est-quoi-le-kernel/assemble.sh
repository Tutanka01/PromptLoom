#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VIDEO="${VIDEO:-final/kernel-intro-silent.mp4}"
AUDIO="${AUDIO:-audio/voiceover.mp3}"
OUTPUT="${OUTPUT:-final/kernel-intro-final.mp4}"

if [[ ! -f "${VIDEO}" ]]; then
  echo "Missing video: ${VIDEO}" >&2
  exit 1
fi

if [[ ! -f "${AUDIO}" ]]; then
  echo "Missing audio: ${AUDIO}" >&2
  exit 1
fi

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
