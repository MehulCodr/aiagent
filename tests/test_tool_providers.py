from __future__ import annotations

from code_agent.tool_providers import ToolProvider
from code_agent.tools import build_default_tool_registry


def test_default_registry_satisfies_tool_provider_interface() -> None:
    registry = build_default_tool_registry()

    assert isinstance(registry, ToolProvider)
    assert "shell" in registry.names()
