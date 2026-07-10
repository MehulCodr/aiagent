from __future__ import annotations

import asyncio
import re
import threading
import time
from io import StringIO
from unittest.mock import patch

import pytest
from prompt_toolkit.data_structures import Size
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.console import Console

from code_agent.ui import (
    ALT_ENTER_SEQUENCES,
    COMPOSER_MAX_CONTENT_ROWS,
    COMPOSER_PROMPT,
    SHIFT_ENTER_SEQUENCES,
    TerminalUI,
    _line_visual_segments,
    _windows_shift_pressed,
)


UP = "\x1b[A"
DOWN = "\x1b[B"
LEFT = "\x1b[D"
RIGHT = "\x1b[C"
CONTROL_HOME = "\x1b[1;5H"
BRACKETED_PASTE_START = "\x1b[200~"
BRACKETED_PASTE_END = "\x1b[201~"


class RecordingOutput(DummyOutput):
    def __init__(self, *, rows: int = 40, columns: int = 80) -> None:
        self.rows = rows
        self.columns = columns
        self.parts: list[str] = []

    def get_size(self) -> Size:
        return Size(rows=self.rows, columns=self.columns)

    def write(self, data: str) -> None:
        self.parts.append(data)

    def write_raw(self, data: str) -> None:
        self.parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self.parts)


def _new_ui(*, history: InMemoryHistory | None = None, output: DummyOutput | None = None) -> tuple[TerminalUI, object]:
    pipe_context = create_pipe_input()
    pipe = pipe_context.__enter__()
    ui = TerminalUI(Console(file=StringIO(), no_color=True), no_color=True)
    if history is None:
        ui._prompt_session = ui._create_prompt_session(input=pipe, output=output or DummyOutput())
    else:
        with patch.object(ui, "_create_prompt_history", return_value=history):
            ui._prompt_session = ui._create_prompt_session(input=pipe, output=output or DummyOutput())
    return ui, (pipe_context, pipe)


def _close_pipe(pipe_state: object) -> None:
    pipe_context, _pipe = pipe_state
    pipe_context.__exit__(None, None, None)


def _run_prompt(
    keys: str,
    *,
    history: InMemoryHistory | None = None,
    output: DummyOutput | None = None,
    wait_for_history: bool = False,
) -> tuple[str, TerminalUI]:
    ui, pipe_state = _new_ui(history=history, output=output)
    _pipe_context, pipe = pipe_state
    try:
        if wait_for_history:
            def send_after_history_load() -> None:
                deadline = time.monotonic() + 2
                while history is not None and not history.get_strings() and time.monotonic() < deadline:
                    time.sleep(0.005)
                pipe.send_text(keys)

            feeder = threading.Thread(
                target=send_after_history_load,
                daemon=True,
            )
            feeder.start()
        else:
            pipe.send_text(keys)
        return ui.user_prompt(), ui
    finally:
        _close_pipe(pipe_state)


def _paste(text: str) -> str:
    return f"{BRACKETED_PASTE_START}{text}{BRACKETED_PASTE_END}"


def test_composer_uses_minimal_marker_and_prompt_toolkit_frame() -> None:
    output = RecordingOutput()

    result, ui = _run_prompt("x\r", output=output)

    assert result == "x"
    assert COMPOSER_PROMPT == "> "
    assert ui._prompt_session.message == "> "
    assert "you" + ">" not in output.text
    assert "│>" in output.text
    assert "┌" in output.text
    assert "└" in output.text


def test_plain_enter_submits_instead_of_inserting_newline() -> None:
    result, _ui = _run_prompt("hello\r")

    assert result == "hello"


def test_native_windows_shift_enter_inserts_newline_when_modifier_is_pressed() -> None:
    with patch("code_agent.ui._windows_shift_pressed", side_effect=[True, False]):
        result, _ui = _run_prompt("first\rsecond\r")

    assert result == "first\nsecond"


def test_windows_shift_detector_ignores_non_console_input() -> None:
    assert _windows_shift_pressed(object()) is False


