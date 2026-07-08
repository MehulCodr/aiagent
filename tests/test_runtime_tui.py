from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from code_agent.agent import AgentRuntime
from code_agent.config import AgentConfig
from code_agent.messages import ChatMessage, ProviderEvent, ToolCall
from code_agent.providers.base import LLMProvider, ModelInfo
from code_agent.session import SessionStore
from code_agent.tools.base import Tool, ToolContext, ToolDefinition, ToolRegistry, ToolResult


class RecordingSpinner:
    def __init__(self, events: list[str], label: str) -> None:
        self.events = events
        self.label = label
        self.active = False

    def __enter__(self) -> RecordingSpinner:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if not self.active:
            self.events.append(f"start:{self.label}")
            self.active = True

    def stop(self) -> None:
        if self.active:
            self.events.append(f"stop:{self.label}")
            self.active = False


class RecordingUI:
    def __init__(self) -> None:
        self.events: list[str] = []

    def thinking(self, *, step: int, model: str) -> RecordingSpinner:
        return RecordingSpinner(self.events, f"thinking:{model}:{step}")

    def executing_tool(self, name: str) -> RecordingSpinner:
        return RecordingSpinner(self.events, f"tool:{name}")

    def assistant_response(self, text: str) -> None:
        self.events.append(f"assistant:{text}")

    def tool_call(self, call: ToolCall) -> None:
        self.events.append(f"tool_call:{call.name}")

    def tool_result(self, name: str, result: ToolResult) -> None:
        self.events.append(f"tool_result:{name}:{result.content}")

    def info(self, message: str) -> None:
        self.events.append(f"info:{message}")

    def error(self, message: str) -> None:
        self.events.append(f"error:{message}")

    def warning(self, message: str) -> None:
        self.events.append(f"warning:{message}")

    def confirm_shell(self, command: str, reason: str) -> bool:
        self.events.append(f"confirm:{command}:{reason}")
        return True


class FakeProvider(LLMProvider):
    id = "fake"
    display_name = "Fake"
    default_model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    def list_models(self) -> list[ModelInfo]:
        return []

    def stream_chat(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Iterator[ProviderEvent]:
        self.calls += 1
        if self.calls == 1:
            yield ProviderEvent(
                type="tool_calls",
                tool_calls=[ToolCall(id="call-1", name="echo", arguments={"text": "hello"})],
            )
            return
        yield ProviderEvent(type="text", text="done")


class EchoTool(Tool):
    definition = ToolDefinition(
        name="echo",
        description="Echo text.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )

    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content=arguments["text"])


def test_runtime_uses_spinners_for_thinking_and_tool_execution(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = store.create(provider="fake", model="fake-model")
    tools = ToolRegistry()
    tools.register(EchoTool())
    ui = RecordingUI()
    runtime = AgentRuntime(
        root=tmp_path,
        config=AgentConfig(provider="fake", model="fake-model", max_steps=3, require_shell_confirmation=False),
        provider=FakeProvider(),
        model="fake-model",
        session=session,
        session_store=store,
        tools=tools,
        ui=ui,  # type: ignore[arg-type]
    )

    assert runtime.run_user_turn("use a tool") == "done"

    assert ui.events == [
        "start:thinking:fake-model:1",
        "stop:thinking:fake-model:1",
        "tool_call:echo",
        "start:tool:echo",
        "stop:tool:echo",
        "tool_result:echo:hello",
        "info:Continuing after tool step 1...",
        "start:thinking:fake-model:2",
        "stop:thinking:fake-model:2",
        "assistant:done",
    ]
