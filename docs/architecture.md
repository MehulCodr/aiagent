# Architecture

`code-agent` keeps the runtime small:

- `AgentRuntime` owns the loop: user message, provider stream, assistant message, tool execution, tool results, repeat.
- `LLMProvider` translates internal messages and tool schemas into provider-specific requests.
- `ToolRegistry` validates JSON arguments and dispatches tools.
- `SessionStore` saves each step as JSON under `.code-agent/sessions`.
- `TerminalUI` renders streaming output and approval prompts with Rich.

Pi AI was used as architectural inspiration: unified provider abstraction, model registry, tool-calling-first control flow, stateful sessions, and configurable coding-agent runtime.

The internal message shape is intentionally simple: `user`, `assistant`, and `tool` messages with optional `ToolCall` objects. Each provider handles its own wire format at the boundary.
