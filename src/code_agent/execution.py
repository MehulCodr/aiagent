from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from code_agent.approval import ApprovalLayer, PermissionDecision
from code_agent.messages import ToolCall
from code_agent.observability import Observer
from code_agent.tools import ToolRegistry
from code_agent.tools.base import ToolContext, ToolResult


class ToolExecutionRecord(BaseModel):
    index: int
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: ToolResult
    duration_ms: float
    started_at: str
    ended_at: str
    permission: PermissionDecision


class ExecutionEngine:
    def __init__(
        self,
        *,
        root: Path,
        tools: ToolRegistry,
        approval: ApprovalLayer,
        observer: Observer | None = None,
        max_workers: int = 4,
    ) -> None:
        self.root = root.resolve()
        self.tools = tools
        self.approval = approval
        self.observer = observer
        self.max_workers = max_workers

    def run_many(self, calls: list[ToolCall]) -> list[ToolExecutionRecord]:
        records: list[ToolExecutionRecord] = []
        index = 0
        while index < len(calls):
            call = calls[index]
            if self.tools.is_parallel_safe(call.name):
                group: list[tuple[int, ToolCall]] = []
                while index < len(calls) and self.tools.is_parallel_safe(calls[index].name):
                    group.append((index, calls[index]))
                    index += 1
                records.extend(self._run_parallel_group(group))
            else:
                records.append(self._run_one(index, call))
                index += 1
        return sorted(records, key=lambda record: record.index)

    def _run_parallel_group(self, group: list[tuple[int, ToolCall]]) -> list[ToolExecutionRecord]:
        if len(group) == 1:
            index, call = group[0]
            return [self._run_one(index, call)]
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(group))) as executor:
            futures = {executor.submit(self._run_one, index, call): index for index, call in group}
            records = [future.result() for future in as_completed(futures)]
        return sorted(records, key=lambda record: record.index)

    def _run_one(self, index: int, call: ToolCall) -> ToolExecutionRecord:
        started_at = datetime.now(UTC).isoformat()
        timer = self.observer.timer() if self.observer else None
        decision = self.approval.authorize(call.name, call.arguments, self.root)
        if decision.allowed:
            context = ToolContext(root=self.root, auto_approve=True)
            result = self.tools.run(call.name, call.arguments, context)
        else:
            result = ToolResult(content=decision.reason, is_error=True)
        duration_ms = timer.elapsed_ms() if timer else 0.0
        ended_at = datetime.now(UTC).isoformat()
        if self.observer:
            self.observer.record_tool(name=call.name, duration_ms=duration_ms, is_error=result.is_error)
        return ToolExecutionRecord(
            index=index,
            call_id=call.id,
            name=call.name,
            arguments=call.arguments,
            result=result,
            duration_ms=duration_ms,
            started_at=started_at,
            ended_at=ended_at,
            permission=decision,
        )
