# Testing

Install dev dependencies:

```powershell
python -m pip install -e ".[dev]"
```

Run local tests:

```powershell
pytest tests/test_tools.py
```

Run live Gemini tests:

```powershell
$env:GEMINI_API_KEY = "your-key"
pytest -m live
```

The live tests call the real Gemini API. They fail clearly if no API key is configured.
