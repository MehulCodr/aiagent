from __future__ import annotations

from pathlib import Path

from code_agent.tools import build_default_tool_registry
from code_agent.tools.base import ToolContext
from code_agent.tools.filesystem import resolve_inside_root
from code_agent.tools.shell import classify_command


def test_file_tools_write_read_edit_and_list(tmp_path: Path) -> None:
    registry = build_default_tool_registry()
    context = ToolContext(root=tmp_path)

    result = registry.run(
        "write_file",
        {"path": "src/example.py", "content": "print('old')\n"},
        context,
    )
    assert not result.is_error

    result = registry.run("read_file", {"path": "src/example.py"}, context)
    assert "print('old')" in result.content

    result = registry.run(
        "edit_file",
        {
            "path": "src/example.py",
            "old_text": "old",
            "new_text": "new",
            "expected_replacements": 1,
        },
        context,
    )
    assert not result.is_error
    assert (tmp_path / "src" / "example.py").read_text(encoding="utf-8") == "print('new')\n"

    result = registry.run("list_files", {"path": ".", "recursive": True}, context)
    assert "src/example.py" in result.content


def test_filesystem_rejects_outside_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    try:
        resolve_inside_root(tmp_path, str(outside))
    except PermissionError as exc:
        assert "escapes project root" in str(exc)
    else:
        raise AssertionError("outside path should be rejected")


def test_shell_policy_blocks_destructive_and_flags_risky(tmp_path: Path) -> None:
    assert classify_command("git reset --hard", tmp_path)[0] == "blocked"
    assert classify_command("pip install rich", tmp_path)[0] == "risky"
    assert classify_command("python --version", tmp_path)[0] == "safe"
