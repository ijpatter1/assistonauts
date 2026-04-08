"""Resolve LLM provider settings from workspace config."""

from __future__ import annotations

from assistonauts.models.config import AssistonautsConfig

_DEFAULT_MODEL = "gpt-3.5-turbo"


def resolve_llm_for_role(
    config: AssistonautsConfig,
    role: str,
) -> tuple[str, str | None]:
    """Resolve model name and base_url for an agent role.

    Resolution order:
    1. Look up role in config.llm.roles → provider name
    2. Look up provider in config.llm.providers → model + base_url
    3. If no role mapping but providers exist, use the first provider
    4. Fall back to defaults (gpt-3.5-turbo, no base_url)

    Returns (model, base_url) tuple.
    """
    llm = config.llm

    # Try role→provider mapping
    provider_name = llm.roles.get(role)

    if provider_name and provider_name in llm.providers:
        provider = llm.providers[provider_name]
        return provider.model or _DEFAULT_MODEL, provider.base_url

    # No role mapping — if there's exactly one or any providers, use first
    if not provider_name and llm.providers:
        first_provider = next(iter(llm.providers.values()))
        return first_provider.model or _DEFAULT_MODEL, first_provider.base_url

    return _DEFAULT_MODEL, None
