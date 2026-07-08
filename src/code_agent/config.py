from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    provider: str = "gemini"
    model: str | None = None
    preferred_models: dict[str, str] = Field(
        default_factory=lambda: {
            "gemini": "gemini-3.1-flash-lite",
            "openai": "gpt-4.1-mini",
            "ollama": "qwen3",
        }
    )
    temperature: float | None = None
    max_output_tokens: int | None = None
    max_steps: int = 12
    stream: bool = True
    require_shell_confirmation: bool = True
    session_char_budget: int = 120_000


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return current


def config_dir(root: Path) -> Path:
    return root / ".code-agent"


def config_path(root: Path) -> Path:
    return config_dir(root) / "config.json"


def load_config(root: Path) -> AgentConfig:
    load_dotenv(root / ".env", override=False)
    data: dict[str, Any] = {}
    path = config_path(root)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    config = AgentConfig.model_validate(data)
    if provider := os.getenv("CODE_AGENT_PROVIDER"):
        config.provider = provider
    if model := os.getenv("CODE_AGENT_MODEL"):
        config.model = model
    return config


def write_default_config(root: Path) -> Path:
    path = config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(
            AgentConfig().model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
    return path
