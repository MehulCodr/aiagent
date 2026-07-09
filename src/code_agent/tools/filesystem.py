from __future__ import annotations

from pathlib import Path
from typing import Any

from code_agent.context import EXCLUDED_NAMES
from code_agent.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


MAX_FILE_CHARS = 80_000


def resolve_inside_root(root: Path, raw_path: str) -> Path:
    if not raw_path:
        raw_path = "."
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    root_resolved = root.resolve()
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root_resolved):
        raise PermissionError(f"Path escapes project root: {raw_path}")
    return resolved


class ListFilesTool(Tool):
    parallel_safe = True

    definition = ToolDefinition(
        name="list_files",
        description="List files and directories under a project-root-relative path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "recursive": {"type": "boolean", "default": False},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 200},
            },
            "additionalProperties": False,
        },
    )

    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_inside_root(context.root, arguments.get("path", "."))
        recursive = arguments.get("recursive", False)
        max_entries = arguments.get("max_entries", 200)
        if not path.exists():
            return ToolResult(content=f"Path does not exist: {path}", is_error=True)
        iterator = path.rglob("*") if recursive else path.iterdir()
        rows: list[str] = []
        for item in sorted(iterator, key=lambda child: str(child).lower()):
            if any(part in EXCLUDED_NAMES for part in item.relative_to(context.root).parts):
                continue
            rel = item.relative_to(context.root).as_posix()
            rows.append(rel + ("/" if item.is_dir() else ""))
            if len(rows) >= max_entries:
                rows.append("[truncated]")
                break
        return ToolResult(content="\n".join(rows) if rows else "[empty]")


class ReadFileTool(Tool):
    parallel_safe = True

    definition = ToolDefinition(
        name="read_file",
        description="Read a UTF-8 text file inside the project root, optionally by 1-based line range.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "start_line": {"type": "integer", "minimum": 1},
                "end_line": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    )

    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_inside_root(context.root, arguments["path"])
        if not path.is_file():
            return ToolResult(content=f"Not a file: {arguments['path']}", is_error=True)
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        start = arguments.get("start_line")
        end = arguments.get("end_line")
        if start is not None or end is not None:
            start_idx = max((start or 1) - 1, 0)
            end_idx = end if end is not None else len(lines)
            selected = lines[start_idx:end_idx]
            text = "\n".join(f"{start_idx + i + 1}: {line}" for i, line in enumerate(selected))
        if len(text) > MAX_FILE_CHARS:
            text = text[:MAX_FILE_CHARS] + "\n[truncated]"
        return ToolResult(content=text)


class WriteFileTool(Tool):
    definition = ToolDefinition(
        name="write_file",
        description="Write a UTF-8 text file inside the project root. Set overwrite=true to replace an existing file.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "overwrite": {"type": "boolean", "default": False},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    )

    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_inside_root(context.root, arguments["path"])
        overwrite = arguments.get("overwrite", False)
        if path.exists() and not overwrite:
            return ToolResult(content=f"File already exists. Use overwrite=true: {arguments['path']}", is_error=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(arguments["content"], encoding="utf-8")
        return ToolResult(content=f"Wrote {path.relative_to(context.root).as_posix()}")


class EditFileTool(Tool):
    definition = ToolDefinition(
        name="edit_file",
        description="Replace exact text in a UTF-8 file inside the project root.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "expected_replacements": {"type": "integer", "minimum": 1, "default": 1},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
    )

    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        path = resolve_inside_root(context.root, arguments["path"])
        if not path.is_file():
            return ToolResult(content=f"Not a file: {arguments['path']}", is_error=True)
        old_text = arguments["old_text"]
        new_text = arguments["new_text"]
        expected = arguments.get("expected_replacements", 1)
        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count(old_text)
        if count != expected:
            return ToolResult(
                content=f"Expected {expected} replacement(s), found {count}. No changes made.",
                is_error=True,
            )
        path.write_text(text.replace(old_text, new_text, expected), encoding="utf-8")
        return ToolResult(content=f"Edited {path.relative_to(context.root).as_posix()} ({count} replacement(s))")
