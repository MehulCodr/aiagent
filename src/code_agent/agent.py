from __future__ import annotations

from pathlib import Path

from code_agent.approval import ApprovalLayer, PermissionPolicy
from code_agent.config import AgentConfig
from code_agent.context import build_system_prompt
from code_agent.execution import ExecutionEngine
from code_agent.git_workflow import GitWorkflow
from code_agent.messages import ChatMessage, ToolCall
from code_agent.observability import Observer
from code_agent.planner import Plan, PlanStore, Planner, build_apply_prompt
from code_agent.providers.base import LLMProvider, ProviderError
from code_agent.rag import RepositoryRAG
from code_agent.session import Session, SessionStore
from code_agent.tools import ToolRegistry
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
        observer: Observer | None = None,
        repository_rag: RepositoryRAG | None = None,
        plan_store: PlanStore | None = None,
        git_workflow: GitWorkflow | None = None,
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
        self.observer = observer or Observer(self.root, verbose=config.verbose)
        self.repository_rag = repository_rag or RepositoryRAG(self.root)
        self.plan_store = plan_store or PlanStore(self.root)
        self.git_workflow = git_workflow or GitWorkflow(self.root)

    def run_user_turn(self, prompt: str) -> str:
        self._save_rollback_snapshot()
        self.session.messages.append(ChatMessage(role="user", content=prompt))
        self.session_store.save(self.session)
        final_text = ""
        retrieved_context = self._retrieve_context(prompt)

        for step in range(1, self.config.max_steps + 1):
            system_prompt = build_system_prompt(self.root, self.tools.definitions(), self.config, retrieved_context)
            input_messages = _budget_messages(self.session.messages, self.config.session_char_budget)
            assistant_text = ""
            tool_calls: list[ToolCall] = []
            usage = None
            timer = self.observer.timer()
            try:
                with self.ui.activity("Thinking...") as activity:
                    is_generating = False
                    for event in self.provider.stream_chat(
                        model=self.model,
                        system_prompt=system_prompt,
                        messages=input_messages,
                        tools=self.tools.definitions(),
                        temperature=self.config.temperature,
                        max_output_tokens=self.config.max_output_tokens,
                    ):
                        if event.type == "text" and event.text:
                            if not is_generating:
                                activity.update("[cyan]Generating...[/cyan]")
                                is_generating = True
                            assistant_text += event.text
                        elif event.type == "tool_calls":
                            if event.tool_calls:
                                activity.update("[cyan]Preparing tool calls...[/cyan]")
                            tool_calls.extend(event.tool_calls)
                        elif event.type == "done" and event.usage is not None:
                            usage = event.usage
            except ProviderError as exc:
                self.ui.error(str(exc))
                raise
            finally:
                self.observer.record_response(
                    provider=self.provider.id,
                    model=self.model,
                    latency_ms=timer.elapsed_ms(),
                    usage=usage,
                )

            if assistant_text:
                self.ui.assistant_text(assistant_text)
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

    def create_plan(self, prompt: str) -> Plan:
        repository_context = self._retrieve_context(prompt)
        planner = Planner(provider=self.provider, model=self.model, config=self.config, observer=self.observer)
        plan = planner.create_plan(prompt, repository_context=repository_context)
        self.plan_store.save(plan)
        return plan

    def load_last_plan(self) -> Plan:
        return self.plan_store.load_last()

    def apply_plan(self, plan: Plan | None = None, *, extra_instruction: str | None = None) -> str:
        selected = plan or self.plan_store.load_last()
        result = self.run_user_turn(build_apply_prompt(selected, extra_instruction))
        self.plan_store.mark_applied(selected)
        return result

    def rollback_last_turn(self) -> None:
        self.git_workflow.rollback()

    def _run_tool_calls(self, tool_calls: list[ToolCall]) -> None:
        approval = ApprovalLayer(
            policy=PermissionPolicy.from_name(self.config.permission_profile),
            callback=self.ui.confirm_tool if self.config.require_shell_confirmation else None,
            auto_approve=self.auto_approve or not self.config.require_shell_confirmation,
        )
        engine = ExecutionEngine(root=self.root, tools=self.tools, approval=approval, observer=self.observer)
        for call in tool_calls:
            self.ui.tool_call(call)
        count = len(tool_calls)
        label = "Calling 1 tool..." if count == 1 else f"Calling {count} tools..."
        with self.ui.activity(label):
            records = engine.run_many(tool_calls)
        for record in records:
            result = record.result
            self.ui.tool_result(record.name, result)
            self.session.messages.append(
                ChatMessage(
                    role="tool",
                    content=result.content,
                    tool_call_id=record.call_id,
                    name=record.name,
                )
            )
            self.session_store.save(self.session)
        self.ui.tool_timeline(records)

    def _retrieve_context(self, prompt: str) -> str:
        if not self.config.rag_enabled:
            return ""
        context = self.repository_rag.retrieve_context(prompt, limit=self.config.rag_max_chunks)
        if context:
            self.observer.record("rag_retrieval", chunks=context.count("```") // 2)
        return context

    def _save_rollback_snapshot(self) -> None:
        try:
            self.git_workflow.save_snapshot()
        except Exception as exc:
            self.observer.record("rollback_snapshot_failed", error=str(exc))


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
