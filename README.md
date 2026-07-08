# code-agent

A minimal Python 3.12 CLI coding agent inspired by Pi's provider/model registry, tool-call-first runtime, session state, and terminal workflow.

## Features

- CLI command: `code-agent`
- Provider abstraction for Gemini, OpenAI, and Ollama
- Tool-calling agent loop with streaming text
- Project-root file tools: `list_files`, `read_file`, `write_file`, `edit_file`
- Shell tool with blocked destructive commands, risky-command approval, and project-root execution
- JSON session storage in `.code-agent/sessions`
- Project config in `.code-agent/config.json`
- Rich terminal panels for sessions, tool calls, and results
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
code-agent chat --provider gemini
```

Run one prompt and exit:

```powershell
code-agent run "Inspect this repo and summarize how to run it" --provider gemini
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

Local tool tests:

```powershell
pytest tests/test_tools.py
```

Live Gemini tests:

```powershell
$env:GEMINI_API_KEY = "your-key"
pytest -m live
```

The live tests do not mock provider responses. They call Gemini to list models, choose the nearest Flash model, generate a short response, and verify a real tool-call request.

## Safety Model

File tools are restricted to the project root. The shell tool runs from the project root, blocks destructive commands such as `git reset --hard` and recursive force deletes, and asks before risky commands such as package installs or file removal. `--yes` auto-approves risky shell commands but does not bypass blocked commands.

## Docs

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Providers](docs/providers.md)
- [Tools](docs/tools.md)
- [Testing](docs/testing.md)
