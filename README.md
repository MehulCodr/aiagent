# code-agent

A Python 3.12 CLI coding agent with provider abstraction, repository-aware context, plan/apply workflow, approval-gated tools, persistent sessions, and Rich terminal output.

## Features

- CLI command: `code-agent`
- Provider abstraction for Gemini, OpenAI, and Ollama
- Repository RAG over local files with path and line-range citations
- Plan/apply modes with persisted reviewable plans
- Tool-calling agent loop with streaming text
- Project-root file tools: `list_files`, `read_file`, `write_file`, `edit_file`
- Approval layer for shell and git operations with `--yes` for non-interactive runs
- Parallel execution for safe read-only tool calls with deterministic result ordering
- JSON session storage in `.agent/sessions`
- `/save`, `/load`, and `/sessions` memory commands
- Rollback snapshots for the last agent turn
- Tool timing, response latency, provider usage fields, and verbose debug logs
- Bounded `code-agent test` command for test/lint/fix loops
- Project config in `.code-agent/config.json`
- Rich terminal panels for sessions, tool calls, diffs, timelines, and fixed-bottom prompts
- Live Gemini smoke tests using the real API

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Set provider credentials with environment variables:

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:OPENAI_API_KEY = "your-key"
$env:OLLAMA_BASE_URL = "http://localhost:11434"
```

## Run

Create default config:

```powershell
code-agent config-init
```

Run a real Gemini smoke test. The requested model is `gemini-3.1-flash-lite`; if it is not available, the CLI asks Gemini for available models and selects the nearest Flash model.

```powershell
code-agent smoke
```

Start the coding agent:

```powershell
code-agent chat --provider gemini --verbose
```

Run one prompt and exit:

```powershell
code-agent run "Inspect this repo and summarize how to run it" --provider gemini --yes
```

Create a plan without applying changes, review it, then execute it:

```powershell
code-agent plan "Add validation tests for the filesystem tools" --provider gemini
code-agent apply --yes
```

Interactive memory commands:

```text
/save parser-refactor
/sessions
/load parser-refactor
/plan Add retry handling around provider calls
/apply
/rollback
```

Disable terminal colors when piping output or running in plain logs:

```powershell
code-agent run "List the repo architecture" --no-color
```

Run a bounded test command:

```powershell
code-agent test "pytest" --max-attempts 1
```

Use Ollama:

```powershell
ollama pull qwen3
code-agent chat --provider ollama --model qwen3
```

Use OpenAI:

```powershell
code-agent chat --provider openai --model gpt-4.1-mini
```

## Tests

Local tests:

```powershell
pytest
```

Live Gemini tests:

```powershell
$env:GEMINI_API_KEY = "your-key"
pytest -m live
```

The live tests do not mock provider responses. They call Gemini to list models, choose the nearest Flash model, generate a short response, and verify a real tool-call request.

## Safety Model

File tools are restricted to the project root. Repository RAG ignores `.git`, `vendor`, `node_modules`, `dist`, `build`, `.agent`, and generated cache folders.

The default permission profile is `strict`: all shell commands require approval, and git operations are approval-gated. `--yes` auto-approves commands that need approval but does not bypass blocked destructive commands such as `git reset --hard`, `git clean -fd`, recursive force deletes, `format`, `mkfs`, shutdown, or reboot.

Profiles:

- `strict`: approve every shell command.
- `relaxed`: allow safe shell commands, approve risky shell and git commands.
- `read-only`: block shell and file-writing tools.

## Docs

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Providers](docs/providers.md)
- [Tools](docs/tools.md)
- [Testing](docs/testing.md)
