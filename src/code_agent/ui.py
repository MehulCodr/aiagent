from __future__ import annotations

from pathlib import Path
from typing import Any

from prompt_toolkit import prompt
from rich.console import Console
from rich.markup import escape
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text

from code_agent.messages import ToolCall
from code_agent.tools.base import ToolResult


class TerminalSpinner:
    def __init__(self, status: Status) -> None:
        self._status = status
        self._active = False

    def __enter__(self) -> TerminalSpinner:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if not self._active:
            self._status.start()
            self._active = True

    def stop(self) -> None:
        if self._active:
            self._status.stop()
            self._active = False


def _tool_arguments_table(arguments: dict[str, Any]) -> Table | Text:
    if not arguments:
        return Text("no arguments", style="dim")

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold magenta", no_wrap=True)
    table.add_column()
    for key, value in sorted(arguments.items()):
        table.add_row(str(key), Text(_format_tool_value(value)))
    return table


def _format_tool_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return ", ".join(_format_tool_value(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(f"{key}: {_format_tool_value(item)}" for key, item in value.items())
    return str(value)


class TerminalUI:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def header(self, *, provider: str, model: str, root: Path, session_id: str) -> None:
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(justify="right")
        table.add_row(f"[bold]code-agent[/bold]  {provider}/{model}", f"[dim]{root}[/dim]")
        table.add_row(f"[dim]session {session_id[:12]}[/dim]", "[dim]/help for commands[/dim]")
        self.console.print(Panel(table, border_style="cyan"))

    def info(self, message: str) -> None:
        self.console.print(f"[cyan]{message}[/cyan]")

    def warning(self, message: str) -> None:
        self.console.print(f"[yellow]{message}[/yellow]")

    def error(self, message: str) -> None:
        self.console.print(f"[red]{message}[/red]")

    def user_prompt(self) -> str:
        return prompt("you> ").strip()

    def stream_text(self, text: str) -> None:
        self.console.print(text, end="", markup=False, highlight=False)

    def end_stream(self) -> None:
        self.console.print()

    def assistant_response(self, text: str) -> None:
        self.console.print(Markdown(text, code_theme="monokai", hyperlinks=False))

    def thinking(self, *, step: int, model: str) -> TerminalSpinner:
        return self.spinner(f"[cyan]thinking[/cyan] [dim]{escape(model)} step {step}[/dim]")

    def executing_tool(self, name: str) -> TerminalSpinner:
        return self.spinner(f"[magenta]executing tool[/magenta] [bold]{escape(name)}[/bold]", spinner="arc")

    def spinner(self, message: str, *, spinner: str = "dots") -> TerminalSpinner:
        return TerminalSpinner(self.console.status(message, spinner=spinner))

    def tool_call(self, call: ToolCall) -> None:
        self.console.print(
            Panel.fit(
                _tool_arguments_table(call.arguments),
                title="tool call",
                subtitle=escape(call.name),
                border_style="magenta",
            )
        )

    def tool_result(self, name: str, result: ToolResult) -> None:
        style = "red" if result.is_error else "green"
        content = result.content if len(result.content) <= 2000 else result.content[:2000] + "\n[truncated]"
        title = f"{escape(name)} result"
        subtitle = "error" if result.is_error else "ok"
        self.console.print(Panel(Text(content), title=title, subtitle=subtitle, border_style=style))

    def confirm_shell(self, command: str, reason: str) -> bool:
        self.warning("Shell command requires approval.")
        self.console.print(Panel(f"{command}\n\n[dim]{reason}[/dim]", title="shell", border_style="yellow"))
        answer = prompt("approve? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    def help(self) -> None:
        self.console.print(
            Panel(
                "\n".join(
                    [
                        "/help             show commands",
                        "/session          show current session details",
                        "/clear            clear in-memory messages for this session",
                        "/quit             exit",
                        "",
                        "Type any request to let the agent work. Shell commands that look risky will ask first.",
                    ]
                ),
                title="commands",
                border_style="cyan",
            )
        )
