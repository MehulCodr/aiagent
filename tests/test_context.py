from __future__ import annotations

from pathlib import Path

from code_agent.config import AgentConfig
from code_agent.context import build_system_prompt


def test_system_prompt_allows_markdown_rendered_by_terminal_ui(tmp_path: Path) -> None:
    prompt = build_system_prompt(tmp_path, [], AgentConfig(rag_enabled=False), retrieved_context="src/app.py:1-2")

    assert "concise Markdown" in prompt
    assert "terminal UI renders Markdown" in prompt
    assert "not Markdown" not in prompt
    assert "src/file.py:10-24" in prompt