def test_newline_is_inserted_at_the_cursor_without_submitting() -> None:
    result, _ui = _run_prompt(f"ab{LEFT}{SHIFT_ENTER_SEQUENCES[0]}c\r")

    assert result == "a\ncb"


@pytest.mark.parametrize("sequence", SHIFT_ENTER_SEQUENCES)
def test_supported_shift_enter_sequences_insert_newline(sequence: str) -> None:
    result, _ui = _run_prompt(f"a{sequence}b\r")

    assert result == "a\nb"


@pytest.mark.parametrize("sequence", ALT_ENTER_SEQUENCES)
def test_alt_or_escape_enter_fallback_sequences_insert_newline(sequence: str) -> None:
    result, _ui = _run_prompt(f"a{sequence}b\r")

    assert result == "a\nb"


def test_lf_keeps_prompt_toolkit_enter_compatibility() -> None:
    result, _ui = _run_prompt("hello\n")

    assert result == "hello"


def test_kitty_key_release_is_ignored_instead_of_inserted_as_text() -> None:
    result, _ui = _run_prompt("a\x1b[13;2:1u\x1b[13;2:3ub\r")

    assert result == "a\nb"


def test_up_moves_within_multiline_input() -> None:
    result, _ui = _run_prompt(f"{_paste('one\ntwo\nthree')}{UP}X\r")

    assert result == "one\ntwoX\nthree"


def test_down_moves_within_multiline_input() -> None:
    keys = f"{_paste('one\ntwo\nthree')}{CONTROL_HOME}{DOWN}X\r"

    result, _ui = _run_prompt(keys)

    assert result == "one\nXtwo\nthree"


def test_up_on_first_visual_line_immediately_recalls_history() -> None:
    history = InMemoryHistory(["older", "newer"])

    result, _ui = _run_prompt(f"draft{UP}\r", history=history, wait_for_history=True)

    assert result == "newer"


def test_down_on_last_line_navigates_toward_newer_history() -> None:
    history = InMemoryHistory(["older", "newer"])

    result, _ui = _run_prompt(f"draft{UP}{UP}{DOWN}\r", history=history, wait_for_history=True)

    assert result == "newer"


def test_moving_past_newest_history_restores_unfinished_draft() -> None:
    history = InMemoryHistory(["previous"])

    result, _ui = _run_prompt(f"unfinished{UP}{DOWN}\r", history=history, wait_for_history=True)

    assert result == "unfinished"


def test_multiline_history_entry_is_restored_intact() -> None:
    history = InMemoryHistory(["first\n    second"])

    result, _ui = _run_prompt(f"{UP}\r", history=history, wait_for_history=True)

    assert result == "first\n    second"


def test_file_history_persists_multiline_entries_without_consecutive_duplicates(tmp_path) -> None:
    text = "first\n    second"
    with create_pipe_input() as pipe:
        first_ui = TerminalUI(Console(file=StringIO(), no_color=True), no_color=True)
        first_ui.header(provider="fake", model="fake", root=tmp_path, session_id="one")
        first_ui._prompt_session = first_ui._create_prompt_session(input=pipe, output=DummyOutput())
        pipe.send_text(f"{_paste(text)}\r")
        assert first_ui.user_prompt() == text
        pipe.send_text(f"{_paste(text)}\r")
        assert first_ui.user_prompt() == text

    history_path = tmp_path / ".agent" / "prompt_history"
    assert history_path.is_file()

    with create_pipe_input() as pipe:
        restored_ui = TerminalUI(Console(file=StringIO(), no_color=True), no_color=True)
        restored_ui.header(provider="fake", model="fake", root=tmp_path, session_id="two")
        restored_ui._prompt_session = restored_ui._create_prompt_session(input=pipe, output=DummyOutput())

        def recall_after_history_load() -> None:
            history = restored_ui._prompt_session.history
            deadline = time.monotonic() + 2
            while not history.get_strings() and time.monotonic() < deadline:
                time.sleep(0.005)
            pipe.send_text(f"{UP}\r")

        feeder = threading.Thread(
            target=recall_after_history_load,
            daemon=True,
        )
        feeder.start()
        assert restored_ui.user_prompt() == text

    stored_text = history_path.read_text(encoding="utf-8")
    assert stored_text.count("# ") == 1


