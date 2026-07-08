from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from code_agent.config import config_dir
from code_agent.messages import ChatMessage


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Session(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str | None = None
    root: str
    provider: str
    model: str
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    messages: list[ChatMessage] = Field(default_factory=list)


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = config_dir(self.root) / "sessions"
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.directory / f"{session_id}.json"

    def create(self, *, provider: str, model: str, name: str | None = None) -> Session:
        return Session(root=str(self.root), provider=provider, model=model, name=name)

    def save(self, session: Session) -> Path:
        session.updated_at = now_iso()
        path = self.path_for(session.id)
        path.write_text(session.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def load(self, session: str | Path) -> Session:
        path = Path(session)
        if not path.exists():
            path = self.path_for(str(session))
        if not path.exists():
            matches = list(self.directory.glob(f"{session}*.json"))
            if len(matches) == 1:
                path = matches[0]
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session}")
        return Session.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def latest(self) -> Session | None:
        paths = sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime)
        if not paths:
            return None
        return self.load(paths[-1])

    def list(self) -> list[Path]:
        return sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
