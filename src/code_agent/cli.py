from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from code_agent.agent import AgentRuntime
from code_agent.config import find_project_root, load_config, write_default_config
from code_agent.messages import ChatMessage
from code_agent.providers import build_provider_registry, choose_nearest_model
from code_agent.providers.base import ProviderError
from code_agent.session import SessionStore
from code_agent.test_runner import TestRunner
from code_agent.tools import build_default_tool_registry
from code_agent.ui import TerminalUI


app = typer.Typer(help="Python CLI coding agent.", no_args_is_help=True)
console = Console()


@app.command()
def chat(
    prompt: Annotated[str | None, typer.Argument(help="Optional first prompt.")] = None,
    provider: Annotated[str | None, typer.Option("--provider", "-p")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
    resume: Annotated[bool, typer.Option("--resume", "-c", help="Resume the latest local session.")] = False,
    session: Annotated[str | None, typer.Option("--session", "-s", help="Session id or path to resume.")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Auto-approve risky shell commands.")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colored terminal output.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Write debug logs and show extra runtime detail.")] = False,
) -> None:
    """Start an interactive coding-agent session."""
    runtime = _build_runtime(
        root=root,
        provider_override=provider,
        model_override=model,
        resume=resume,
        session_ref=session,
        yes=yes,
        no_color=no_color,
        verbose=verbose,
    )
    runtime.ui.header(provider=runtime.provider.id, model=runtime.model, root=runtime.root, session_id=runtime.session.id)
    if prompt:
        runtime.run_user_turn(prompt)
    while True:
        try:
            text = runtime.ui.user_prompt()
        except (EOFError, KeyboardInterrupt):
            runtime.ui.info("bye")
            return
        if not text:
            continue
        if text.startswith("/"):
            if _handle_command(text, runtime):
                return
            continue
        try:
            runtime.run_user_turn(text)
        except ProviderError:
            continue


@app.command()
def run(
    prompt: Annotated[str, typer.Argument(help="Prompt to run once.")],
    provider: Annotated[str | None, typer.Option("--provider", "-p")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Auto-approve risky shell commands.")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colored terminal output.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Write debug logs and show extra runtime detail.")] = False,
) -> None:
    """Run one prompt and exit after the agent finishes."""
    runtime = _build_runtime(
        root=root,
        provider_override=provider,
        model_override=model,
        resume=False,
        session_ref=None,
        yes=yes,
        no_color=no_color,
        verbose=verbose,
    )
    runtime.ui.header(provider=runtime.provider.id, model=runtime.model, root=runtime.root, session_id=runtime.session.id)
    runtime.run_user_turn(prompt)


@app.command()
def plan(
    prompt: Annotated[str, typer.Argument(help="Request to plan without applying changes.")],
    provider: Annotated[str | None, typer.Option("--provider", "-p")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colored terminal output.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Write debug logs and show extra runtime detail.")] = False,
) -> None:
    """Create and persist a reviewed plan without executing tools."""
    runtime = _build_runtime(
        root=root,
        provider_override=provider,
        model_override=model,
        resume=True,
        session_ref=None,
        yes=False,
        no_color=no_color,
        verbose=verbose,
    )
    created = runtime.create_plan(prompt)
    runtime.ui.print_plan(created.body)
    runtime.ui.info(f"saved plan {created.id}")


@app.command()
def apply(
    extra_instruction: Annotated[str | None, typer.Argument(help="Optional extra instruction for the saved plan.")] = None,
    provider: Annotated[str | None, typer.Option("--provider", "-p")] = None,
    model: Annotated[str | None, typer.Option("--model", "-m")] = None,
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Auto-approve tool operations that need approval.")] = False,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colored terminal output.")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Write debug logs and show extra runtime detail.")] = False,
) -> None:
    """Execute the last persisted plan."""
    runtime = _build_runtime(
        root=root,
        provider_override=provider,
        model_override=model,
        resume=True,
        session_ref=None,
        yes=yes,
        no_color=no_color,
        verbose=verbose,
    )
    runtime.ui.header(provider=runtime.provider.id, model=runtime.model, root=runtime.root, session_id=runtime.session.id)
    runtime.apply_plan(extra_instruction=extra_instruction)


@app.command("test")
def test_command(
    command: Annotated[str, typer.Argument(help="Test or lint command to run.")] = "pytest",
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
    max_attempts: Annotated[int, typer.Option("--max-attempts", min=1, max=5)] = 1,
    timeout_seconds: Annotated[int, typer.Option("--timeout-seconds", min=1)] = 120,
    no_color: Annotated[bool, typer.Option("--no-color", help="Disable colored terminal output.")] = False,
) -> None:
    """Run a bounded test/lint command and summarize failures."""
    project_root = find_project_root(root)
    local_console = Console(no_color=no_color)
    result = TestRunner(project_root).run(command, max_attempts=max_attempts, timeout_seconds=timeout_seconds)
    style = "green" if result.passed else "red"
    local_console.print(f"[{style}]exit_code={result.exit_code} attempts={result.attempts} time={result.duration_ms:.1f} ms[/{style}]")
    if result.summary:
        local_console.print(result.summary)
    if not result.passed:
        raise typer.Exit(result.exit_code)


@app.command("models")
def list_models(
    provider: Annotated[str, typer.Option("--provider", "-p")] = "gemini",
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
) -> None:
    """List models reported by a provider."""
    project_root = find_project_root(root)
    load_config(project_root)
    registry = build_provider_registry()
    selected = registry.get(provider)
    table = Table(title=f"{selected.display_name} models")
    table.add_column("model")
    table.add_column("tools")
    for item in selected.list_models():
        table.add_row(item.name, "yes" if item.supports_tools else "unknown")
    console.print(table)


