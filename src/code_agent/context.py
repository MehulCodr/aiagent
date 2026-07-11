from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from code_agent.config import AgentConfig


EXCLUDED_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".agent",
    ".code-agent",
}


def build_system_prompt(root: Path, tools: list[Any], config: AgentConfig, retrieved_context: str = "") -> str:
    tool_names = ", ".join(tool.name for tool in tools)
    project_snapshot = _project_snapshot(root)
    agent_instructions = _read_optional(root / "AGENTS.md", 12_000)
    date = datetime.now(UTC).date().isoformat()
    parts = [
        "You are code-agent, a Python CLI coding agent.",
        f"Current date: {date}.",
        f"Project root: {root.resolve()}",
        f"Available tools: {tool_names}.",
        "",
        "Operating rules:",
        "- Use tool calls when you need project facts, file contents, edits, or command output.",
        "- Read relevant files before editing them.",
        "- Keep changes minimal and directly tied to the user's request.",
        "- File tools are limited to the project root.",
        "- Shell commands run from the project root. Destructive commands are blocked; risky commands require user approval.",
        "- Do not expose secrets. If a command output contains a secret, summarize safely.",
        "- Continue the agent loop until the requested work is actually complete or a real blocker is reached.",
        "",
        "Response style:",
        "- Write user-facing replies in concise Markdown when structure helps.",
        "- Use headings, bullets, inline code, and fenced code blocks naturally; the terminal UI renders Markdown for display.",
        "- Keep final answers compact and focused on the completed work, verification, and blockers if any.",
        "",
        "Project snapshot:",
        project_snapshot,
    ]
    if retrieved_context:
        parts.extend(
            [
                "",
                "Retrieved repository context:",
                retrieved_context,
                "",
                "When you use retrieved repository facts, cite paths and line ranges exactly in this form: src/file.py:10-24.",
            ]
        )
    if agent_instructions:
        parts.extend(["", "AGENTS.md:", agent_instructions])
    if config.session_char_budget:
        parts.append(f"\nApproximate session character budget: {config.session_char_budget}.")
    return "\n".join(parts)


def _read_optional(path: Path, max_chars: int) -> str:
    if not path.exists() or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n[truncated]"
    return text


def _project_snapshot(root: Path, max_entries: int = 80) -> str:
    entries: list[str] = []
    for item in sorted(root.iterdir(), key=lambda child: (child.is_file(), child.name.lower())):
        if item.name in EXCLUDED_NAMES:
            continue
        suffix = "/" if item.is_dir() else ""
        entries.append(f"- {item.name}{suffix}")
        if len(entries) >= max_entries:
            entries.append("- [truncated]")
            break
    return "\n".join(entries) if entries else "- [empty project]"
