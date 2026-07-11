from __future__ import annotations

import json
import os
from uuid import uuid4

import httpx

from code_agent.messages import ChatMessage, ProviderEvent, ProviderUsage, ToolCall
from code_agent.providers.base import LLMProvider, ModelInfo, ProviderError
from code_agent.tools.base import ToolDefinition


class OllamaProvider(LLMProvider):
    id = "ollama"
    display_name = "Ollama"
    default_model = "qwen3"

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")

    def list_models(self) -> list[ModelInfo]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            data = response.json()
            return [
                ModelInfo(provider=self.id, name=item["name"], display_name=item.get("name"), supports_tools=True)
                for item in data.get("models", [])
                if item.get("name")
            ]
        except Exception as exc:
            raise ProviderError(f"Could not list Ollama models at {self.base_url}: {exc}") from exc

    def stream_chat(
        self,
        *,
        model: str,
        system_prompt: str,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ):
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, *_to_ollama_messages(messages)],
            "tools": [tool.as_openai_tool() for tool in tools],
            "stream": True,
        }
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_output_tokens is not None:
            options["num_predict"] = max_output_tokens
        if options:
            payload["options"] = options

        tool_calls: list[ToolCall] = []
        usage: ProviderUsage | None = None
        try:
            with httpx.stream("POST", f"{self.base_url}/api/chat", json=payload, timeout=None) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    message = data.get("message") or {}
                    content = message.get("content") or ""
                    if content:
                        yield ProviderEvent(type="text", text=content)
                    for raw_call in message.get("tool_calls") or []:
                        tool_calls.append(_ollama_call(raw_call, len(tool_calls)))
                    if data.get("done"):
                        input_tokens = data.get("prompt_eval_count")
                        output_tokens = data.get("eval_count")
                        total_tokens = None
                        if input_tokens is not None or output_tokens is not None:
                            total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
                        usage = ProviderUsage(
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            total_tokens=total_tokens,
                        )
        except Exception as exc:
            raise ProviderError(f"Ollama request failed for model '{model}': {exc}") from exc

        if tool_calls:
            yield ProviderEvent(type="tool_calls", tool_calls=tool_calls)
        yield ProviderEvent(type="done", usage=usage)


def _to_ollama_messages(messages: list[ChatMessage]) -> list[dict]:
    converted = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "assistant":
            item = {"role": "assistant", "content": message.content}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "type": "function",
                        "function": {
                            "index": index,
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    }
                    for index, call in enumerate(message.tool_calls)
                ]
            converted.append(item)
        elif message.role == "tool":
            converted.append({"role": "tool", "tool_name": message.name, "content": message.content})
        else:
            converted.append({"role": "user", "content": message.content})
    return converted


def _ollama_call(raw_call: dict, index: int) -> ToolCall:
    function = raw_call.get("function") or {}
    return ToolCall(
        id=raw_call.get("id") or f"ollama-{index}-{uuid4().hex[:8]}",
        name=function.get("name", ""),
        arguments=function.get("arguments") or {},
    )
