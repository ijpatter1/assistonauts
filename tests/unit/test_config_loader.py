"""Tests for config loading system."""

from pathlib import Path

import pytest
import yaml

from assistonauts.config.loader import (
    load_config,
    load_expedition_config,
)
from assistonauts.models.config import (
    AssistonautsConfig,
    CacheConfig,
    EmbeddingConfig,
    ExpeditionConfig,
    LLMConfig,
    LLMProviderConfig,
)


class TestLoadConfig:
    """Test global config loading from .assistonauts/config.yaml."""

    def test_loads_valid_config(self, tmp_workspace: Path) -> None:
        """Loads a well-formed config.yaml into an AssistonautsConfig."""
        config_dir = tmp_workspace / ".assistonauts"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump(
                {
                    "llm": {
                        "providers": {
                            "anthropic": {
                                "model": "claude-sonnet-4-20250514",
                                "api_key_env": "ANTHROPIC_API_KEY",
                            }
                        },
                        "roles": {"scout": "anthropic"},
                    },
                    "embedding": {
                        "active": "ollama",
                        "providers": {
                            "ollama": {
                                "model": "nomic-embed-text",
                                "base_url": "http://localhost:11434",
                            }
                        },
                    },
                    "cache": {
                        "llm_responses": {
                            "enabled": True,
                            "backend": "sqlite",
                            "ttl_hours": 168,
                            "max_size_mb": 500,
                        }
                    },
                }
            )
        )

        config = load_config(tmp_workspace)

        assert isinstance(config, AssistonautsConfig)
        assert "anthropic" in config.llm.providers
        assert config.llm.providers["anthropic"].model == "claude-sonnet-4-20250514"
        assert config.llm.roles["scout"] == "anthropic"
        assert config.embedding.active == "ollama"
        assert config.cache.llm_responses.enabled is True

    def test_missing_config_returns_defaults(self, tmp_workspace: Path) -> None:
        """Returns default config when config.yaml doesn't exist."""
        config = load_config(tmp_workspace)

        assert isinstance(config, AssistonautsConfig)
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.cache, CacheConfig)

    def test_partial_config_fills_defaults(self, tmp_workspace: Path) -> None:
        """Missing sections are filled with defaults."""
        config_dir = tmp_workspace / ".assistonauts"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump({"llm": {"roles": {"scout": "ollama"}}})
        )

        config = load_config(tmp_workspace)

        assert config.llm.roles["scout"] == "ollama"
        # Embedding and cache should have defaults
        assert isinstance(config.embedding, EmbeddingConfig)
        assert isinstance(config.cache, CacheConfig)

    def test_unknown_keys_are_ignored(self, tmp_workspace: Path) -> None:
        """Unknown top-level keys don't cause errors."""
        config_dir = tmp_workspace / ".assistonauts"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump({"llm": {"roles": {}}, "unknown_section": True})
        )

        config = load_config(tmp_workspace)
        assert isinstance(config, AssistonautsConfig)

    def test_provider_config_fields(self, tmp_workspace: Path) -> None:
        """Provider config captures model, api_key_env, and base_url."""
        config_dir = tmp_workspace / ".assistonauts"
        config_dir.mkdir(parents=True)
        (config_dir / "config.yaml").write_text(
            yaml.dump(
                {
                    "llm": {
                        "providers": {
                            "ollama": {
                                "model": "llama3.2",
                                "base_url": "http://localhost:11434",
                            }
                        },
                        "roles": {},
                    }
                }
            )
        )

        config = load_config(tmp_workspace)
        ollama = config.llm.providers["ollama"]
        assert isinstance(ollama, LLMProviderConfig)
        assert ollama.model == "llama3.2"
        assert ollama.base_url == "http://localhost:11434"
        assert ollama.api_key_env is None


class TestLoadExpeditionConfig:
    """Test expedition config loading."""

    def test_loads_expedition_config(self, tmp_workspace: Path) -> None:
        """Loads a valid expedition.yaml."""
        exp_dir = tmp_workspace / "expeditions" / "test-exp"
        exp_dir.mkdir(parents=True)
        (exp_dir / "expedition.yaml").write_text(
            yaml.dump(
                {
                    "expedition": {
                        "name": "test-expedition",
                        "description": "A test expedition",
                        "phase": "build",
                        "scope": {
                            "description": "Testing scope",
                            "keywords": ["test", "demo"],
                        },
                        "sources": {
                            "local": [
                                {
                                    "path": "~/papers/",
                                    "pattern": "*.pdf",
                                }
                            ]
                        },
                    }
                }
            )
        )

        config = load_expedition_config(exp_dir / "expedition.yaml")

        assert isinstance(config, ExpeditionConfig)
        assert config.name == "test-expedition"
        assert config.phase == "build"
        assert config.scope.keywords == ["test", "demo"]
        assert len(config.sources.local) == 1

    def test_missing_expedition_file_raises(self, tmp_workspace: Path) -> None:
        """Raises FileNotFoundError for missing expedition.yaml."""
        with pytest.raises(FileNotFoundError):
            load_expedition_config(
                tmp_workspace / "expeditions" / "nope" / "expedition.yaml"
            )

    def test_expedition_minimal_config(self, tmp_workspace: Path) -> None:
        """Expedition with only required fields loads correctly."""
        exp_dir = tmp_workspace / "expeditions" / "minimal"
        exp_dir.mkdir(parents=True)
        (exp_dir / "expedition.yaml").write_text(
            yaml.dump(
                {
                    "expedition": {
                        "name": "minimal",
                        "description": "Minimal expedition",
                    }
                }
            )
        )

        config = load_expedition_config(exp_dir / "expedition.yaml")
        assert config.name == "minimal"
        assert config.phase == "build"  # default