def test_recalled_history_entry_remains_editable() -> None:
    history = InMemoryHistory(["hello"])

    result, _ui = _run_prompt(f"{UP}{LEFT}X\r", history=history, wait_for_history=True)

    assert result == "hellXo"


def test_up_and_down_follow_soft_wrapped_visual_rows_with_sticky_column() -> None:
    text = "z" * 200

    up_result, _ui = _run_prompt(f"{text}{UP}{UP}X\r")
    down_keys = f"{_paste(text)}{CONTROL_HOME}{RIGHT * 48}{DOWN}{DOWN}X\r"
    down_result, _ui = _run_prompt(down_keys)

    assert up_result == text[:48] + "X" + text[48:]
    assert down_result == text[:200] + "X"


def test_wrapped_up_reaches_history_only_after_first_visual_row() -> None:
    history = InMemoryHistory(["history prompt"])

    result, _ui = _run_prompt(f"{'z' * 200}{UP}{UP}{UP}\r", history=history, wait_for_history=True)

    assert result == "history prompt"


def test_wide_unicode_characters_participate_in_visual_line_movement() -> None:
    text = "界" * 100

    result, _ui = _run_prompt(f"{text}{UP}{UP}X\r")

    assert result == text[:24] + "X" + text[24:]


def test_wrapped_tabs_match_prompt_toolkit_visual_width() -> None:
    text = "\t" * 100

    result, _ui = _run_prompt(f"{_paste(text)}{UP}{UP}X\r")

    assert result == text[:24] + "X" + text[24:]


def test_ultra_narrow_wide_character_navigation_does_not_create_empty_target_rows() -> None:
    text = "界界"

    result, _ui = _run_prompt(f"{_paste(text)}{UP}X\r", output=RecordingOutput(columns=5))

    assert result.replace("X", "") == text
    assert result.count("X") == 1


def test_large_ascii_line_uses_compact_visual_segments() -> None:
    segments = _line_visual_segments("x" * 1_000_000, 78)

    assert len(segments) == 13_158
    assert segments[0].start == 0 and segments[0].end == 75
    assert segments[-1].end == 1_000_000


@pytest.mark.parametrize(
    ("text", "expected_height"),
    [
        ("", 1),
        ("\n".join(str(index) for index in range(5)), 5),
        ("\n".join(str(index) for index in range(11)), COMPOSER_MAX_CONTENT_ROWS),
    ],
)
def test_composer_starts_grows_and_caps_content_height(text: str, expected_height: int) -> None:
    result, ui = _run_prompt(f"{_paste(text)}\r")
    render_info = ui._prompt_window.render_info

    assert result == text
    assert render_info.window_height == expected_height
    assert render_info.cursor_position.y < expected_height


def test_more_than_ten_rows_scroll_inside_composer_and_keep_cursor_visible() -> None:
    text = "\n".join(str(index) for index in range(11))

    _result, ui = _run_prompt(f"{_paste(text)}\r")
    render_info = ui._prompt_window.render_info

    assert render_info.window_height == COMPOSER_MAX_CONTENT_ROWS
    assert render_info.vertical_scroll > 0
    assert render_info.cursor_position.y == COMPOSER_MAX_CONTENT_ROWS - 1


def test_long_wrapped_line_scrolls_without_corrupting_frame() -> None:
    output = RecordingOutput()
    text = "wide content " * 300

    result, ui = _run_prompt(f"{_paste(text)}\r", output=output)
    render_info = ui._prompt_window.render_info

    assert result == text
    assert render_info.window_height == COMPOSER_MAX_CONTENT_ROWS
    assert ui._prompt_window.vertical_scroll_2 > 0
    assert render_info.cursor_position.y == COMPOSER_MAX_CONTENT_ROWS - 1
    assert "┌" in output.text and "└" in output.text and "│" in output.text


