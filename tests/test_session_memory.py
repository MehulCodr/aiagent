from __future__ import annotations

from pathlib import Path

from code_agent.messages import ChatMessage
from code_agent.session import SessionStore


def test_session_save_load_and_list_under_agent_sessions(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create(provider="fake", model="fake-model")
    session.messages.append(ChatMessage(role="user", content="remember this"))

    path = store.save_named(session, "demo")
    loaded = store.load("demo")
    sessions = store.list_sessions()

    assert path.parent == tmp_path / ".agent" / "sessions"
    assert loaded.id == session.id
    assert loaded.name == "demo"
    assert sessions[0].id == session.id
