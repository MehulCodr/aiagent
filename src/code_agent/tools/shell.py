from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

from code_agent.tools.base import Tool, ToolContext, ToolDefinition, ToolResult


Risk = Literal["safe", "risky", "blocked"]

BLOCKED_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*|-r\s+-f|-f\s+-r)\s+[/~]?",
    r"\bRemove-Item\b.*\b-Recurse\b.*\b-Force\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b.*-[a-zA-Z]*[fdx]",
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bStop-Computer\b",
]

RISKY_PATTERNS = [
    r"\brm\b",
    r"\bdel\b",
    r"\brmdir\b",
    r"\bRemove-Item\b",
    r"\bmove\b",
    r"\bmv\b",
    r"\bgit\b",
    r"\b(pip|uv|poetry|npm|pnpm|yarn)\s+(install|add|remove|update)\b",
    r"\bchmod\b",
    r"\bchown\b",
]


def classify_command(command: str, root: Path, allow_outside_root: bool = False) -> tuple[Risk, str]:
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return "blocked", f"Blocked by safety rule: {pattern}"
    if not allow_outside_root:
        if _mentions_outside_path(command, root):
            return "blocked", "Command references a path outside the project root."
        if re.search(r"(^|\s)\.\.([\\/]|$)", command):
            return "blocked", "Command uses a parent-directory path while outside-root access is disabled."
    for pattern in RISKY_PATTERNS:
        if re.search(pattern, command, flags=re.IGNORECASE):
            return "risky", f"Risky command matched: {pattern}"
    if allow_outside_root:
        return "risky", "Command requested outside-root access."
    return "safe", "Command classified as safe."


def _mentions_outside_path(command: str, root: Path) -> bool:
    root_resolved = root.resolve()
    windows_paths = re.findall(r"(?i)([a-z]:\\[^\"'\n\r]+)", command)
    for raw in windows_paths:
        try:
            path = Path(raw.strip()).resolve(strict=False)
        except OSError:
            continue
        if not path.is_relative_to(root_resolved):
            return True
    return False


class ShellTool(Tool):
    definition = ToolDefinition(
        name="shell",
        description="Run a shell command from the project root with safety checks and output capture.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 120, "default": 30},
                "allow_outside_root": {"type": "boolean", "default": False},
                "reason": {"type": "string", "default": ""},
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    )

    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        command = arguments["command"]
        timeout = arguments.get("timeout_seconds", 30)
        allow_outside_root = arguments.get("allow_outside_root", False)
        risk, reason = classify_command(command, context.root, allow_outside_root)
        if risk == "blocked":
            return ToolResult(content=reason, is_error=True)
        if not context.auto_approve:
            if context.approval_callback is None:
                return ToolResult(content=f"Command requires user approval: {reason}", is_error=True)
            if not context.approval_callback(command, arguments.get("reason") or reason):
                return ToolResult(content="User denied shell command.", is_error=True)

        try:
            completed = _run_command(command, context.root, timeout)
        except subprocess.TimeoutExpired:
            return ToolResult(content=f"Command timed out after {timeout}s", is_error=True)

        output = [
            f"exit_code: {completed.returncode}",
            "stdout:",
            _trim(completed.stdout),
            "stderr:",
            _trim(completed.stderr),
        ]
        return ToolResult(content="\n".join(output), is_error=completed.returncode != 0)


def _run_command(command: str, root: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    if platform.system().lower() == "windows":
        args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command]
        return subprocess.run(
            args,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    return subprocess.run(
        command,
        cwd=root,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _trim(text: str, limit: int = 20_000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text.rstrip()
    return text[:limit].rstrip() + "\n[truncated]"
