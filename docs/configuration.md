# Configuration

Create config:

```powershell
code-agent config-init
```

Config lives at `.code-agent/config.json`:

```json
{
  "provider": "gemini",
  "model": null,
  "preferred_models": {
    "gemini": "gemini-3.1-flash-lite",
    "openai": "gpt-4.1-mini",
    "ollama": "qwen3"
  },
  "temperature": null,
  "max_output_tokens": null,
  "max_steps": 12,
  "stream": true,
  "require_shell_confirmation": true,
  "permission_profile": "strict",
  "session_char_budget": 120000,
  "rag_enabled": true,
  "rag_max_chunks": 6,
  "verbose": false
}
```

Runtime state lives under `.agent/`:

- `.agent/sessions/` for saved sessions
- `.agent/plans/` for the last reviewed plan
- `.agent/rag_index.json` for the repository index cache
- `.agent/logs/debug.jsonl` when `--verbose` is enabled

Permission profiles:

- `strict`: approve every shell command.
- `relaxed`: approve risky shell and git commands, allow safe shell commands.
- `read-only`: block shell and write tools.

Environment overrides:

- `CODE_AGENT_PROVIDER`
- `CODE_AGENT_MODEL`
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- `OPENAI_API_KEY`
- `OLLAMA_BASE_URL`

`.env` in the project root is loaded automatically.
