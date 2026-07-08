# Providers

## Gemini

Gemini uses the official `google-genai` SDK. It converts messages into Gemini `Content` objects and sends tool declarations as function declarations. Tool results are returned as `function_response` parts.

```powershell
$env:GEMINI_API_KEY = "your-key"
code-agent chat --provider gemini
```

## OpenAI

OpenAI uses the official Python SDK with chat-completions streaming and function tools.

```powershell
$env:OPENAI_API_KEY = "your-key"
code-agent chat --provider openai --model gpt-4.1-mini
```

## Ollama

Ollama uses the documented `/api/chat` HTTP API through `httpx`. Tool results use Ollama's `tool_name` message field.

```powershell
ollama pull qwen3
code-agent chat --provider ollama --model qwen3
```

## Model Selection

`code-agent smoke` asks Gemini for the available model list and chooses the nearest Flash model to `gemini-3.1-flash-lite`.
