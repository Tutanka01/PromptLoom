# What is a syscall?

## Overview

- **Topic**: Linux system calls, from user code to kernel work and back.
- **Audience**: Developers or Linux learners who know what programs and files are, but not how user space crosses into the kernel.
- **Estimated length**: 7 to 9 minutes.
- **Core insight**: A syscall is a controlled transition, not just a function call. It is the narrow, privileged API through which user programs ask the kernel to do protected work.
- **Format**: English narration, 16:9, Manim Community Edition, final render 1080p60.

## Narrative Arc

The video starts with a familiar command that appears simple, then reveals the hidden trip through user space, CPU privilege modes, the syscall instruction, kernel dispatch, validation, and return values. It then expands into practical syscall families: files, permissions, blocking I/O, processes, memory, networking, tracing, sandboxing, and performance.

## Scene Breakdown

1. **Hook: a command is not direct**
   - Show `cat notes.txt` flowing through app, libc, syscall gate, kernel, storage.
   - Establish that the app asks; the kernel performs protected work.

2. **User mode and kernel mode**
   - Split screen into user space and kernel space.
   - Show CPU privilege changing through a controlled gate.

3. **Syscall is not a normal function call**
   - Compare a normal call stack with the special syscall path.
   - Show registers, syscall number, arguments, and return.

4. **The syscall table**
   - Map numbers like `read`, `write`, `openat`, `clone`, `mmap` to handlers.
   - Emphasize stable ABI and kernel validation.

5. **Files and file descriptors**
   - Show `openat`, fd `3`, `read`, `write`, VFS, driver, disk.
   - Explain file descriptors as small process-local handles.

6. **Permissions and errors**
   - Show UID, path, flags, credentials, LSM/policy checks.
   - Return success or `-EACCES` / `errno`.

7. **Blocking, sleeping, waking**
   - Show a process blocked in `read`, scheduler running another process, interrupt waking it.

8. **Process syscalls**
   - Show `fork`, `execve`, `wait`, `exit`, process table, PID, memory map, fd table.

9. **Memory syscalls and page faults**
   - Show `mmap`, `brk`, virtual pages, page table, RAM, lazy allocation.

10. **Network syscalls**
    - Show `socket`, `connect`, `send`, `recv`, kernel network stack, NIC.

11. **Observability, sandboxing, and cost**
    - Show `strace`, `seccomp`, and context-switch overhead.
    - Mention batching and async interfaces without derailing the video.

12. **Recap**
    - Summarize: program, libc wrapper, syscall number, trap, kernel handler, checked work, result.

## Visual Rules

- One scene per audio segment.
- No scene should show generic kernel imagery while the narration discusses a specific syscall mechanism.
- Use a consistent color language:
  - blue: user space and programs;
  - yellow: kernel/syscall gate;
  - green: memory and successful returns;
  - orange/red: errors, privilege, interrupts;
  - gray: hardware.
- Keep labels short and inside stable boxes.
- Avoid static screens: every scene must introduce or transform at least one concept while the voiceover progresses.
