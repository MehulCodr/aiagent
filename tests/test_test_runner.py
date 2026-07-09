from __future__ import annotations

import sys
from pathlib import Path

from code_agent.test_runner import TestRunner


def test_test_runner_summarizes_failures_and_stops_after_max_attempts(tmp_path: Path) -> None:
    command = f'"{sys.executable}" -c "import sys; print(\'FAILED sample\'); sys.exit(1)"'
    callbacks = []

    result = TestRunner(tmp_path).run(command, max_attempts=2, fix_callback=lambda failure: callbacks.append(failure))

    assert not result.passed
    assert result.attempts == 2
    assert len(callbacks) == 1
    assert "FAILED sample" in result.summary


def test_test_runner_reports_success(tmp_path: Path) -> None:
    command = f'"{sys.executable}" -c "print(\'ok\')"'
    result = TestRunner(tmp_path).run(command)

    assert result.passed
    assert result.summary == "Tests passed."