@app.command("config-init")
def config_init(root: Annotated[Path | None, typer.Option("--root", "-r")] = None) -> None:
    """Create .code-agent/config.json if it does not exist."""
    project_root = find_project_root(root)
    path = write_default_config(project_root)
    console.print(f"[green]config ready:[/green] {path}")


@app.command("config-show")
def config_show(root: Annotated[Path | None, typer.Option("--root", "-r")] = None) -> None:
    """Print the merged project config."""
    project_root = find_project_root(root)
    config = load_config(project_root)
    console.print_json(config.model_dump_json())


@app.command()
def smoke(
    preferred_model: Annotated[str, typer.Option("--preferred-model")] = "gemini-3.1-flash-lite",
    root: Annotated[Path | None, typer.Option("--root", "-r")] = None,
) -> None:
    """Run a real Gemini provider smoke test with the nearest available Flash model."""
    project_root = find_project_root(root)
    load_config(project_root)
    registry = build_provider_registry()
    provider = registry.get("gemini")
    model = choose_nearest_model(provider, preferred_model)
    console.print(f"[cyan]using Gemini model:[/cyan] {model}")
    text = ""
    for event in provider.stream_chat(
        model=model,
        system_prompt="You are a smoke-test assistant. Follow the user instruction exactly.",
        messages=[ChatMessage(role="user", content="Reply with exactly: code-agent-ok")],
        tools=[],
        temperature=0,
        max_output_tokens=32,
    ):
        if event.type == "text":
            text += event.text
    console.print(text.strip())
    if "code-agent-ok" not in text:
        raise typer.Exit(1)


def _build_runtime(
    *,
    root: Path | None,
    provider_override: str | None,
    model_override: str | None,
    resume: bool,
    session_ref: str | None,
    yes: bool,
    no_color: bool,
    verbose: bool,
) -> AgentRuntime:
    project_root = find_project_root(root)
    config = load_config(project_root)
    config.verbose = config.verbose or verbose
    provider_id = provider_override or config.provider
    registry = build_provider_registry()
    provider = registry.get(provider_id)
    model = model_override or config.model or config.preferred_models.get(provider_id) or provider.default_model
    if provider_id == "gemini" and os.getenv("GEMINI_API_KEY"):
        model = choose_nearest_model(provider, model)
    store = SessionStore(project_root)
    if session_ref:
        session = store.load(session_ref)
    elif resume:
        session = store.latest() or store.create(provider=provider_id, model=model)
    else:
        session = store.create(provider=provider_id, model=model)
    session.provider = provider_id
    session.model = model
    store.save(session)
    return AgentRuntime(
        root=project_root,
        config=config,
        provider=provider,
        model=model,
        session=session,
        session_store=store,
        tools=build_default_tool_registry(),
        ui=TerminalUI(Console(no_color=no_color), no_color=no_color, verbose=config.verbose),
        auto_approve=yes,
    )


def _handle_command(text: str, runtime: AgentRuntime) -> bool:
    command, *_rest = text.split(maxsplit=1)
    if command in {"/quit", "/exit"}:
        runtime.ui.info("bye")
        return True
    if command == "/help":
        runtime.ui.help()
        return False
    if command == "/sessions":
        table = Table(title="sessions")
        table.add_column("id")
        table.add_column("name")
        table.add_column("updated")
        table.add_column("messages", justify="right")
        for item in runtime.session_store.list_sessions():
            table.add_row(item.id[:12], item.name or "", item.updated_at, str(len(item.messages)))
        runtime.ui.console.print(table)
        return False
    if command == "/save":
        name = _rest[0].strip() if _rest else ""
        if not name:
            runtime.ui.warning("Usage: /save <name>")
            return False
        runtime.session_store.save_named(runtime.session, name)
        runtime.ui.info(f"saved session as {name}")
        return False
    if command == "/load":
        ref = _rest[0].strip() if _rest else ""
        if not ref:
            runtime.ui.warning("Usage: /load <name-or-id>")
            return False
        runtime.session = runtime.session_store.load(ref)
        runtime.ui.header(provider=runtime.provider.id, model=runtime.model, root=runtime.root, session_id=runtime.session.id)
        return False
    if command == "/session":
        runtime.ui.info(
            f"id={runtime.session.id} provider={runtime.provider.id} model={runtime.model} messages={len(runtime.session.messages)}"
        )
        return False
    if command == "/plan":
        if _rest:
            created = runtime.create_plan(_rest[0].strip())
            runtime.ui.print_plan(created.body)
            runtime.ui.info(f"saved plan {created.id}")
        else:
            runtime.ui.print_plan(runtime.load_last_plan().body)
        return False
    if command == "/apply":
        runtime.apply_plan(extra_instruction=_rest[0].strip() if _rest else None)
        return False
    if command == "/rollback":
        try:
            runtime.rollback_last_turn()
        except Exception as exc:
            runtime.ui.error(str(exc))
        else:
            runtime.ui.info("workspace restored from last rollback snapshot")
        return False
    if command == "/clear":
        runtime.session.messages.clear()
        runtime.session_store.save(runtime.session)
        runtime.ui.info("session messages cleared")
        return False
    runtime.ui.warning(f"Unknown command: {command}")
    return False
