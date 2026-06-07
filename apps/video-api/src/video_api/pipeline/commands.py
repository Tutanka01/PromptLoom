from __future__ import annotations

import logging
import os
import subprocess
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
        result = subprocess.run(
            args,
            cwd=cwd,
            env=command_env,
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
        )
        elapsed = time.monotonic() - started
        log.write_text(
            "$ " + " ".join(args) + "\n\n"
            + "STDOUT\n"
            + result.stdout
            + "\nSTDERR\n"
            + result.stderr,
            encoding="utf-8",
        )
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
