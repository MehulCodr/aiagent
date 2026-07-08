from __future__ import annotations

from difflib import SequenceMatcher

from code_agent.providers.base import LLMProvider, ModelInfo, ProviderError
from code_agent.providers.gemini import GeminiProvider
from code_agent.providers.ollama import OllamaProvider
from code_agent.providers.openai_provider import OpenAIProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> LLMProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            known = ", ".join(sorted(self._providers))
            raise ProviderError(f"Unknown provider '{provider_id}'. Known providers: {known}") from exc

    def ids(self) -> list[str]:
        return sorted(self._providers)


def build_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(GeminiProvider())
    registry.register(OpenAIProvider())
    registry.register(OllamaProvider())
    return registry


def choose_nearest_model(provider: LLMProvider, preferred: str | None = None) -> str:
    models = provider.list_models()
    names = [model.name for model in models]
    if not names:
        raise ProviderError(f"{provider.display_name} returned no models.")
    target = preferred or provider.default_model
    if target in names:
        return target
    short_name_matches = [name for name in names if name.split("/")[-1] == target]
    if short_name_matches:
        return short_name_matches[0]
    ranked = sorted(models, key=lambda model: _model_score(model, target), reverse=True)
    return ranked[0].name


def _model_score(model: ModelInfo, target: str) -> float:
    name = model.name.lower()
    display = (model.display_name or "").lower()
    haystack = f"{name} {display}"
    target_lower = target.lower()
    score = SequenceMatcher(None, target_lower, name).ratio()
    for token in target_lower.replace("-", " ").split():
        if token in haystack:
            score += 0.15
    if "flash" in target_lower and "flash" in haystack:
        score += 0.4
    if "lite" in target_lower and "lite" in haystack:
        score += 0.2
    if model.supports_tools:
        score += 0.05
    return score
