# What is a syscall?

## Scene 1 - Hook: a command is not direct

Run a tiny command: cat notes dot txt. It feels like the program simply opens a file and prints bytes. But a normal program is not allowed to command the disk, rewrite page tables, or send packets directly. It lives in user space, with limited privileges. So when it needs protected work, it asks the kernel through a system call. A syscall is the controlled doorway between ordinary code and the privileged core of the operating system.

## Scene 2 - User mode and kernel mode

Modern CPUs support different privilege levels. Your browser, shell, editor, and database run in user mode. The kernel runs in kernel mode, where it can access hardware, manage memory, schedule threads, and enforce isolation. The border is deliberate. If a program could just jump into kernel memory, a bug or exploit could own the machine. A syscall crosses the border only through a CPU-defined entry path, then returns back to user mode.

## Scene 3 - Syscall is not a normal function call

A normal function call stays inside the same process: push a return address, run code, return. A syscall is different. A wrapper, often in libc, places a syscall number and arguments in CPU registers, then executes a special instruction such as syscall on x eighty six sixty four. The CPU switches context to a kernel entry point. The kernel reads the number, finds the handler, performs checked work, and places the result back where user code can read it.

## Scene 4 - The syscall table

Inside the kernel, syscall numbers are dispatched through a table. Number zero might mean read on one architecture, number one might mean write, and another number means openat, mmap, clone, or execve. This table is part of the user-kernel ABI, so it changes very carefully. Programs do not get arbitrary kernel functions. They get a documented list of entry points, each with expected arguments, validation rules, and a return convention.

## Scene 5 - Files and file descriptors

File syscalls make the idea concrete. Openat asks the kernel to resolve a path and create an open file description. If that succeeds, the process receives a small integer, often three, called a file descriptor. Later, read and write use that descriptor instead of the path. The descriptor points through the process table into kernel state, then into the virtual filesystem, a filesystem implementation, drivers, and eventually storage. The application sees bytes; the kernel manages the route.

## Scene 6 - Permissions and errors

Every syscall is also a checkpoint. For openat, the kernel checks the process credentials, the requested flags, mount options, file permissions, and security modules. For kill, it checks whether one process may signal another. For ptrace, it checks a much stricter debugging permission. If the request is allowed, the kernel returns a non-negative result. If not, it returns an error code such as access denied. User libraries translate that into errno.

## Scene 7 - Blocking, sleeping, waking

Syscalls also explain why programs can wait without burning the CPU. Imagine a process calls read on a socket, but no packet has arrived. The kernel can mark that process as sleeping and let the scheduler run something else. Later, a network interrupt arrives. The kernel handles the packet, marks the sleeping process runnable again, and read finally returns. To the program, read looked like one call. Inside the kernel, it involved queues, interrupts, and scheduling.

## Scene 8 - Process syscalls

Processes are built with syscalls too. On Unix-like systems, fork or clone creates a new process shape. Execve replaces that process image with a new program. Wait lets a parent collect the child status. Exit tears the process down. Around those calls, the kernel tracks PIDs, credentials, memory maps, file descriptor tables, signal state, priorities, and accounting. Starting a program is not a shell trick. It is a negotiated construction of kernel-managed objects.

## Scene 9 - Memory syscalls and page faults

Memory management uses syscalls and traps together. Mmap asks for a mapping: maybe anonymous memory, maybe a file mapped into the address space. Brk moves the process heap boundary. But the kernel often does not allocate every physical page immediately. It records the mapping, updates page tables, and waits. When the process touches a missing page, a page fault brings the kernel back in to allocate memory, load data, or reject invalid access.

## Scene 10 - Network syscalls

Networking is another syscall surface. Socket creates an endpoint. Connect asks the kernel network stack to reach a peer. Send copies bytes from user memory into kernel buffers. Recv copies data back when packets arrive. Under that simple API are protocols, routing, congestion control, device drivers, and interrupts from the network card. A web request may look like application logic, but every packet crosses the user-kernel boundary through syscalls.

## Scene 11 - Observability, sandboxing, and cost

Because syscalls are the boundary, they are useful places to observe and control software. Strace shows the syscalls a process makes and the results it gets. Seccomp can restrict which syscalls are allowed, which is why containers and sandboxes care about syscall filters. But crossing the boundary has a cost: registers must be saved, privilege changes, checks run, and data may be copied. Fast programs reduce unnecessary syscalls, batch work, or use newer interfaces when that matters.

## Scene 12 - Recap

So a syscall is the kernel's public doorway for protected operations. User code usually calls a library wrapper. The wrapper loads a syscall number and arguments. The CPU enters the kernel through a controlled path. The kernel dispatches a handler, validates the request, touches protected resources if allowed, and returns a result or an error. Files, processes, memory, networking, clocks, signals, and permissions all meet at this boundary. Understand syscalls, and Linux stops feeling like a black box.
