from __future__ import annotations

from pathlib import Path

from prompt_toolkit import prompt
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from code_agent.messages import ToolCall
from code_agent.tools.base import ToolResult


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

    def tool_call(self, call: ToolCall) -> None:
        self.console.print(
            Panel.fit(
                f"[bold]{call.name}[/bold]\n[dim]{call.arguments}[/dim]",
                title="tool call",
                border_style="magenta",
            )
        )

    def tool_result(self, name: str, result: ToolResult) -> None:
        style = "red" if result.is_error else "green"
        content = result.content if len(result.content) <= 2000 else result.content[:2000] + "\n[truncated]"
        self.console.print(Panel(content, title=f"{name} result", border_style=style))

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
