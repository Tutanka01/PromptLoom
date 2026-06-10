from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path


logger = logging.getLogger(__name__)


class CommandExecutionError(RuntimeError):
    def __init__(self, args: list[str], log_name: str, log_path: Path, log_tail: str):
        self.args_list = args
        self.log_name = log_name
        self.log_path = log_path
        self.log_tail = log_tail
        super().__init__(
            f"command failed ({log_name}): {' '.join(args)}\n"
            f"log: {log_path}\n"
            f"tail:\n{log_tail}"
        )


def _tail_text(value: str, limit: int = 6000) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


class CommandRunner:
    def __init__(self, log_dir: Path, timeout_seconds: int):
        self.log_dir = log_dir
        self.timeout_seconds = timeout_seconds
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        args: list[str],
        cwd: Path,
        log_name: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command_env = os.environ.copy()
        if env:
            command_env.update(env)
        log = self.log_dir / log_name
        started = time.monotonic()
        logger.info(
            "command.start name=%s cwd=%s timeout=%ss command=%s",
            log_name,
            cwd,
            self.timeout_seconds,
            " ".join(args),
        )
        # Stream both pipes into the log file AS THE COMMAND RUNS, so a long
        # render can be followed with `tail -f` instead of producing its log
        # only after completion. stdout/stderr are still captured separately —
        # verify parses ffprobe stdout and freezedetect stderr.
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        log_lock = threading.Lock()
        with log.open("w", encoding="utf-8") as log_file:
            log_file.write("$ " + " ".join(args) + "\n\n")
            log_file.flush()

            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=command_env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            def _pump(stream, sink: list[str], prefix: str) -> None:
                for line in iter(stream.readline, ""):
                    sink.append(line)
                    with log_lock:
                        log_file.write(prefix + line)
                        log_file.flush()
                stream.close()

            readers = [
                threading.Thread(target=_pump, args=(process.stdout, stdout_lines, ""), daemon=True),
                threading.Thread(target=_pump, args=(process.stderr, stderr_lines, ""), daemon=True),
            ]
            for reader in readers:
                reader.start()
            try:
                returncode = process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                for reader in readers:
                    reader.join(timeout=5)
                raise
            for reader in readers:
                reader.join(timeout=10)

        result = subprocess.CompletedProcess(
            args=args,
            returncode=returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )
        elapsed = time.monotonic() - started
        if result.returncode != 0:
            logger.error(
                "command.failed name=%s returncode=%s elapsed=%.2fs log=%s",
                log_name,
                result.returncode,
                elapsed,
                log,
            )
            raise CommandExecutionError(args, log_name, log, _tail_text(log.read_text(encoding="utf-8")))
        logger.info(
            "command.done name=%s returncode=%s elapsed=%.2fs log=%s stdout_chars=%d stderr_chars=%d",
            log_name,
            result.returncode,
            elapsed,
            log,
            len(result.stdout),
            len(result.stderr),
        )
        return result
