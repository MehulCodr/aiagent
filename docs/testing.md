# Testing

Install dev dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run local tests:

```powershell
pytest
```

Use the built-in bounded runner:

```powershell
code-agent test "pytest" --max-attempts 1
```

The runner summarizes failures and stops after the configured attempt count. It does not retry infinitely.

Run live Gemini tests:

```powershell
$env:GEMINI_API_KEY = "your-key"
pytest -m live
```

The live tests call the real Gemini API. They fail clearly if no API key is configured.
