from __future__ import annotations

import sys

import pytest

from video_api.pipeline.commands import CommandExecutionError, CommandRunner


def test_command_failure_includes_log_tail(tmp_path) -> None:
    runner = CommandRunner(tmp_path / "logs", timeout_seconds=10)

    with pytest.raises(CommandExecutionError) as exc_info:
        runner.run(
            [
                sys.executable,
                "-c",
                "import sys; print('stdout marker'); print('stderr marker', file=sys.stderr); sys.exit(3)",
            ],
            cwd=tmp_path,
            log_name="failed.log",
        )

    assert "failed.log" in str(exc_info.value)
    assert "stdout marker" in exc_info.value.log_tail
    assert "stderr marker" in exc_info.value.log_tail
