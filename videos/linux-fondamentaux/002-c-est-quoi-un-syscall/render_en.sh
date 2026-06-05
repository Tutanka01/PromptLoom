#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

QUALITY="${QUALITY:-qm}"
SCENES=(
  Scene1_HookEN
  Scene2_PrivilegeBoundaryEN
  Scene3_NotAFunctionCallEN
  Scene4_SyscallTableEN
  Scene5_FileDescriptorsEN
  Scene6_PermissionsErrorsEN
  Scene7_BlockingWakeupsEN
  Scene8_ProcessSyscallsEN
  Scene9_MemorySyscallsEN
  Scene10_NetworkSyscallsEN
  Scene11_ObserveControlCostEN
  Scene12_RecapEN
)

uv run --with manim python -m manim "-${QUALITY}" syscall_intro_en.py "${SCENES[@]}"

QUALITY_DIR="720p30"
if [[ "${QUALITY}" == "ql" ]]; then
  QUALITY_DIR="480p15"
elif [[ "${QUALITY}" == "qh" ]]; then
  QUALITY_DIR="1080p60"
fi

cat > concat_en.txt <<EOF
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene1_HookEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene2_PrivilegeBoundaryEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene3_NotAFunctionCallEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene4_SyscallTableEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene5_FileDescriptorsEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene6_PermissionsErrorsEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene7_BlockingWakeupsEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene8_ProcessSyscallsEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene9_MemorySyscallsEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene10_NetworkSyscallsEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene11_ObserveControlCostEN.mp4'
file 'media/videos/syscall_intro_en/${QUALITY_DIR}/Scene12_RecapEN.mp4'
EOF

mkdir -p final
ffmpeg -y -f concat -safe 0 -i concat_en.txt -c copy final/syscall-intro-en-silent.mp4
