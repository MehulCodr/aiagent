from __future__ import annotations

from rich.console import Console

from code_agent.messages import ToolCall
from code_agent.ui import TerminalUI


def test_tool_call_arguments_render_as_terminal_fields() -> None:
    console = Console(record=True, force_terminal=False, width=80)
    ui = TerminalUI(console)

    ui.tool_call(ToolCall(id="call-1", name="shell", arguments={"command": "pwd", "timeout_seconds": 5}))

    output = console.export_text()
    assert "command" in output
    assert "pwd" in output
    assert "timeout_seconds" in output
    assert '"command"' not in output
    assert "{" not in output


def test_assistant_response_renders_markdown_as_terminal_output() -> None:
    console = Console(record=True, force_terminal=False, width=80)
    ui = TerminalUI(console)

    ui.assistant_response("# Summary\n\n**Done**\n\n```python\nprint('ok')\n```")

    output = console.export_text()
    assert "Summary" in output
    assert "Done" in output
    assert "print('ok')" in output
    assert "# Summary" not in output
    assert "**Done**" not in output
    assert "```" not in output
