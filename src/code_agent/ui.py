from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
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
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.history import History
    from prompt_toolkit.input import Input
    from prompt_toolkit.layout import Window
    from prompt_toolkit.output import Output
    from prompt_toolkit.styles import BaseStyle, StyleTransformation
    from rich.markdown import Markdown
    from rich.status import Status


COMPOSER_PROMPT = "> "
COMPOSER_MAX_CONTENT_ROWS = 10

# prompt-toolkit 3.0.52 does not expose a Shift+Enter key. Unknown CSI-u
# sequences are delivered as their individual characters, so these exact,
# narrowly-scoped bindings let modern terminals expose the modifier without
# changing prompt-toolkit's parser or global bindings.
SHIFT_ENTER_SEQUENCES = (
    "\x1b[13;2u",  # Kitty/CSI-u Enter.
    "\x1b[13;2:1u",  # Kitty key-press event.
    "\x1b[13;2:2u",  # Kitty key-repeat event.
    "\x1b[57414;2u",  # Kitty/CSI-u keypad Enter.
    "\x1b[57414;2:1u",
    "\x1b[57414;2:2u",
    "\x1b[27;2;13~",  # xterm modifyOtherKeys.
    "\x1b[13;2~",  # Legacy CSI modified Enter.
)

ALT_ENTER_SEQUENCES = (
    "\x1b\r",  # Legacy Alt+Enter, or Escape followed by Enter.
    "\x1b\n",
    "\x1b[13;3u",  # Kitty/CSI-u Alt+Enter.
    "\x1b[13;3:1u",
    "\x1b[57414;3u",
    "\x1b[57414;3:1u",
    "\x1b[27;3;13~",  # xterm modifyOtherKeys Alt+Enter.
    "\x1b[13;3~",
)

_CSI_ENTER_SEQUENCES = (
    "\x1b[13u",
    "\x1b[13;1u",
    "\x1b[13;1:1u",
    "\x1b[57414u",
    "\x1b[57414;1u",
    "\x1b[57414;1:1u",
    "\x1b[106;5u",  # CSI-u Ctrl+J; retain LF-as-submit behavior.
    "\x1b[106;5:1u",
    "\x1b[106;5:2u",
)

_CSI_KEY_RELEASE_SEQUENCES = (
    "\x1b[13;1:3u",
    "\x1b[13;2:3u",
    "\x1b[13;3:3u",
    "\x1b[57414;1:3u",
    "\x1b[57414;2:3u",
    "\x1b[57414;3:3u",
    "\x1b[106;5:3u",
)

_SINGLE_KEY_NEWLINE_SEQUENCES = frozenset({"\x1b[27;2;13~"})


