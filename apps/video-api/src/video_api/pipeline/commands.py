from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path


logger = logging.getLogger(__name__)


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
            raise RuntimeError(f"command failed ({log_name}): {' '.join(args)}")
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
