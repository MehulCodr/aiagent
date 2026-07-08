from __future__ import annotations

import os

import pytest

from code_agent.messages import ChatMessage
from code_agent.providers import choose_nearest_model
from code_agent.providers.gemini import GeminiProvider
from code_agent.tools.base import ToolDefinition


pytestmark = pytest.mark.live


def _require_key() -> None:
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        pytest.fail("GEMINI_API_KEY or GOOGLE_API_KEY is required for live Gemini tests.")


def test_gemini_live_text_smoke() -> None:
    _require_key()
    provider = GeminiProvider()
    model = choose_nearest_model(provider, "gemini-3.1-flash-lite")
    text = ""
    for event in provider.stream_chat(
        model=model,
        system_prompt="You are a test assistant. Follow the user's instruction exactly.",
        messages=[ChatMessage(role="user", content="Reply with exactly: code-agent-ok")],
        tools=[],
        temperature=0,
        max_output_tokens=32,
    ):
        if event.type == "text":
            text += event.text
    assert "code-agent-ok" in text.lower()


def test_gemini_live_tool_call_smoke() -> None:
    _require_key()
    provider = GeminiProvider()
    model = choose_nearest_model(provider, "gemini-3.1-flash-lite")
    tool = ToolDefinition(
        name="echo_text",
        description="Echo text back to the caller.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    calls = []
    for event in provider.stream_chat(
        model=model,
        system_prompt="You must use the provided tools when the user asks you to call one.",
        messages=[ChatMessage(role="user", content="Call echo_text with text set to hello-live-test.")],
        tools=[tool],
        temperature=0,
        max_output_tokens=128,
    ):
        if event.type == "tool_calls":
            calls.extend(event.tool_calls)
    assert calls
    assert calls[0].name == "echo_text"
    assert calls[0].arguments.get("text") == "hello-live-test"


def test_gemini_live_tool_result_round_trip() -> None:
    _require_key()
    provider = GeminiProvider()
    model = choose_nearest_model(provider, "gemini-3.1-flash-lite")
    tool = ToolDefinition(
        name="echo_text",
        description="Echo text back to the caller.",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    )
    user = ChatMessage(
        role="user",
        content=(
            "Call echo_text with text set to hello-live-test. "
            "After the tool result is provided, reply with exactly: code-agent-tool-result-ok"
        ),
    )
    calls = []
    for event in provider.stream_chat(
        model=model,
        system_prompt="You must use the provided tools when the user asks you to call one.",
        messages=[user],
        tools=[tool],
        temperature=0,
        max_output_tokens=128,
    ):
        if event.type == "tool_calls":
            calls.extend(event.tool_calls)
    assert calls

    final_text = ""
    for event in provider.stream_chat(
        model=model,
        system_prompt="You must use the provided tools when the user asks you to call one.",
        messages=[
            user,
            ChatMessage(role="assistant", tool_calls=calls),
            ChatMessage(role="tool", name="echo_text", tool_call_id=calls[0].id, content="hello-live-test"),
        ],
        tools=[tool],
        temperature=0,
        max_output_tokens=128,
    ):
        if event.type == "text":
            final_text += event.text
    assert "code-agent-tool-result-ok" in final_text.lower()
