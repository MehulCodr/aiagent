from __future__ import annotations

import json
import os
from uuid import uuid4

from code_agent.messages import ChatMessage, ProviderEvent, ProviderUsage, ToolCall
from code_agent.providers.base import LLMProvider, ModelInfo, ProviderError
from code_agent.tools.base import ToolDefinition


class OpenAIProvider(LLMProvider):
    id = "openai"
    display_name = "OpenAI"
    default_model = "gpt-4.1-mini"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise ProviderError("OPENAI_API_KEY is required for OpenAI.")
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def list_models(self) -> list[ModelInfo]:
        client = self._get_client()
        try:
            return [
                ModelInfo(provider=self.id, name=model.id, display_name=model.id, supports_tools=True)
                for model in client.models.list().data
            ]
        except Exception as exc:
            raise ProviderError(f"Could not list OpenAI models: {exc}") from exc

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
        client = self._get_client()
        request = {
            "model": model,
            "messages": [{"role": "system", "content": system_prompt}, *_to_openai_messages(messages)],
            "stream": True,
        }
        if tools:
            request["tools"] = [tool.as_openai_tool() for tool in tools]
            request["tool_choice"] = "auto"
        request["stream_options"] = {"include_usage": True}
        if temperature is not None:
            request["temperature"] = temperature
        if max_output_tokens is not None:
            request["max_completion_tokens"] = max_output_tokens

        tool_state: dict[int, dict[str, str]] = {}
        usage: ProviderUsage | None = None
        try:
            stream = client.chat.completions.create(**request)
            for chunk in stream:
                raw_usage = getattr(chunk, "usage", None)
                if raw_usage is not None:
                    usage = ProviderUsage(
                        input_tokens=getattr(raw_usage, "prompt_tokens", None),
                        output_tokens=getattr(raw_usage, "completion_tokens", None),
                        total_tokens=getattr(raw_usage, "total_tokens", None),
                    )
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield ProviderEvent(type="text", text=content)
                for tool_call in getattr(delta, "tool_calls", None) or []:
                    index = int(getattr(tool_call, "index", 0) or 0)
                    state = tool_state.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if getattr(tool_call, "id", None):
                        state["id"] = tool_call.id
                    function = getattr(tool_call, "function", None)
                    if function is not None:
                        if getattr(function, "name", None):
                            state["name"] = function.name
                        if getattr(function, "arguments", None):
                            state["arguments"] += function.arguments
        except Exception as exc:
            raise ProviderError(f"OpenAI request failed for model '{model}': {exc}") from exc

        calls = [_openai_state_to_call(index, state) for index, state in sorted(tool_state.items()) if state.get("name")]
        if calls:
            yield ProviderEvent(type="tool_calls", tool_calls=calls)
        yield ProviderEvent(type="done", usage=usage)


def _to_openai_messages(messages: list[ChatMessage]) -> list[dict]:
    converted = []
    for message in messages:
        if message.role == "system":
            continue
        if message.role == "assistant":
            item = {"role": "assistant", "content": message.content or None}
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for call in message.tool_calls
                ]
            converted.append(item)
        elif message.role == "tool":
            converted.append(
                {
                    "role": "tool",
                    "tool_call_id": message.tool_call_id,
                    "content": message.content,
                }
            )
        else:
            converted.append({"role": "user", "content": message.content})
    return converted


def _openai_state_to_call(index: int, state: dict[str, str]) -> ToolCall:
    raw_args = state.get("arguments") or "{}"
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        args = {"_raw": raw_args}
    return ToolCall(
        id=state.get("id") or f"call-{index}-{uuid4().hex[:8]}",
        name=state["name"],
        arguments=args,
    )
