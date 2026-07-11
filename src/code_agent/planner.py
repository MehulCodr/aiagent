from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from code_agent.config import AgentConfig, agent_dir
from code_agent.messages import ChatMessage
from code_agent.observability import Observer
from code_agent.providers.base import LLMProvider, ProviderError


class Plan(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    goal: str
    body: str
    provider: str
    model: str
    status: str = "draft"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class PlanStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.directory = agent_dir(self.root) / "plans"
        self.directory.mkdir(parents=True, exist_ok=True)

    @property
    def last_plan_path(self) -> Path:
        return self.directory / "last_plan.json"

    def save(self, plan: Plan) -> Path:
        plan.updated_at = datetime.now(UTC).isoformat()
        path = self.directory / f"{plan.id}.json"
        path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        self.last_plan_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def load_last(self) -> Plan:
        if not self.last_plan_path.exists():
            raise FileNotFoundError("No saved plan found. Run `code-agent plan ...` first.")
        return Plan.model_validate(json.loads(self.last_plan_path.read_text(encoding="utf-8")))

    def mark_applied(self, plan: Plan) -> None:
        plan.status = "applied"
        self.save(plan)


class Planner:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        model: str,
        config: AgentConfig,
        observer: Observer | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.config = config
        self.observer = observer

    def create_plan(self, goal: str, *, repository_context: str = "") -> Plan:
        system_prompt = _planner_system_prompt(repository_context)
        messages = [ChatMessage(role="user", content=goal)]
        timer = self.observer.timer() if self.observer else None
        usage = None
        body = ""
        try:
            for event in self.provider.stream_chat(
                model=self.model,
                system_prompt=system_prompt,
                messages=messages,
                tools=[],
                temperature=self.config.temperature,
                max_output_tokens=self.config.max_output_tokens,
            ):
                if event.type == "text":
                    body += event.text
                if event.usage is not None:
                    usage = event.usage
        except ProviderError:
            raise
        finally:
            if self.observer and timer:
                self.observer.record_response(
                    provider=self.provider.id,
                    model=self.model,
                    latency_ms=timer.elapsed_ms(),
                    usage=usage,
                )
        return Plan(goal=goal, body=body.strip(), provider=self.provider.id, model=self.model)


def build_apply_prompt(plan: Plan, extra_instruction: str | None = None) -> str:
    parts = [
        "Apply this reviewed plan. Execute the concrete coding and verification steps needed to complete it.",
        "",
        f"Plan id: {plan.id}",
        plan.body,
    ]
    if extra_instruction:
        parts.extend(["", "Additional instruction:", extra_instruction])
    return "\n".join(parts)


def _planner_system_prompt(repository_context: str) -> str:
    parts = [
        "You are the planning mode of code-agent.",
        "Create a practical implementation plan only. Do not call tools or claim changes were made.",
        "Include verification steps and note risky operations that should require approval.",
        "Write the plan in concise Markdown; the terminal UI renders Markdown for display.",
        "Use compact sections such as Goal, Steps, Verification, and Risks when structure helps.",
        "When repository excerpts are relevant, cite paths and line ranges exactly in this form: src/file.py:10-24.",
    ]
    if repository_context:
        parts.extend(["", "Repository context:", repository_context])
    return "\n".join(parts)
