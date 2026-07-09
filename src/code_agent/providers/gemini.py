from __future__ import annotations

import base64
import os
from typing import Any
from uuid import uuid4

from code_agent.messages import ChatMessage, ProviderEvent, ProviderUsage, ToolCall
from code_agent.providers.base import LLMProvider, ModelInfo, ProviderError
from code_agent.tools.base import ToolDefinition


class GeminiProvider(LLMProvider):
    id = "gemini"
    display_name = "Google Gemini"
    default_model = "gemini-2.5-flash"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._client = None

    def _get_client(self):
        if not self.api_key:
            raise ProviderError("GEMINI_API_KEY or GOOGLE_API_KEY is required for Gemini.")
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def list_models(self) -> list[ModelInfo]:
        client = self._get_client()
        models: list[ModelInfo] = []
        try:
            for model in client.models.list():
                raw_name = str(getattr(model, "name", ""))
                name = raw_name.split("/")[-1] if raw_name else ""
                if not name:
                    continue
                actions = list(getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None) or [])
                supports_generate = not actions or any("generate" in str(action).lower() for action in actions)
                display = getattr(model, "display_name", None)
                models.append(
                    ModelInfo(
                        provider=self.id,
                        name=name,
                        display_name=display,
                        supports_tools=supports_generate,
                    )
                )
        except Exception as exc:
            raise ProviderError(f"Could not list Gemini models: {exc}") from exc
        return models

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
        from google.genai import types

        contents = [_to_gemini_content(message, types) for message in messages if message.role != "system"]
        config_kwargs = {
            "system_instruction": system_prompt,
            "tools": [_to_gemini_tool(tools, types)] if tools else None,
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if temperature is not None:
            config_kwargs["temperature"] = temperature
        if max_output_tokens is not None:
            config_kwargs["max_output_tokens"] = max_output_tokens
        config = types.GenerateContentConfig(**{key: value for key, value in config_kwargs.items() if value is not None})

        collected_calls: list[ToolCall] = []
        seen_calls: set[str] = set()
        usage: ProviderUsage | None = None
        try:
            stream = client.models.generate_content_stream(model=model, contents=contents, config=config)
            for chunk in stream:
                usage = _extract_usage(chunk) or usage
                text = _safe_chunk_text(chunk)
                if text:
                    yield ProviderEvent(type="text", text=text)
                for call in _extract_gemini_calls(chunk):
                    key = f"{call.name}:{call.arguments}"
                    if key not in seen_calls:
                        seen_calls.add(key)
                        collected_calls.append(call)
        except Exception as exc:
            raise ProviderError(f"Gemini request failed for model '{model}': {exc}") from exc
        if collected_calls:
            yield ProviderEvent(type="tool_calls", tool_calls=collected_calls)
        yield ProviderEvent(type="done", usage=usage)


def _to_gemini_tool(tools: list[ToolDefinition], types):
    declarations = []
    for tool in tools:
        declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=_sanitize_schema(tool.parameters),
            )
        )
    return types.Tool(function_declarations=declarations)


def _to_gemini_content(message: ChatMessage, types):
    parts = []
    if message.role == "tool":
        response = {"result": message.content}
        return types.Content(
            role="tool",
            parts=[types.Part.from_function_response(name=message.name or "tool", response=response)],
        )
    if message.content:
        parts.append(types.Part.from_text(text=message.content))
    if message.role == "assistant":
        for call in message.tool_calls:
            part = types.Part.from_function_call(name=call.name, args=call.arguments)
            signature = _decode_signature(call.provider_data.get("gemini", {}).get("thought_signature"))
            if signature is not None:
                part.thought_signature = signature
            parts.append(part)
        return types.Content(role="model", parts=parts or [types.Part.from_text(text="")])
    return types.Content(role="user", parts=parts or [types.Part.from_text(text="")])


def _safe_chunk_text(chunk) -> str:
    saw_parts = False
    text_parts: list[str] = []
    for candidate in getattr(chunk, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            saw_parts = True
            text = getattr(part, "text", None)
            if text:
                text_parts.append(text)
    if saw_parts:
        return "".join(text_parts)
    try:
        return chunk.text or ""
    except Exception:
        return ""


def _extract_usage(chunk) -> ProviderUsage | None:
    raw = getattr(chunk, "usage_metadata", None)
    if raw is None:
        return None
    input_tokens = getattr(raw, "prompt_token_count", None)
    output_tokens = getattr(raw, "candidates_token_count", None)
    total_tokens = getattr(raw, "total_token_count", None)
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return ProviderUsage(input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens)


def _extract_gemini_calls(chunk) -> list[ToolCall]:
    calls = []
    for candidate in getattr(chunk, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            raw = getattr(part, "function_call", None)
            call = _tool_call_from_gemini(raw, part=part)
            if call:
                calls.append(call)
    if calls:
        return calls
    raw_calls = getattr(chunk, "function_calls", None) or []
    for raw in raw_calls:
        call = _tool_call_from_gemini(raw)
        if call:
            calls.append(call)
    return calls


def _tool_call_from_gemini(raw, part=None) -> ToolCall | None:
    if raw is None:
        return None
    name = getattr(raw, "name", None)
    args = getattr(raw, "args", None)
    if not name:
        nested = getattr(raw, "function_call", None)
        if nested is not None:
            name = getattr(nested, "name", None)
            args = getattr(nested, "args", None)
    if not name:
        return None
    provider_data: dict[str, Any] = {}
    signature = getattr(part, "thought_signature", None) if part is not None else None
    if signature is not None:
        provider_data["gemini"] = {"thought_signature": _encode_signature(signature)}
    return ToolCall(
        id=getattr(raw, "id", None) or f"gemini-{uuid4().hex[:10]}",
        name=name,
        arguments=dict(args or {}),
        provider_data=provider_data,
    )


def _sanitize_schema(schema: dict) -> dict:
    if isinstance(schema, dict):
        return {
            key: _sanitize_schema(value)
            for key, value in schema.items()
            if key not in {"$schema", "title"}
        }
    if isinstance(schema, list):
        return [_sanitize_schema(value) for value in schema]
    return schema


def _encode_signature(signature) -> dict[str, str] | str:
    if isinstance(signature, bytes):
        return {"encoding": "base64", "value": base64.b64encode(signature).decode("ascii")}
    return signature


def _decode_signature(encoded):
    if not encoded:
        return None
    if isinstance(encoded, dict) and encoded.get("encoding") == "base64":
        return base64.b64decode(encoded["value"])
    return encoded
