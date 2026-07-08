from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field


ApprovalCallback = Callable[[str, str], bool]


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    def as_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolResult(BaseModel):
    content: str
    is_error: bool = False


@dataclass
class ToolContext:
    root: Path
    approval_callback: ApprovalCallback | None = None
    auto_approve: bool = False


class Tool(ABC):
    definition: ToolDefinition

    @abstractmethod
    def run(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def validate(self, arguments: dict[str, Any]) -> None:
        Draft202012Validator(self.definition.parameters).validate(arguments)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.definition.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.definition.name}")
        self._tools[tool.definition.name] = tool

    def definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def run(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(content=f"Unknown tool: {name}", is_error=True)
        try:
            tool.validate(arguments)
            return tool.run(context, arguments)
        except Exception as exc:
            return ToolResult(content=f"{type(exc).__name__}: {exc}", is_error=True)