def test_bracketed_multiline_paste_preserves_indentation_and_submits_once() -> None:
    ui, pipe_state = _new_ui()
    _pipe_context, pipe = pipe_state
    accept_count = 0
    original_accept = ui._prompt_session.default_buffer.accept_handler

    def counted_accept(buffer: object) -> bool:
        nonlocal accept_count
        accept_count += 1
        return original_accept(buffer)

    ui._prompt_session.default_buffer.accept_handler = counted_accept
    try:
        pipe.send_text(f"{_paste('  a\r\n\tb \r')}\r")
        result = ui.user_prompt()
    finally:
        _close_pipe(pipe_state)

    assert result == "  a\n\tb \n"
    assert accept_count == 1


def test_large_bracketed_paste_is_preserved_exactly() -> None:
    text = "\n".join(f"    line {index}: {'x' * 80}" for index in range(200))

    result, _ui = _run_prompt(f"{_paste(text)}\r")

    assert result == text


def test_valid_outer_whitespace_is_returned_and_stored_unchanged() -> None:
    history = InMemoryHistory()

    result, _ui = _run_prompt("  code  \r", history=history)

    assert result == "  code  "
    assert history.get_strings() == ["  code  "]


def test_whitespace_only_prompt_is_returned_but_not_added_to_history() -> None:
    history = InMemoryHistory()

    result, _ui = _run_prompt("   \r", history=history)

    assert result == "   "
    assert history.get_strings() == []


def test_prompt_eof_and_keyboard_interrupt_behavior() -> None:
    with pytest.raises(EOFError):
        _run_prompt("\x04")
    with pytest.raises(KeyboardInterrupt):
        _run_prompt("\x03")


def test_no_color_composer_emits_no_color_sgr_sequences() -> None:
    captured = StringIO()
    output = Vt100_Output(
        captured,
        lambda: Size(rows=40, columns=80),
        term="xterm",
        enable_cpr=False,
    )

    _result, _ui = _run_prompt("x\r", output=output)

    sgr_sequences = set(re.findall(r"\x1b\[[0-9;]*m", captured.getvalue()))
    assert sgr_sequences <= {"\x1b[0m"}


def test_terminal_resize_reflows_content_with_one_attached_frame() -> None:
    async def exercise() -> tuple[str, list[tuple[int, int, int, int]], bool]:
        output = RecordingOutput(columns=80)
        with create_pipe_input() as pipe:
            ui = TerminalUI(Console(file=StringIO(), no_color=True), no_color=True)
            session = ui._create_prompt_session(input=pipe, output=output)
            ui._prompt_session = session
            root_container_id = id(session.layout.container)
            renders: asyncio.Queue[tuple[int, int, int, int]] = asyncio.Queue()

            def record_render(_app: object) -> None:
                info = ui._prompt_window.render_info
                if info is not None and len(session.default_buffer.text) == 120:
                    renders.put_nowait(
                        (output.columns, info.window_width, info.window_height, info.cursor_position.y)
                    )

            session.app.after_render += record_render

            async def expect_render(expected: tuple[int, int, int]) -> tuple[int, int, int, int]:
                while True:
                    state = await asyncio.wait_for(renders.get(), timeout=1.0)
                    if state[:3] == expected:
                        return state

            try:
                task = asyncio.create_task(
                    session.prompt_async(
                        COMPOSER_PROMPT,
                        bottom_toolbar=ui._bottom_toolbar,
                        show_frame=True,
                        default="x" * 120,
                    )
                )
                initial = await expect_render((80, 78, 2))

                output.columns = 30
                session.app.invalidate()
                narrow = await expect_render((30, 28, 5))

                output.columns = 80
                session.app.invalidate()
                wide = await expect_render((80, 78, 2))

                pipe.send_text("\r")
                result = await task
                return result, [initial, narrow, wide], id(session.layout.container) == root_container_id
            finally:
                session.app.after_render -= record_render

    result, states, frame_remained_attached = asyncio.run(exercise())

    assert result == "x" * 120
    assert any(
        columns == 30 and width == 28 and height == 5 and cursor_y < height
        for columns, width, height, cursor_y in states
    )
    assert any(
        columns == 80 and width == 78 and height == 2 and cursor_y < height
        for columns, width, height, cursor_y in states
    )
    assert frame_remained_attached is True
