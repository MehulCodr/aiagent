from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from code_agent.tools.shell import classify_command


class PermissionProfile(StrEnum):
    STRICT = "strict"
    RELAXED = "relaxed"
    READ_ONLY = "read-only"


class ApprovalCallback(Protocol):
    def __call__(self, tool_name: str, arguments: dict[str, Any], reason: str) -> bool:
        raise NotImplementedError


class PermissionDecision(BaseModel):
    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    risk: str = "safe"


@dataclass(frozen=True)
class PermissionPolicy:
    profile: PermissionProfile = PermissionProfile.STRICT

    @classmethod
    def from_name(cls, name: str | None) -> "PermissionPolicy":
        if not name:
            return cls()
        try:
            return cls(PermissionProfile(name))
        except ValueError as exc:
            known = ", ".join(item.value for item in PermissionProfile)
            raise ValueError(f"Unknown permission profile '{name}'. Known profiles: {known}") from exc

    def evaluate(self, tool_name: str, arguments: dict[str, Any], root: Path) -> PermissionDecision:
        if self.profile == PermissionProfile.READ_ONLY and tool_name in {"write_file", "edit_file", "shell"}:
            return PermissionDecision(
                allowed=False,
                reason=f"{tool_name} is blocked by the read-only permission profile.",
                risk="blocked",
            )

        if tool_name != "shell":
            return PermissionDecision(allowed=True, reason="Tool allowed by permission profile.")

        command = str(arguments.get("command") or "")
        allow_outside_root = bool(arguments.get("allow_outside_root", False))
        risk, reason = classify_command(command, root, allow_outside_root)
        if risk == "blocked":
            return PermissionDecision(allowed=False, reason=reason, risk=risk)

        if self.profile == PermissionProfile.STRICT:
            return PermissionDecision(
                allowed=True,
                requires_approval=True,
                reason=reason if risk != "safe" else "Shell commands require approval in strict mode.",
                risk=risk,
            )

        if risk != "safe":
            return PermissionDecision(allowed=True, requires_approval=True, reason=reason, risk=risk)

        return PermissionDecision(allowed=True, reason=reason, risk=risk)


class ApprovalLayer:
    def __init__(
        self,
        *,
        policy: PermissionPolicy,
        callback: ApprovalCallback | None = None,
        auto_approve: bool = False,
    ) -> None:
        self.policy = policy
        self.callback = callback
        self.auto_approve = auto_approve

    def authorize(self, tool_name: str, arguments: dict[str, Any], root: Path) -> PermissionDecision:
        decision = self.policy.evaluate(tool_name, arguments, root)
        if not decision.allowed or not decision.requires_approval:
            return decision
        if self.auto_approve:
            return decision.model_copy(update={"requires_approval": False, "reason": f"Auto-approved: {decision.reason}"})
        if self.callback is None:
            return decision.model_copy(update={"allowed": False, "reason": f"Approval required: {decision.reason}"})
        if self.callback(tool_name, arguments, decision.reason):
            return decision.model_copy(update={"requires_approval": False, "reason": f"Approved: {decision.reason}"})
        return decision.model_copy(update={"allowed": False, "reason": f"Denied: {decision.reason}"})
