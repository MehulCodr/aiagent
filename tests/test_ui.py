from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from rich.console import Console

from code_agent.messages import ToolCall
from code_agent.ui import TerminalMarkdownRenderer, TerminalUI


def test_ui_no_color_mode_emits_no_ansi_codes() -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    ui.info("hello")
    ui.warning("careful")

    text = output.getvalue()
    assert "\x1b[" not in text
    assert "hello" in text
    assert "careful" in text


def test_tool_call_formats_arguments_as_pretty_json() -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    ui.tool_call(ToolCall(id="read", name="read_file", arguments={"path": "src/app.py", "lines": [1, 3]}))

    text = output.getvalue()
    assert '"path": "src/app.py"' in text
    assert '"lines": [' in text
    assert "{'path':" not in text


def test_assistant_text_renders_markdown_as_terminal_output() -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    ui.assistant_text("# Summary\n\n- **Done** with `src/app.py`")

    text = output.getvalue()
    assert "Summary" in text
    assert "Done" in text
    assert "src/app.py" in text
    assert "# Summary" not in text
    assert "**Done**" not in text
    assert "`src/app.py`" not in text


def test_markdown_renderer_disables_hyperlinks_for_terminal_logs() -> None:
    renderer = TerminalMarkdownRenderer()

    rendered = renderer.render("[docs](https://example.com)")

    assert rendered.hyperlinks is False


def test_shell_approval_uses_simple_yes_no_prompt() -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    with patch("prompt_toolkit.prompt", return_value="y") as prompt:
        approved = ui.confirm_tool("shell", {"command": "pytest"}, "Shell commands require approval in strict mode.")

    text = output.getvalue()
    assert approved is True
    prompt.assert_called_once_with("Run command? [y/N] ")
    assert "Shell command requires approval:" in text
    assert "pytest" in text
    assert "╭" not in text
