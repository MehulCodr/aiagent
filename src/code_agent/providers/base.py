from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

from code_agent.messages import ChatMessage, ProviderEvent
from code_agent.tools.base import ToolDefinition


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    name: str
    display_name: str | None = None
    supports_tools: bool = True


class LLMProvider(ABC):
    id: str
    display_name: str
    default_model: str

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError


class ProviderError(RuntimeError):
    pass
