from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from code_agent.observability import Timer


class TestRunResult(BaseModel):
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    attempts: int
    summary: str

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


class TestRunner:
    __test__ = False

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def run(
        self,
        command: str,
        *,
        max_attempts: int = 1,
        fix_callback: Callable[[TestRunResult], None] | None = None,
        timeout_seconds: int = 120,
    ) -> TestRunResult:
        attempts = max(1, max_attempts)
        last: TestRunResult | None = None
        for attempt in range(1, attempts + 1):
            last = self._run_once(command, attempt=attempt, timeout_seconds=timeout_seconds)
            if last.passed or attempt == attempts:
                return last
            if fix_callback is not None:
                fix_callback(last)
        assert last is not None
        return last

    def _run_once(self, command: str, *, attempt: int, timeout_seconds: int) -> TestRunResult:
        timer = Timer()
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            exit_code = 124
            stderr = f"{stderr}\nCommand timed out after {timeout_seconds}s".strip()
        return TestRunResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=timer.elapsed_ms(),
            attempts=attempt,
            summary=summarize_test_failure(stdout, stderr, exit_code),
        )


def summarize_test_failure(stdout: str, stderr: str, exit_code: int, *, max_lines: int = 20) -> str:
    if exit_code == 0:
        return "Tests passed."
    combined = f"{stdout}\n{stderr}"
    markers = ("FAILED", "ERROR", "AssertionError", "Traceback", "E   ", "Command timed out")
    selected = [line.rstrip() for line in combined.splitlines() if any(marker in line for marker in markers)]
    if not selected:
        selected = [line.rstrip() for line in combined.splitlines() if line.strip()][-max_lines:]
    return "\n".join(selected[:max_lines]) or f"Command failed with exit code {exit_code}."
