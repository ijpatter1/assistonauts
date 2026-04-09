"""Data models for configuration files."""

from dataclasses import dataclass, field


@dataclass
class LLMProviderConfig:
    """Configuration for a single LLM provider."""

    model: str = ""
    api_key_env: str | None = None
    base_url: str | None = None


@dataclass
class LLMConfig:
    """LLM configuration — providers and role-to-provider mapping."""

    providers: dict[str, LLMProviderConfig] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)


@dataclass
class EmbeddingProviderConfig:
    """Configuration for a single embedding provider."""

    model: str = ""
    base_url: str | None = None
    dimensions: int | None = None


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""

    active: str = ""
    providers: dict[str, EmbeddingProviderConfig] = field(default_factory=dict)


@dataclass
class LLMResponseCacheConfig:
    """LLM response cache configuration."""

    enabled: bool = True
    backend: str = "sqlite"
    ttl_hours: int = 168
    max_size_mb: int = 500


@dataclass
class CacheConfig:
    """Cache layer configuration."""

    llm_responses: LLMResponseCacheConfig = field(
        default_factory=LLMResponseCacheConfig
    )


@dataclass
class AssistonautsConfig:
    """Top-level Assistonauts configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)


# --- Expedition config models ---


@dataclass
class ExpeditionScope:
    """Scope definition for an expedition."""

    description: str = ""
    keywords: list[str] = field(default_factory=list)


@dataclass
class LocalSource:
    """A local file source for an expedition."""

    path: str = ""
    pattern: str = "*"


@dataclass
class ExpeditionSources:
    """Source definitions for an expedition."""

    local: list[LocalSource] = field(default_factory=list)


@dataclass
class ExpeditionConfig:
    """Configuration for a single expedition."""

    name: str = ""
    description: str = ""
    phase: str = "build"
    scope: ExpeditionScope = field(default_factory=ExpeditionScope)
    sources: ExpeditionSources = field(default_factory=ExpeditionSources)
