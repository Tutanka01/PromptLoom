# What is the Linux kernel?

## Overview

- **Topic**: The Linux kernel as the privileged core of the operating system.
- **Audience**: Developers, junior system administrators, and curious Linux users who need a clear mental model of what the kernel does.
- **Language**: English.
- **Final duration**: About 4 minutes 35 seconds.
- **Final video**: `final/kernel-intro-en-final.mp4`.
- **Rendering target**: 1920x1080, 60 fps.
- **Voice**: Chatterbox main model, non-turbo.

## Core Idea

Applications do not talk directly to the CPU, memory, disks, network cards, or devices. They make controlled requests. The Linux kernel is the privileged layer that checks those requests, manages resources, protects processes from each other, and turns messy hardware into stable abstractions.

The video should always keep voice and image aligned: when the narration explains scheduling, the image shows CPU time sharing; when it explains virtual memory, the image shows virtual addresses, translation, and RAM; when it explains containers, the image shows namespaces and cgroups on the same shared kernel.

## Scene Plan

### Scene 1 - Hook

**Key**: `Scene1_HookEN`

**Purpose**: Establish that a simple user action hides a deeper path through the system.

**Visuals**:

- Application window.
- File request.
- Layered reveal: application, kernel, hardware.

**Narrative beat**: An app opening a file feels direct, but every meaningful request passes through the Linux kernel.

### Scene 2 - Why the kernel exists

**Key**: `Scene2_HardwareChaosEN`

**Purpose**: Show why direct hardware access by every program would be unsafe.

**Visuals**:

- Multiple programs competing for CPU, memory, disk, and network.
- Chaotic red arrows.
- Kernel appears as trusted arbiter.

**Narrative beat**: Without the kernel, a single buggy program could corrupt memory, monopolize CPU time, or damage another program's data.

### Scene 3 - User space and kernel space

**Key**: `Scene3_BoundaryEN`

**Purpose**: Explain the privilege boundary and syscalls.

**Visuals**:

- User space above.
- Kernel space below.
- Controlled syscall gate.

**Narrative beat**: A syscall is a controlled request, not a shortcut around security.

### Scene 4 - The scheduler

**Key**: `Scene4_SchedulerEN`

**Purpose**: Explain how the kernel shares CPU time.

**Visuals**:

- Process queue.
- CPU core.
- Time slices moving between processes.

**Narrative beat**: Multitasking is a fast negotiation managed by the kernel scheduler.

### Scene 5 - Virtual memory

**Key**: `Scene5_MemoryEN`

**Purpose**: Show that each process sees a private virtual address space.

**Visuals**:

- Two processes with matching virtual addresses.
- Translation table.
- Different physical RAM blocks.
- Protected kernel region.

**Narrative beat**: The kernel and hardware translate virtual addresses and prevent one process from freely reading or writing another process's memory.

### Scene 6 - Files, sockets, devices

**Key**: `Scene6_AbstractionsEN`

**Purpose**: Explain the kernel's stable abstractions over varied hardware.

**Visuals**:

- Kernel in the center.
- Files, sockets, and devices as interface cards.
- Disk, network, and peripheral blocks underneath.

**Narrative beat**: The kernel hides hardware differences behind concepts developers can reason about.

### Scene 7 - Interrupts

**Key**: `Scene7_InterruptsEN`

**Purpose**: Explain how the system reacts to hardware events.

**Visuals**:

- Keyboard, network, disk, and timer events.
- Interrupt signal into CPU/kernel.
- Kernel wakes the correct process.

**Narrative beat**: Hardware can interrupt the CPU; the kernel records the event, handles it, and returns control.

### Scene 8 - Drivers

**Key**: `Scene8_DriversEN`

**Purpose**: Explain drivers as device-specific translators inside or near kernel space.

**Visuals**:

- Device-specific hardware blocks.
- Driver layer.
- Stable interface exposed upward.

**Narrative beat**: Drivers make real hardware usable through stable interfaces, but privileged driver code must be treated carefully.

### Scene 9 - Processes

**Key**: `Scene9_ProcessLifecycleEN`

**Purpose**: Explain what the kernel creates and tracks when a program starts.

**Visuals**:

- Process ID.
- Memory mappings.
- File descriptors.
- Scheduling state.
- `fork` and `exec` path.

**Narrative beat**: Launching an app is kernel bookkeeping, permissions, memory management, and scheduling all at once.

### Scene 10 - Containers

**Key**: `Scene7_ContainersEN`

**Purpose**: Connect modern containers to kernel features.

**Visuals**:

- Multiple containers on one shared kernel.
- Namespaces for what processes can see.
- Cgroups for what processes can consume.

**Narrative beat**: Containers are usually isolated processes on the same Linux kernel, not tiny virtual machines with their own kernel.

### Scene 11 - What the kernel is not

**Key**: `Scene10_WhatKernelIsNotEN`

**Purpose**: Separate the kernel from the full operating system and distribution.

**Visuals**:

- Kernel core separated from shell, desktop, package manager, and distro branding.
- Linux distributions shown as complete systems around the kernel.

**Narrative beat**: Linux can mean the kernel or a complete system built around it; this video uses kernel to mean the privileged core.

### Scene 12 - Recap

**Key**: `Scene8_RecapEN`

**Purpose**: Anchor the final definition.

**Visuals**:

- Layered path: application, syscall, kernel, hardware, back.
- Three verbs: protect, share, abstract.

**Narrative beat**: The kernel protects programs, shares resources, and abstracts hardware into processes, files, sockets, and virtual memory.

## Visual Language

- User-space programs: blue.
- Kernel: yellow/gold.
- Hardware: dark gray.
- Danger/contention: orange/red.
- Memory/resources: green.
- Background: dark neutral.

The kernel should remain visually central or act as a boundary in most scenes, so the viewer builds a stable mental model of it as the mediator between applications and hardware.

## Final Verification Target

The final MP4 must contain:

- H.264 video.
- AAC audio.
- 1920x1080 resolution.
- 60 fps.
- Audio and video durations aligned.
- No empty scenes, clipped text, or incoherent overlaps in snapshot checks.
