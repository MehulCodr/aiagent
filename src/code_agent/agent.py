from __future__ import annotations

from pathlib import Path

from code_agent.config import AgentConfig
from code_agent.context import build_system_prompt
from code_agent.messages import ChatMessage, ToolCall
from code_agent.providers.base import LLMProvider, ProviderError
from code_agent.session import Session, SessionStore
from code_agent.tools import ToolRegistry
from code_agent.tools.base import ToolContext
from code_agent.ui import TerminalUI


class AgentRuntime:
    def __init__(
        self,
        *,
        root: Path,
        config: AgentConfig,
        provider: LLMProvider,
        model: str,
        session: Session,
        session_store: SessionStore,
        tools: ToolRegistry,
        ui: TerminalUI,
        auto_approve: bool = False,
    ) -> None:
        self.root = root.resolve()
        self.config = config
        self.provider = provider
        self.model = model
        self.session = session
        self.session_store = session_store
        self.tools = tools
        self.ui = ui
        self.auto_approve = auto_approve

    def run_user_turn(self, prompt: str) -> str:
        self.session.messages.append(ChatMessage(role="user", content=prompt))
        self.session_store.save(self.session)
        final_text = ""

        for step in range(1, self.config.max_steps + 1):
            system_prompt = build_system_prompt(self.root, self.tools.definitions(), self.config)
            input_messages = _budget_messages(self.session.messages, self.config.session_char_budget)
            assistant_text = ""
            tool_calls: list[ToolCall] = []
            try:
                for event in self.provider.stream_chat(
                    model=self.model,
                    system_prompt=system_prompt,
                    messages=input_messages,
                    tools=self.tools.definitions(),
                    temperature=self.config.temperature,
                    max_output_tokens=self.config.max_output_tokens,
                ):
                    if event.type == "text" and event.text:
                        assistant_text += event.text
                        self.ui.stream_text(event.text)
                    elif event.type == "tool_calls":
                        tool_calls.extend(event.tool_calls)
            except ProviderError as exc:
                self.ui.error(str(exc))
                raise

            if assistant_text:
                self.ui.end_stream()
                final_text = assistant_text

            assistant_message = ChatMessage(role="assistant", content=assistant_text, tool_calls=tool_calls)
            self.session.messages.append(assistant_message)
            self.session_store.save(self.session)

            if not tool_calls:
                return final_text

            self._run_tool_calls(tool_calls)
            self.ui.info(f"Continuing after tool step {step}...")

        message = f"Stopped after max_steps={self.config.max_steps}. Increase max_steps if the task needs more tool rounds."
        self.ui.warning(message)
        return final_text

    def _run_tool_calls(self, tool_calls: list[ToolCall]) -> None:
        context = ToolContext(
            root=self.root,
            approval_callback=self.ui.confirm_shell if self.config.require_shell_confirmation else None,
            auto_approve=self.auto_approve or not self.config.require_shell_confirmation,
        )
        for call in tool_calls:
            self.ui.tool_call(call)
            result = self.tools.run(call.name, call.arguments, context)
            self.ui.tool_result(call.name, result)
            self.session.messages.append(
                ChatMessage(
                    role="tool",
                    content=result.content,
                    tool_call_id=call.id,
                    name=call.name,
                )
            )
            self.session_store.save(self.session)


def _budget_messages(messages: list[ChatMessage], budget: int) -> list[ChatMessage]:
    if budget <= 0:
        return messages
    total = sum(_message_size(message) for message in messages)
    if total <= budget:
        return messages
    kept: list[ChatMessage] = []
    running = 0
    for message in reversed(messages):
        size = _message_size(message)
        if kept and running + size > budget:
            break
        kept.append(message)
        running += size
    kept.reverse()
    if kept and kept[0].role != "user":
        kept.insert(0, ChatMessage(role="user", content="[Earlier conversation was truncated to fit context.]"))
    return kept


def _message_size(message: ChatMessage) -> int:
    return len(message.model_dump_json())
