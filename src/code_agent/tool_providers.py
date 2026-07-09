from __future__ import annotations

from typing import Protocol, runtime_checkable

from code_agent.tools.base import ToolContext, ToolDefinition, ToolResult


@runtime_checkable
class ToolProvider(Protocol):
    def definitions(self) -> list[ToolDefinition]:
        raise NotImplementedError

    def run(self, name: str, arguments: dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError


@runtime_checkable
class ExternalToolProvider(Protocol):
    """Interface for future MCP-style external tool providers."""

    def definitions(self) -> list[ToolDefinition]:
        raise NotImplementedError

    def invoke(self, name: str, arguments: dict, context: ToolContext) -> ToolResult:
        raise NotImplementedError
