from __future__ import annotations

import subprocess
from pathlib import Path

from code_agent.git_workflow import GitWorkflow


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_git_workflow_branch_snapshot_and_rollback(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    _git(tmp_path, "checkout", "-b", "dev")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "tracked.txt").write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    _git(tmp_path, "commit", "-m", "init")

    workflow = GitWorkflow(tmp_path)
    workflow.ensure_branch("dev")
    snapshot = workflow.capture_snapshot()

    (tmp_path / "tracked.txt").write_text("after\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")
    workflow.rollback(snapshot)

    assert (tmp_path / "tracked.txt").read_text(encoding="utf-8") == "before\n"
    assert not (tmp_path / "new.txt").exists()
