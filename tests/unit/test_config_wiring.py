"""Tests for config→LLM client wiring."""

from __future__ import annotations

from pathlib import Path

import yaml

from assistonauts.config.loader import load_config
from assistonauts.llm.client import LLMClient


class TestLLMClientDefaultModel:
    """Test that LLMClient uses configured default model."""

    def test_default_model_stored(self) -> None:
        client = LLMClient(
            provider_config={},
            default_model="ollama/gemma3",
        )
        assert client.default_model == "ollama/gemma3"

    def test_default_model_fallback(self) -> None:
        client = LLMClient(provider_config={})
        assert client.default_model == "gpt-3.5-turbo"

    def test_base_url_stored(self) -> None:
        client = LLMClient(
            provider_config={},
            base_url="http://localhost:11434",
        )
        assert client.base_url == "http://localhost:11434"


class TestResolveProviderFromConfig:
    """Test resolving LLM provider settings from workspace config."""

    def test_resolve_model_for_role(self, tmp_path: Path) -> None:
        from assistonauts.config.resolver import resolve_llm_for_role

        config_dir = tmp_path / ".assistonauts"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {
                        "providers": {
                            "local": {
                                "model": "ollama/gemma3",
                                "base_url": "http://localhost:11434",
                            },
                        },
                        "roles": {
                            "compiler": "local",
                            "scout": "local",
                        },
                    }
                }
            )
        )
        config = load_config(tmp_path)
        model, base_url = resolve_llm_for_role(config, "compiler")
        assert model == "ollama/gemma3"
        assert base_url == "http://localhost:11434"

    def test_resolve_unknown_role_returns_defaults(self, tmp_path: Path) -> None:
        from assistonauts.config.resolver import resolve_llm_for_role

        config = load_config(tmp_path)  # no config file → defaults
        model, base_url = resolve_llm_for_role(config, "compiler")
        assert model == "gpt-3.5-turbo"
        assert base_url is None

    def test_resolve_role_with_missing_provider(self, tmp_path: Path) -> None:
        from assistonauts.config.resolver import resolve_llm_for_role

        config_dir = tmp_path / ".assistonauts"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {
                        "providers": {},
                        "roles": {"compiler": "nonexistent"},
                    }
                }
            )
        )
        config = load_config(tmp_path)
        model, base_url = resolve_llm_for_role(config, "compiler")
        # Falls back to default when provider not found
        assert model == "gpt-3.5-turbo"
        assert base_url is None

    def test_resolve_first_provider_when_no_role_mapping(self, tmp_path: Path) -> None:
        from assistonauts.config.resolver import resolve_llm_for_role

        config_dir = tmp_path / ".assistonauts"
        config_dir.mkdir()
        config_file = config_dir / "config.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "llm": {
                        "providers": {
                            "local": {
                                "model": "ollama/gemma3",
                                "base_url": "http://localhost:11434",
                            },
                        },
                        # no roles mapping
                    }
                }
            )
        )
        config = load_config(tmp_path)
        model, base_url = resolve_llm_for_role(config, "compiler")
        # With providers but no role mapping, use first provider
        assert model == "ollama/gemma3"
        assert base_url == "http://localhost:11434"
