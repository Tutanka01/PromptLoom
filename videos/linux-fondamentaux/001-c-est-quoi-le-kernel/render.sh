#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

QUALITY="${QUALITY:-qm}"
SCENES=(
  Scene1_Hook
  Scene2_HardwareChaos
  Scene3_UserKernelBoundary
  Scene4_Scheduler
  Scene5_VirtualMemory
  Scene6_FilesNetworkDrivers
  Scene7_Containers
  Scene8_Recap
)

uv run --with manim python -m manim "-${QUALITY}" kernel_intro.py "${SCENES[@]}"

QUALITY_DIR="720p30"
if [[ "${QUALITY}" == "ql" ]]; then
  QUALITY_DIR="480p15"
elif [[ "${QUALITY}" == "qh" ]]; then
  QUALITY_DIR="1080p60"
fi

cat > concat.txt <<EOF
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene1_Hook.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene2_HardwareChaos.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene3_UserKernelBoundary.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene4_Scheduler.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene5_VirtualMemory.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene6_FilesNetworkDrivers.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene7_Containers.mp4'
file 'media/videos/kernel_intro/${QUALITY_DIR}/Scene8_Recap.mp4'
EOF

mkdir -p final
ffmpeg -y -f concat -safe 0 -i concat.txt -c copy final/kernel-intro-silent.mp4
