from __future__ import annotations

from io import StringIO

from rich.console import Console

from code_agent.ui import TerminalUI


def test_ui_no_color_mode_emits_no_ansi_codes() -> None:
    output = StringIO()
    ui = TerminalUI(Console(file=output, force_terminal=True, no_color=True), no_color=True)

    ui.info("hello")
    ui.warning("careful")

    text = output.getvalue()
    assert "\x1b[" not in text
    assert "hello" in text
    assert "careful" in text
