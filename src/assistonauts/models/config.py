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
class ExpeditionResources:
    """Resource limits for an expedition."""

    daily_token_budget: int = 100_000
    max_concurrent_missions: int = 3


@dataclass
class StationedConfig:
    """Stationed phase configuration."""

    resources: ExpeditionResources = field(
        default_factory=ExpeditionResources,
    )
    schedule: dict[str, str] = field(default_factory=dict)
    triggers: dict[str, list[str] | dict[str, list[str] | str]] = field(
        default_factory=dict,
    )


@dataclass
class AutoScaleConfig:
    """Auto-scaling rules."""

    trigger: str = "queue_depth > 5"
    max_instances: int = 3
    cooldown_minutes: int = 10


@dataclass
class BudgetConfig:
    """Token budget configuration."""

    daily_token_limit: int = 100_000
    warning_threshold: float = 0.8


SINGLETONS = frozenset({"captain", "curator", "inspector"})


@dataclass
class ScalingConfig:
    """Agent scaling configuration."""

    agents: dict[str, str] = field(default_factory=dict)
    auto_scale: AutoScaleConfig = field(default_factory=AutoScaleConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)

    def is_scalable(self, agent: str) -> bool:
        """Check if an agent can be scaled (not a singleton)."""
        if agent in SINGLETONS:
            return False
        return agent in self.agents


@dataclass
class ExpeditionConfig:
    """Configuration for a single expedition."""

    name: str = ""
    description: str = ""
    phase: str = "build"
    scope: ExpeditionScope = field(default_factory=ExpeditionScope)
    sources: ExpeditionSources = field(default_factory=ExpeditionSources)
    stationed: StationedConfig = field(default_factory=StationedConfig)
    scaling: ScalingConfig = field(default_factory=ScalingConfig)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ExpeditionConfig":
        """Parse an expedition config from a dict (e.g. YAML)."""
        scope_data = data.get("scope", {})
        scope = ExpeditionScope(
            description=str(scope_data.get("description", ""))  # type: ignore[union-attr]
            if isinstance(scope_data, dict)
            else "",
            keywords=scope_data.get("keywords", [])  # type: ignore[union-attr]
            if isinstance(scope_data, dict)
            else [],
        )

        sources_data = data.get("sources", {})
        local_sources = []
        if isinstance(sources_data, dict):
            for ls in sources_data.get("local", []):
                if isinstance(ls, dict):
                    local_sources.append(
                        LocalSource(
                            path=str(ls.get("path", "")),
                            pattern=str(ls.get("pattern", "*")),
                        )
                    )
        sources = ExpeditionSources(local=local_sources)

        stationed_data = data.get("stationed", {})
        stationed = StationedConfig()
        if isinstance(stationed_data, dict):
            res_data = stationed_data.get("resources", {})
            if isinstance(res_data, dict):
                stationed.resources = ExpeditionResources(
                    daily_token_budget=int(
                        res_data.get("daily_token_budget", 100_000),
                    ),
                    max_concurrent_missions=int(
                        res_data.get("max_concurrent_missions", 3),
                    ),
                )
            sched = stationed_data.get("schedule", {})
            if isinstance(sched, dict):
                stationed.schedule = sched
            trigs = stationed_data.get("triggers", {})
            if isinstance(trigs, dict):
                stationed.triggers = trigs

        scaling_data = data.get("scaling", {})
        scaling = ScalingConfig()
        if isinstance(scaling_data, dict):
            agents = scaling_data.get("agents", {})
            if isinstance(agents, dict):
                scaling.agents = agents
            auto_data = scaling_data.get("auto_scale", {})
            if isinstance(auto_data, dict):
                scaling.auto_scale = AutoScaleConfig(
                    trigger=str(
                        auto_data.get("trigger", "queue_depth > 5"),
                    ),
                    max_instances=int(
                        auto_data.get("max_instances", 3),
                    ),
                    cooldown_minutes=int(
                        auto_data.get("cooldown_minutes", 10),
                    ),
                )
            budget_data = scaling_data.get("budget", {})
            if isinstance(budget_data, dict):
                scaling.budget = BudgetConfig(
                    daily_token_limit=int(
                        budget_data.get("daily_token_limit", 100_000),
                    ),
                    warning_threshold=float(
                        budget_data.get("warning_threshold", 0.8),
                    ),
                )

        return cls(
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            phase=str(data.get("phase", "build")),
            scope=scope,
            sources=sources,
            stationed=stationed,
            scaling=scaling,
        )
