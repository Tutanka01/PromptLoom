#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

QUALITY="${QUALITY:-qm}"
SCENES=(
  Scene1_HookEN
  Scene2_HardwareChaosEN
  Scene3_BoundaryEN
  Scene4_SchedulerEN
  Scene5_MemoryEN
  Scene6_AbstractionsEN
  Scene7_InterruptsEN
  Scene8_DriversEN
  Scene9_ProcessLifecycleEN
  Scene7_ContainersEN
  Scene10_WhatKernelIsNotEN
  Scene8_RecapEN
)

uv run --with manim python -m manim "-${QUALITY}" kernel_intro_en.py "${SCENES[@]}"

QUALITY_DIR="720p30"
if [[ "${QUALITY}" == "ql" ]]; then
  QUALITY_DIR="480p15"
elif [[ "${QUALITY}" == "qh" ]]; then
  QUALITY_DIR="1080p60"
fi

cat > concat_en.txt <<EOF
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene1_HookEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene2_HardwareChaosEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene3_BoundaryEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene4_SchedulerEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene5_MemoryEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene6_AbstractionsEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene7_InterruptsEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene8_DriversEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene9_ProcessLifecycleEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene7_ContainersEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene10_WhatKernelIsNotEN.mp4'
file 'media/videos/kernel_intro_en/${QUALITY_DIR}/Scene8_RecapEN.mp4'
EOF

mkdir -p final
ffmpeg -y -f concat -safe 0 -i concat_en.txt -c copy final/kernel-intro-en-silent.mp4
