from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from code_agent.config import agent_dir
from code_agent.messages import ProviderUsage


class ObservationEvent(BaseModel):
    type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    fields: dict[str, Any] = Field(default_factory=dict)


class Timer:
    def __init__(self) -> None:
        self.started = perf_counter()

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self.started) * 1000, 3)


class Observer:
    def __init__(self, root: Path, *, verbose: bool = False) -> None:
        self.root = root.resolve()
        self.verbose = verbose
        self.events: list[ObservationEvent] = []
        self.log_path = agent_dir(self.root) / "logs" / "debug.jsonl"

    def timer(self) -> Timer:
        return Timer()

    def record(self, event_type: str, **fields: Any) -> ObservationEvent:
        event = ObservationEvent(type=event_type, fields=fields)
        self.events.append(event)
        if self.verbose:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
        return event

    def record_response(
        self,
        *,
        provider: str,
        model: str,
        latency_ms: float,
        usage: ProviderUsage | None = None,
    ) -> ObservationEvent:
        fields: dict[str, Any] = {"provider": provider, "model": model, "latency_ms": latency_ms}
        if usage is not None:
            fields["usage"] = usage.model_dump(exclude_none=True)
        return self.record("llm_response", **fields)

    def record_tool(self, *, name: str, duration_ms: float, is_error: bool) -> ObservationEvent:
        return self.record("tool_execution", name=name, duration_ms=duration_ms, is_error=is_error)
