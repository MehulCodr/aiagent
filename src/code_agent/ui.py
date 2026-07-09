from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from code_agent.messages import ToolCall
from code_agent.tools.base import ToolResult

if TYPE_CHECKING:
    from prompt_toolkit import PromptSession
    from rich.markdown import Markdown
    from rich.status import Status


class TerminalMarkdownRenderer:
    def __init__(self, *, code_theme: str = "ansi_dark", hyperlinks: bool = False) -> None:
        self.code_theme = code_theme
        self.hyperlinks = hyperlinks

    def render(self, text: str) -> Markdown:
        from rich.markdown import Markdown

        return Markdown(text, code_theme=self.code_theme, hyperlinks=self.hyperlinks)


class TerminalUI:
    def __init__(self, console: Console | None = None, *, no_color: bool = False, verbose: bool = False) -> None:
        self.console = console or Console()
        self.no_color = no_color
        self.verbose = verbose
        self.markdown = TerminalMarkdownRenderer()
        self._prompt_session: PromptSession[str] | None = None
        self._session_id = ""

    def header(self, *, provider: str, model: str, root: Path, session_id: str) -> None:
        self._session_id = session_id
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

    def status(self, label: str, message: str) -> None:
        self.console.print(f"[bold cyan]{label}[/bold cyan] {message}")

    def debug(self, message: str) -> None:
        if self.verbose:
            self.console.print(f"[dim]{message}[/dim]")

    @contextmanager
    def activity(self, message: str) -> Iterator[Status]:
        from rich.status import Status

        with self.console.status(f"[cyan]{message}[/cyan]", spinner="dots") as status:
            yield status

    def user_prompt(self) -> str:
        from prompt_toolkit import PromptSession

        if self._prompt_session is None:
            self._prompt_session = PromptSession()
        return self._prompt_session.prompt("you> ", bottom_toolbar=self._bottom_toolbar).strip()

    def stream_text(self, text: str) -> None:
        self.console.print(text, end="", markup=False, highlight=False)

    def end_stream(self) -> None:
        self.console.print()

    def assistant_text(self, text: str) -> None:
        if not text.strip():
            return
        self.console.print(self.markdown.render(text))

    def tool_call(self, call: ToolCall) -> None:
        self.console.print(
            Panel.fit(
                f"[bold]{call.name}[/bold]\n[dim]{_format_json(call.arguments)}[/dim]",
                title="tool call",
                border_style="magenta",
            )
        )

    def tool_result(self, name: str, result: ToolResult) -> None:
        style = "red" if result.is_error else "green"
        content = result.content if len(result.content) <= 2000 else result.content[:2000] + "\n[truncated]"
        self.console.print(Panel(Text(content), title=f"{name} result", border_style=style))

    def tool_timeline(self, records: list[Any]) -> None:
        if not records:
            return
        table = Table(title="tool timeline")
        table.add_column("#", justify="right")
        table.add_column("tool")
        table.add_column("status")
        table.add_column("time", justify="right")
        for record in records:
            status = "error" if record.result.is_error else "ok"
            table.add_row(str(record.index + 1), record.name, status, f"{record.duration_ms:.1f} ms")
        self.console.print(table)

    def diff(self, text: str) -> None:
        from rich.syntax import Syntax

        self.console.print(Syntax(text, "diff", theme="ansi_dark", word_wrap=True))

    def confirm_shell(self, command: str, reason: str) -> bool:
        from prompt_toolkit import prompt

        self.warning("Shell command requires approval.")
        self.console.print(Panel(f"{command}\n\n[dim]{reason}[/dim]", title="shell", border_style="yellow"))
        answer = prompt("approve? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    def confirm_tool(self, tool_name: str, arguments: dict[str, Any], reason: str) -> bool:
        from prompt_toolkit import prompt

        self.warning(f"{tool_name} requires approval.")
        body = f"{_format_json(arguments)}\n\n{reason}"
        self.console.print(Panel(Text(body), title=tool_name, border_style="yellow"))
        answer = prompt("approve? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    def print_plan(self, body: str) -> None:
        self.console.print(
            Panel(
                self.markdown.render(body),
                title="plan",
                border_style="cyan",
            )
        )

    def help(self) -> None:
        self.console.print(
            Panel(
                "\n".join(
                    [
                        "/help             show commands",
                        "/session          show current session details",
                        "/sessions         list saved sessions",
                        "/save <name>      save current session name",
                        "/load <name>      load a saved session",
                        "/plan <request>   create and review a plan",
                        "/plan             show the last plan",
                        "/apply            execute the last reviewed plan",
                        "/rollback         restore the pre-turn workspace snapshot",
                        "/clear            clear in-memory messages for this session",
                        "/quit             exit",
                        "",
                        "Type any request to let the agent work.",
                    ]
                ),
                title="commands",
                border_style="cyan",
            )
        )

    def _bottom_toolbar(self) -> str:
        suffix = self._session_id[:12] if self._session_id else "new"
        return f" code-agent | session {suffix} "


def _format_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)
