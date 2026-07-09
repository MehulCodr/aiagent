# Architecture

`code-agent` keeps the runtime small and layered:

- CLI / TUI builds a configured runtime and renders streaming output, prompts, approvals, diffs, and timelines.
- `AgentRuntime` orchestrates user turns, RAG retrieval, provider streaming, tool execution, memory, plans, and rollback snapshots.
- `Planner` creates reviewable plans without tools and persists the latest plan under `.agent/plans`.
- `RepositoryRAG` indexes text files into path and line-range chunks, caches under `.agent/rag_index.json`, and retrieves prompt-relevant excerpts.
- `LLMProvider` translates internal messages and tool schemas into provider-specific requests.
- `ToolRegistry` validates JSON arguments and dispatches local tools. It also satisfies the MCP-ready `ToolProvider` protocol.
- `ApprovalLayer` applies permission profiles before tool execution.
- `ExecutionEngine` runs safe read-only tools concurrently, preserves deterministic output ordering, and records clean errors.
- `SessionStore` saves conversations as JSON under `.agent/sessions` while still loading legacy `.code-agent/sessions`.
- `Observer` records response latency, provider usage fields when available, tool timings, and verbose JSONL debug logs.
- `TerminalUI` renders streaming output and fixed-bottom input through Rich and prompt-toolkit.

Pi AI was used as architectural inspiration: unified provider abstraction, model registry, tool-calling-first control flow, stateful sessions, and configurable coding-agent runtime.

The internal message shape is intentionally simple: `user`, `assistant`, and `tool` messages with optional `ToolCall` objects. Each provider handles its own wire format at the boundary.

External MCP servers are not integrated yet. The current architecture exposes provider protocols so future MCP tools can be adapted without changing the orchestrator.
