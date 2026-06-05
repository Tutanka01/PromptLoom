#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

ffmpeg -y \
  -i final/video-en-silent.mp4 \
  -i audio/en/voiceover_en.mp3 \
  -map 0:v:0 \
  -map 1:a:0 \
  -c:v copy \
  -c:a aac \
  -shortest \
  final/video-en-final.mp4

echo "Wrote final/video-en-final.mp4"
