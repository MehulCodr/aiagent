from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field

from code_agent.config import agent_dir
from code_agent.context import EXCLUDED_NAMES


class SnapshotFile(BaseModel):
    path: str
    content_b64: str


class WorkspaceSnapshot(BaseModel):
    files: list[SnapshotFile] = Field(default_factory=list)

    def file_map(self) -> dict[str, bytes]:
        return {item.path: base64.b64decode(item.content_b64.encode("ascii")) for item in self.files}


class GitWorkflow:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.snapshot_path = agent_dir(self.root) / "rollback" / "last_snapshot.json"

    def current_branch(self) -> str:
        return self._git(["branch", "--show-current"]).strip()

    def ensure_branch(self, branch: str) -> None:
        current = self.current_branch()
        if current != branch:
            raise RuntimeError(f"Expected git branch '{branch}', got '{current}'.")

    def status_short(self) -> str:
        return self._git(["status", "--short"])

    def capture_snapshot(self) -> WorkspaceSnapshot:
        paths = self._workspace_paths()
        files: list[SnapshotFile] = []
        for rel in paths:
            path = self.root / rel
            if not path.is_file() or _is_ignored(Path(rel)):
                continue
            content = base64.b64encode(path.read_bytes()).decode("ascii")
            files.append(SnapshotFile(path=rel, content_b64=content))
        return WorkspaceSnapshot(files=files)

    def save_snapshot(self, snapshot: WorkspaceSnapshot | None = None) -> Path:
        snapshot = snapshot or self.capture_snapshot()
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        self.snapshot_path.write_text(snapshot.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return self.snapshot_path

    def load_snapshot(self) -> WorkspaceSnapshot:
        if not self.snapshot_path.exists():
            raise FileNotFoundError("No rollback snapshot found.")
        return WorkspaceSnapshot.model_validate_json(self.snapshot_path.read_text(encoding="utf-8"))

    def rollback(self, snapshot: WorkspaceSnapshot | None = None) -> None:
        snapshot = snapshot or self.load_snapshot()
        before = snapshot.file_map()
        current = set(self._workspace_paths())
        for rel in sorted(current - set(before)):
            path = self.root / rel
            if path.is_file() and not _is_ignored(Path(rel)):
                path.unlink()
        for rel, content in before.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def _workspace_paths(self) -> list[str]:
        tracked = self._git(["ls-files"]).splitlines()
        untracked = self._git(["ls-files", "--others", "--exclude-standard"]).splitlines()
        return sorted({path for path in [*tracked, *untracked] if path})

    def _git(self, args: list[str]) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"git {' '.join(args)} failed")
        return completed.stdout


def _is_ignored(relative_path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in relative_path.parts)
