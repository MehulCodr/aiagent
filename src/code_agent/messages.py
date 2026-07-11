from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    provider_data: dict = Field(default_factory=dict)


class ProviderUsage(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None


class ChatMessage(BaseModel):
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


class ProviderEvent(BaseModel):
    type: Literal["text", "tool_calls", "done"]
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: ProviderUsage | None = None
