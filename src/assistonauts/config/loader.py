"""YAML config loading and validation."""

from pathlib import Path

import yaml

from assistonauts.models.config import (
    AssistonautsConfig,
    CacheConfig,
    EmbeddingConfig,
    EmbeddingProviderConfig,
    ExpeditionConfig,
    ExpeditionScope,
    ExpeditionSources,
    LLMConfig,
    LLMProviderConfig,
    LLMResponseCacheConfig,
    LocalSource,
)


def load_config(workspace_root: Path) -> AssistonautsConfig:
    """Load global config from .assistonauts/config.yaml.

    Returns default config if the file doesn't exist.
    Ignores unknown keys. Missing sections are filled with defaults.
    """
    config_path = workspace_root / ".assistonauts" / "config.yaml"

    if not config_path.exists():
        return AssistonautsConfig()

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        return AssistonautsConfig()

    return _parse_global_config(raw)


def load_expedition_config(path: Path) -> ExpeditionConfig:
    """Load expedition config from an expedition.yaml file.

    Raises FileNotFoundError if the file doesn't exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Expedition config not found: {path}")

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        return ExpeditionConfig()

    exp_data = raw.get("expedition", {})
    return _parse_expedition_config(exp_data)


def _parse_global_config(raw: dict[str, object]) -> AssistonautsConfig:
    """Parse raw YAML dict into AssistonautsConfig."""
    llm = _parse_llm_config(raw.get("llm", {}))
    embedding = _parse_embedding_config(raw.get("embedding", {}))
    cache = _parse_cache_config(raw.get("cache", {}))

    return AssistonautsConfig(llm=llm, embedding=embedding, cache=cache)


def _parse_llm_config(raw: object) -> LLMConfig:
    """Parse LLM config section."""
    if not isinstance(raw, dict):
        return LLMConfig()

    providers: dict[str, LLMProviderConfig] = {}
    for name, pdata in raw.get("providers", {}).items():
        if isinstance(pdata, dict):
            providers[name] = LLMProviderConfig(
                model=pdata.get("model", ""),
                api_key_env=pdata.get("api_key_env"),
                base_url=pdata.get("base_url"),
            )

    roles: dict[str, str] = {}
    for role, provider in raw.get("roles", {}).items():
        if isinstance(provider, str):
            roles[role] = provider

    return LLMConfig(providers=providers, roles=roles)


def _parse_embedding_config(raw: object) -> EmbeddingConfig:
    """Parse embedding config section."""
    if not isinstance(raw, dict):
        return EmbeddingConfig()

    providers: dict[str, EmbeddingProviderConfig] = {}
    for name, pdata in raw.get("providers", {}).items():
        if isinstance(pdata, dict):
            dims_raw = pdata.get("dimensions")
            dims = int(dims_raw) if dims_raw is not None else None
            providers[name] = EmbeddingProviderConfig(
                model=pdata.get("model", ""),
                base_url=pdata.get("base_url"),
                dimensions=dims,
            )

    return EmbeddingConfig(
        active=raw.get("active", ""),
        providers=providers,
    )


def _parse_cache_config(raw: object) -> CacheConfig:
    """Parse cache config section."""
    if not isinstance(raw, dict):
        return CacheConfig()

    llm_raw = raw.get("llm_responses", {})
    if not isinstance(llm_raw, dict):
        return CacheConfig()

    return CacheConfig(
        llm_responses=LLMResponseCacheConfig(
            enabled=llm_raw.get("enabled", True),
            backend=llm_raw.get("backend", "sqlite"),
            ttl_hours=llm_raw.get("ttl_hours", 168),
            max_size_mb=llm_raw.get("max_size_mb", 500),
        )
    )


def _parse_expedition_config(raw: dict[str, object]) -> ExpeditionConfig:
    """Parse expedition config from raw dict."""
    scope_raw = raw.get("scope", {})
    scope = ExpeditionScope()
    if isinstance(scope_raw, dict):
        scope = ExpeditionScope(
            description=scope_raw.get("description", ""),
            keywords=scope_raw.get("keywords", []),
        )

    sources_raw = raw.get("sources", {})
    sources = ExpeditionSources()
    if isinstance(sources_raw, dict):
        local_list = sources_raw.get("local", [])
        if isinstance(local_list, list):
            sources = ExpeditionSources(
                local=[
                    LocalSource(
                        path=s.get("path", ""),
                        pattern=s.get("pattern", "*"),
                    )
                    for s in local_list
                    if isinstance(s, dict)
                ]
            )

    return ExpeditionConfig(
        name=raw.get("name", ""),
        description=raw.get("description", ""),
        phase=raw.get("phase", "build"),
        scope=scope,
        sources=sources,
    )
