from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from prompt_toolkit.history import FileHistory, InMemoryHistory
from rich.console import Console

from code_agent.messages import ToolCall
from code_agent.cli import chat
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


def test_prompt_history_uses_project_file_after_header(tmp_path) -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    ui.header(provider="fake", model="fake-model", root=tmp_path, session_id="session-123")
    history = ui._create_prompt_history()

    assert isinstance(history, FileHistory)
    assert ui._prompt_history_path == tmp_path / ".agent" / "prompt_history"
    assert (tmp_path / ".agent").is_dir()


def test_prompt_history_falls_back_to_memory_before_header() -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    history = ui._create_prompt_history()

    assert isinstance(history, InMemoryHistory)


def test_chat_ignores_whitespace_only_input_but_preserves_valid_prompt_whitespace() -> None:
    ui = Mock()
    ui.user_prompt.side_effect = ["   ", "  keep this whitespace  ", KeyboardInterrupt()]
    runtime = SimpleNamespace(
        ui=ui,
        provider=SimpleNamespace(id="fake"),
        model="fake-model",
        root="root",
        session=SimpleNamespace(id="session-123"),
        run_user_turn=Mock(),
    )

    with patch("code_agent.cli._build_runtime", return_value=runtime):
        chat(
            prompt=None,
            provider=None,
            model=None,
            root=None,
            resume=False,
            session=None,
            yes=False,
            no_color=True,
            verbose=False,
        )

    runtime.run_user_turn.assert_called_once_with("  keep this whitespace  ")
    ui.info.assert_called_once_with("bye")


def test_chat_normalizes_only_session_commands() -> None:
    ui = Mock()
    ui.user_prompt.side_effect = ["  /help  ", KeyboardInterrupt()]
    runtime = SimpleNamespace(
        ui=ui,
        provider=SimpleNamespace(id="fake"),
        model="fake-model",
        root="root",
        session=SimpleNamespace(id="session-123"),
        run_user_turn=Mock(),
    )

    with patch("code_agent.cli._build_runtime", return_value=runtime):
        chat(
            prompt=None,
            provider=None,
            model=None,
            root=None,
            resume=False,
            session=None,
            yes=False,
            no_color=True,
            verbose=False,
        )

    ui.help.assert_called_once_with()
    runtime.run_user_turn.assert_not_called()
