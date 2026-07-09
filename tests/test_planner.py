from __future__ import annotations

from collections.abc import Iterator
from io import StringIO
from pathlib import Path
from typing import Any

from rich.console import Console

from code_agent.agent import AgentRuntime
from code_agent.config import AgentConfig
from code_agent.messages import ChatMessage, ProviderEvent, ToolCall
from code_agent.planner import Plan, PlanStore, Planner, build_apply_prompt
from code_agent.providers.base import LLMProvider, ModelInfo
from code_agent.session import SessionStore
from code_agent.tools import build_default_tool_registry
from code_agent.ui import TerminalUI


class FakeProvider(LLMProvider):
    id = "fake"
    display_name = "Fake"
    default_model = "fake-model"

    def __init__(self, scripts: list[list[ProviderEvent]]) -> None:
        self.scripts = scripts

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(provider=self.id, name=self.default_model)]

    def stream_chat(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[ChatMessage],
        tools: list[Any],
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Iterator[ProviderEvent]:
        del model, system_prompt, messages, tools, temperature, max_output_tokens
        for event in self.scripts.pop(0):
            yield event


def test_planner_persists_last_plan(tmp_path: Path) -> None:
    provider = FakeProvider([[ProviderEvent(type="text", text="1. Update src/app.py\n"), ProviderEvent(type="done")]])
    config = AgentConfig(rag_enabled=False)
    plan = Planner(provider=provider, model="fake-model", config=config).create_plan("add feature")
    store = PlanStore(tmp_path)
    store.save(plan)

    loaded = store.load_last()

    assert loaded.body == "1. Update src/app.py"
    assert loaded.goal == "add feature"
    assert build_apply_prompt(loaded).startswith("Apply this reviewed plan.")


def test_runtime_apply_executes_saved_plan(tmp_path: Path) -> None:
    provider = FakeProvider(
        [
            [
                ProviderEvent(
                    type="tool_calls",
                    tool_calls=[
                        ToolCall(
                            id="write",
                            name="write_file",
                            arguments={"path": "out.txt", "content": "done\n", "overwrite": True},
                        )
                    ],
                ),
                ProviderEvent(type="done"),
            ],
            [ProviderEvent(type="text", text="implemented"), ProviderEvent(type="done")],
        ]
    )
    config = AgentConfig(rag_enabled=False, require_shell_confirmation=False, max_steps=3)
    store = SessionStore(tmp_path)
    runtime = AgentRuntime(
        root=tmp_path,
        config=config,
        provider=provider,
        model="fake-model",
        session=store.create(provider="fake", model="fake-model"),
        session_store=store,
        tools=build_default_tool_registry(),
        ui=TerminalUI(Console(file=StringIO(), force_terminal=False)),
        auto_approve=True,
    )
    plan = Plan(goal="write output", body="Write out.txt", provider="fake", model="fake-model")

    runtime.apply_plan(plan)

    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "done\n"
    assert runtime.load_last_plan().status == "applied"
