# Script - What is the Linux kernel?

This is the synchronized English V2. Each paragraph maps to one Manim scene and one generated audio file.

## Scene 1 - Hook
Open an app. Click a file. The image appears. It feels direct, but it is not. Your app never talks straight to the disk, the CPU, or memory. Every request goes through layers. Between ordinary programs and the real machine sits a privileged layer: the Linux kernel. The whole video is about that invisible layer, and why modern computers depend on it.

## Scene 2 - Why the kernel exists
Raw hardware is powerful, but unsafe. If every program could drive every device directly, each program would need to understand every disk controller, network card, and memory rule. One bug could overwrite memory, steal another program's data, or keep the CPU forever. Without a trusted arbiter, the machine would be fast, but fragile. The kernel exists because programs need rules before they touch hardware.

## Scene 3 - User space and kernel space
Normal programs run in user space. Sensitive operations happen in kernel space. The border matters, because the kernel has privileges that applications do not. To cross the border, a program makes a system call. A syscall is not magic, and it is not a shortcut around security. It is a controlled request: open this file, allocate memory, send this packet, start this process. The kernel checks the request, performs the dangerous part, and returns a result.

## Scene 4 - The scheduler
A CPU core executes one stream of instructions at a time. But your computer feels like many things are running together: a browser, a terminal, music, background services. The scheduler creates that illusion by slicing CPU time into tiny pieces and giving those pieces to different processes. It decides who runs next, for how long, and with what priority. Multitasking is not chaos. It is a very fast negotiation managed by the kernel.

## Scene 5 - Virtual memory
The kernel also protects memory. Each process sees a private virtual address space, as if it owned a clean, continuous block of memory. But that view is an abstraction. Two programs can use the same address, while the hardware and kernel translate those addresses to different physical locations. The kernel also marks some regions as protected. That is how one crashing program does not automatically destroy the rest of the system.

## Scene 6 - Files, sockets, devices
The kernel turns messy hardware into stable abstractions. A spinning disk, an SSD, a USB drive, or a network filesystem can all look like files. A network card becomes sockets. Devices become interfaces that programs can use without knowing every electrical detail. This is one of the kernel's biggest tricks: it hides hardware differences behind concepts that developers can reason about.

## Scene 7 - Interrupts
The kernel is also how the machine reacts to events. Hardware does not politely wait for a program to ask a question. A network packet arrives. A key is pressed. A timer fires. A disk operation finishes. Devices signal the CPU with interrupts, and the CPU temporarily jumps into kernel code. The kernel records what happened, wakes the right process, and returns control. That is why the system can feel responsive even while many programs are asleep.

## Scene 8 - Drivers
Drivers are the kernel's translators for real devices. A program should not need to know the exact command sequence for a graphics card, an NVMe drive, or a Wi-Fi adapter. The driver knows the device-specific protocol. The rest of the kernel exposes a stable interface above it. This separation is powerful, but it is also risky: driver code runs with high privilege. A bad driver can crash the whole system, which is why kernel code is treated so carefully.

## Scene 9 - Processes
When you start a command, the kernel creates and tracks a process. It assigns an identifier, gives it memory mappings, connects file descriptors like standard input and output, and decides when it can run. On Unix-like systems, process creation often uses fork and exec: copy the current process shape, then replace its program image with a new executable. From the outside it feels like launching an app. Inside the kernel, it is bookkeeping, memory management, permissions, and scheduling all at once.

## Scene 10 - Containers
This is also why containers are kernel features. A container is not a tiny virtual machine with its own Linux kernel. Most of the time, it is a set of isolated processes on the same kernel as everything else. Namespaces control what those processes can see: process IDs, networks, mounts, hostnames. Cgroups control what they can consume: CPU, memory, and I/O. Docker feels high level, but the isolation comes from the kernel.

## Scene 11 - What the kernel is not
The kernel is not the whole operating system. It is not the shell, not the desktop, not your package manager, and not the Linux distribution brand. Ubuntu, Arch, Fedora, Debian, and Android combine a Linux kernel with many user-space tools and policies. That distinction matters. When people say Linux, they may mean the kernel, or they may mean a complete system built around it. For this video, kernel means the privileged core that mediates access to hardware.

## Scene 12 - Recap
So the kernel is the privileged core that protects, shares, and abstracts the machine. It protects programs from each other. It shares CPU, memory, and devices. And it turns raw hardware into simple ideas: processes, files, sockets, and virtual memory. The next time a command opens a file, starts a process, or sends a packet, remember the hidden path: application, syscall, kernel, hardware, and back.