@dataclass(frozen=True)
class _VisualSegment:
    start: int
    end: int


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
        self._prompt_window: Window | None = None
        self._prompt_history_path: Path | None = None
        self._visual_segment_cache: tuple[str, int, tuple[_VisualSegment, ...]] | None = None
        self._session_id = ""

    def header(self, *, provider: str, model: str, root: Path, session_id: str) -> None:
        self._session_id = session_id
        self._prompt_history_path = root / ".agent" / "prompt_history"
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
        if self._prompt_session is None:
            self._prompt_session = self._create_prompt_session()
        return self._prompt_session.prompt(COMPOSER_PROMPT, bottom_toolbar=self._bottom_toolbar)

    def _create_prompt_session(
        self,
        *,
        input: Input | None = None,
        output: Output | None = None,
    ) -> PromptSession[str]:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.filters import to_filter
        from prompt_toolkit.layout import Dimension

        session: PromptSession[str] = PromptSession(
            history=self._create_prompt_history(),
            multiline=True,
            wrap_lines=True,
            show_frame=True,
            key_bindings=self._create_composer_key_bindings(),
            style=self._composer_style(),
            style_transformation=self._composer_style_transformation(),
            include_default_pygments_style=False,
            input=input,
            output=output,
        )

        # show_frame owns the border and redraw lifecycle. Constraining the
        # actual Buffer Window (rather than printing a border) makes its body
        # grow from one row to ten, then scroll internally on overflow.
        prompt_window = session.layout.current_window
        prompt_window.height = Dimension(min=1, max=COMPOSER_MAX_CONTENT_ROWS)
        prompt_window.dont_extend_height = to_filter(True)
        session.default_buffer.on_text_changed += self._clear_visual_segment_cache
        self._prompt_window = prompt_window
        return session

    def _clear_visual_segment_cache(self, _buffer: Buffer) -> None:
        self._visual_segment_cache = None

    def _create_composer_key_bindings(self) -> Any:
        from prompt_toolkit.enums import DEFAULT_BUFFER
        from prompt_toolkit.filters import has_focus
        from prompt_toolkit.key_binding import KeyBindings

        bindings = KeyBindings()
        default_focused = has_focus(DEFAULT_BUFFER)

        def insert_newline(event: Any) -> None:
            event.current_buffer.insert_text("\n")

        def submit(event: Any) -> None:
            if not event.current_buffer.text.strip():
                event.app.exit(result=event.current_buffer.text)
            else:
                event.current_buffer.validate_and_handle()

        def ignore(_event: Any) -> None:
            return None

        @bindings.add("enter", filter=default_focused, eager=True)
        def handle_enter(event: Any) -> None:
            if event.data in _SINGLE_KEY_NEWLINE_SEQUENCES:
                insert_newline(event)
            else:
                submit(event)

        # Some terminals send LF for Return. Keep Ctrl+J's prompt-toolkit
        # behavior as submit so normal Enter is never reinterpreted as newline.
        bindings.add("c-j", filter=default_focused, eager=True)(submit)

        for sequence in SHIFT_ENTER_SEQUENCES + ALT_ENTER_SEQUENCES:
            bindings.add(*_key_binding_sequence(sequence), filter=default_focused, eager=True)(
                insert_newline
            )

        for sequence in _CSI_ENTER_SEQUENCES:
            bindings.add(*_key_binding_sequence(sequence), filter=default_focused, eager=True)(submit)

        for sequence in _CSI_KEY_RELEASE_SEQUENCES:
            bindings.add(*_key_binding_sequence(sequence), filter=default_focused, eager=True)(ignore)

        @bindings.add("up", filter=default_focused, eager=True)
        def move_up(event: Any) -> None:
            self._move_on_visual_rows(event.current_buffer, -1)

        @bindings.add("down", filter=default_focused, eager=True)
        def move_down(event: Any) -> None:
            self._move_on_visual_rows(event.current_buffer, 1)

        return bindings

    def _move_on_visual_rows(self, buffer: Buffer, direction: int) -> None:
        if buffer.complete_state is not None:
            if direction < 0:
                buffer.complete_previous()
            else:
                buffer.complete_next()
            return
        if buffer.selection_state is not None:
            if direction < 0:
                buffer.auto_up()
            else:
                buffer.auto_down()
            return

        render_info = self._prompt_window.render_info if self._prompt_window is not None else None
        if render_info is None:
            if direction < 0:
                buffer.auto_up()
            else:
                buffer.auto_down()
            return

        document = buffer.document
        line_number = document.cursor_position_row
        cursor_column = document.cursor_position_col
        line = document.lines[line_number]
        segments = self._visual_segments_for_line(line, render_info.window_width)
        segment_number = next(
            index for index, segment in enumerate(segments) if segment.start <= cursor_column <= segment.end
        )
        current_segment = segments[segment_number]
        preferred_column = (
            buffer.preferred_column
            if buffer.preferred_column is not None
            else _display_column(line, current_segment.start, cursor_column)
        )

        target_segment_number = segment_number + direction
        target_line = line
        target_line_start = buffer.cursor_position - cursor_column
        if 0 <= target_segment_number < len(segments):
            target_segment = segments[target_segment_number]
        elif direction < 0 and line_number > 0:
            target_line = document.lines[line_number - 1]
            target_line_start -= len(target_line) + 1
            target_segment = self._visual_segments_for_line(target_line, render_info.window_width)[-1]
        elif direction > 0 and line_number < len(document.lines) - 1:
            target_line_start += len(line) + 1
            target_line = document.lines[line_number + 1]
            target_segment = self._visual_segments_for_line(target_line, render_info.window_width)[0]
        elif direction < 0:
            buffer.history_backward()
            return
        else:
            buffer.history_forward()
            return

        target_column = _column_nearest_display_position(target_line, target_segment, preferred_column)
        buffer.cursor_position = target_line_start + target_column
        buffer.preferred_column = preferred_column

    def _visual_segments_for_line(self, line: str, window_width: int) -> tuple[_VisualSegment, ...]:
        cache = self._visual_segment_cache
        if cache is not None and cache[0] == line and cache[1] == window_width:
            return cache[2]
        segments = _line_visual_segments(line, window_width)
        self._visual_segment_cache = (line, window_width, segments)
        return segments

    def _composer_style(self) -> BaseStyle:
        from prompt_toolkit.styles import Style

        if self.no_color:
            return Style.from_dict({"bottom-toolbar": "noreverse", "bottom-toolbar.text": "noreverse"})
        return Style.from_dict(
            {
                "frame.border": "ansicyan",
                "prompt": "ansicyan bold",
                "bottom-toolbar": "noreverse ansibrightblack",
                "bottom-toolbar.text": "noreverse ansibrightblack",
            }
        )

    def _composer_style_transformation(self) -> StyleTransformation | None:
        if not self.no_color:
            return None

        from prompt_toolkit.styles import DEFAULT_ATTRS, Attrs, StyleTransformation

        class PlainStyleTransformation(StyleTransformation):
            def transform_attrs(self, attrs: Attrs) -> Attrs:
                return DEFAULT_ATTRS

        return PlainStyleTransformation()

    def _create_prompt_history(self) -> History:
        from prompt_toolkit.history import FileHistory, InMemoryHistory

        if self._prompt_history_path is None:
            return InMemoryHistory()
        self._prompt_history_path.parent.mkdir(parents=True, exist_ok=True)
        return FileHistory(str(self._prompt_history_path))

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

        self.console.print(f"[yellow]Shell command requires approval:[/yellow] {command}")
        if reason:
            self.console.print(f"[dim]{reason}[/dim]")
        answer = prompt("Run command? [y/N] ").strip().lower()
        return answer in {"y", "yes"}

    def confirm_tool(self, tool_name: str, arguments: dict[str, Any], reason: str) -> bool:
        if tool_name == "shell":
            return self.confirm_shell(str(arguments.get("command") or ""), reason)

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
        return f" Enter send  •  Shift+Enter newline  •  ↑/↓ history  •  session {suffix} "


