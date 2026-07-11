from __future__ import annotations

from pathlib import Path

from code_agent.approval import ApprovalLayer, PermissionDecision, PermissionPolicy, PermissionProfile
from code_agent.execution import ExecutionEngine
from code_agent.messages import ToolCall
from code_agent.observability import Observer
from code_agent.tools import build_default_tool_registry


def test_execution_engine_runs_parallel_safe_tools_in_order_and_logs(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("bravo", encoding="utf-8")
    observer = Observer(tmp_path, verbose=True)
    engine = ExecutionEngine(
        root=tmp_path,
        tools=build_default_tool_registry(),
        approval=ApprovalLayer(policy=PermissionPolicy(PermissionProfile.STRICT), auto_approve=True),
        observer=observer,
    )

    records = engine.run_many(
        [
            ToolCall(id="1", name="read_file", arguments={"path": "a.txt"}),
            ToolCall(id="2", name="read_file", arguments={"path": "b.txt"}),
        ]
    )

    assert [record.call_id for record in records] == ["1", "2"]
    assert [record.result.content for record in records] == ["alpha", "bravo"]
    assert all(record.duration_ms >= 0 for record in records)
    assert observer.log_path.exists()
    assert "tool_execution" in observer.log_path.read_text(encoding="utf-8")


def test_execution_engine_collects_tool_errors(tmp_path: Path) -> None:
    engine = ExecutionEngine(
        root=tmp_path,
        tools=build_default_tool_registry(),
        approval=ApprovalLayer(policy=PermissionPolicy(PermissionProfile.STRICT), auto_approve=True),
    )

    records = engine.run_many([ToolCall(id="missing", name="read_file", arguments={"path": "missing.txt"})])

    assert records[0].result.is_error
    assert "Not a file" in records[0].result.content


def test_execution_engine_uses_precomputed_permission_decisions(tmp_path: Path) -> None:
    def fail_callback(*_args) -> bool:
        raise AssertionError("approval callback should not be called during execution")

    engine = ExecutionEngine(
        root=tmp_path,
        tools=build_default_tool_registry(),
        approval=ApprovalLayer(policy=PermissionPolicy(PermissionProfile.STRICT), callback=fail_callback),
    )

    records = engine.run_many(
        [ToolCall(id="shell", name="shell", arguments={"command": "echo ok"})],
        decisions=[PermissionDecision(allowed=True, requires_approval=False, reason="Approved")],
    )

    assert records[0].result.content.startswith("exit_code: 0")
