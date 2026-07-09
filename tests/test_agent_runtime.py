from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Console

from code_agent.agent import AgentRuntime
from code_agent.config import AgentConfig
from code_agent.messages import ToolCall
from code_agent.providers.base import LLMProvider, ModelInfo
from code_agent.session import SessionStore
from code_agent.tools import build_default_tool_registry
from code_agent.tools.base import ToolResult
from code_agent.ui import TerminalUI


class EmptyProvider(LLMProvider):
    id = "fake"
    display_name = "Fake"
    default_model = "fake-model"

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(provider=self.id, name=self.default_model)]

    def stream_chat(self, **_kwargs: Any) -> Iterator[Any]:
        return iter(())


class RecordingStatus:
    def update(self, *_args: Any, **_kwargs: Any) -> None:
        pass


class RecordingUI(TerminalUI):
    def __init__(self, *, approved: bool = True) -> None:
        super().__init__(Console(file=StringIO(), force_terminal=False), no_color=True)
        self.approved = approved
        self.events: list[str] = []

    @contextmanager
    def activity(self, message: str) -> Iterator[RecordingStatus]:
        self.events.append(f"activity:{message}")
        yield RecordingStatus()

    def confirm_tool(self, tool_name: str, arguments: dict[str, Any], reason: str) -> bool:
        self.events.append(f"confirm:{tool_name}:{arguments.get('command')}:{reason}")
        return self.approved

    def tool_call(self, call: ToolCall) -> None:
        self.events.append(f"tool_call:{call.name}")

    def tool_result(self, name: str, result: ToolResult) -> None:
        self.events.append(f"tool_result:{name}:{result.is_error}")

    def tool_timeline(self, records: list[Any]) -> None:
        self.events.append(f"timeline:{len(records)}")


def test_runtime_prompts_for_shell_approval_before_calling_tool_spinner(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    ui = RecordingUI()
    runtime = AgentRuntime(
        root=tmp_path,
        config=AgentConfig(rag_enabled=False, require_shell_confirmation=True, permission_profile="strict"),
        provider=EmptyProvider(),
        model="fake-model",
        session=store.create(provider="fake", model="fake-model"),
        session_store=store,
        tools=build_default_tool_registry(),
        ui=ui,
        auto_approve=False,
    )

    runtime._run_tool_calls([ToolCall(id="shell", name="shell", arguments={"command": "echo ok"})])

    assert ui.events.index("confirm:shell:echo ok:Shell commands require approval in strict mode.") < ui.events.index(
        "activity:Calling 1 tool..."
    )


def test_runtime_does_not_show_calling_spinner_when_shell_approval_is_denied(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    ui = RecordingUI(approved=False)
    runtime = AgentRuntime(
        root=tmp_path,
        config=AgentConfig(rag_enabled=False, require_shell_confirmation=True, permission_profile="strict"),
        provider=EmptyProvider(),
        model="fake-model",
        session=store.create(provider="fake", model="fake-model"),
        session_store=store,
        tools=build_default_tool_registry(),
        ui=ui,
        auto_approve=False,
    )

    runtime._run_tool_calls([ToolCall(id="shell", name="shell", arguments={"command": "echo ok"})])

    assert "confirm:shell:echo ok:Shell commands require approval in strict mode." in ui.events
    assert "activity:Calling 1 tool..." not in ui.events