def _format_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)


def _key_binding_sequence(sequence: str) -> tuple[str, ...]:
    aliases = {"\x1b": "escape", "\r": "enter", "\n": "c-j"}
    return tuple(aliases.get(character, character) for character in sequence)


def _line_visual_segments(line: str, window_width: int) -> tuple[_VisualSegment, ...]:
    """Return source-column ranges for prompt-toolkit's wrapped visual rows."""
    width = max(len(COMPOSER_PROMPT) + 1, window_width)
    prefix_width = len(COMPOSER_PROMPT)
    content_width = width - prefix_width
    if not line or (line.isascii() and line.isprintable()):
        return tuple(
            _VisualSegment(start, min(start + content_width - 1, len(line)))
            for start in range(0, len(line) + 1, content_width)
        )

    segments: list[_VisualSegment] = []
    segment_start = 0
    x = prefix_width

    # BufferControl renders a trailing space so the end-of-line cursor has a
    # cell. Including it models the extra visual row at an exact wrap boundary.
    for column, character in enumerate(line + " "):
        character_width = 1 if " " <= character <= "~" else _display_width(character)
        if x + character_width > width:
            if segment_start < column:
                segments.append(_VisualSegment(segment_start, column - 1))
            segment_start = column
            x = prefix_width
        x += character_width

    segments.append(_VisualSegment(segment_start, len(line)))
    return tuple(segments)


@lru_cache(maxsize=512)
def _display_width(character: str) -> int:
    from prompt_toolkit.layout.screen import Char

    return Char(character).width


def _display_column(line: str, start: int, cursor: int) -> int:
    return sum(_display_width(character) for character in line[start:cursor])


def _column_nearest_display_position(line: str, segment: _VisualSegment, preferred: int) -> int:
    best_column = segment.start
    best_key = (preferred, False, -segment.start)
    display_column = 0
    for column in range(segment.start, segment.end + 1):
        key = (abs(display_column - preferred), display_column > preferred, -column)
        if key < best_key:
            best_column = column
            best_key = key
        if column < len(line):
            display_column += _display_width(line[column])
    return best_column
