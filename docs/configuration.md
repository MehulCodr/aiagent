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
  "session_char_budget": 120000
}
```

Environment overrides:

- `CODE_AGENT_PROVIDER`
- `CODE_AGENT_MODEL`
- `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- `OPENAI_API_KEY`
- `OLLAMA_BASE_URL`

`.env` in the project root is loaded automatically.
