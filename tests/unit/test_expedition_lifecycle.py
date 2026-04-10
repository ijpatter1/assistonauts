"""Tests for expedition lifecycle — config models, creation, CLI."""

from pathlib import Path

import pytest
import yaml

from assistonauts.models.config import (
    ExpeditionConfig,
    ExpeditionResources,
    ScalingConfig,
    StationedConfig,
)

# --- Extended config models ---


class TestExpeditionResources:
    def test_defaults(self) -> None:
        r = ExpeditionResources()
        assert r.daily_token_budget == 100_000
        assert r.max_concurrent_missions == 3

    def test_custom(self) -> None:
        r = ExpeditionResources(
            daily_token_budget=50_000,
            max_concurrent_missions=5,
        )
        assert r.daily_token_budget == 50_000
        assert r.max_concurrent_missions == 5


class TestScalingConfig:
    def test_defaults(self) -> None:
        s = ScalingConfig()
        assert s.agents == {}
        assert s.auto_scale.trigger == "queue_depth > 5"
        assert s.auto_scale.max_instances == 3
        assert s.budget.daily_token_limit == 100_000

    def test_singleton_check(self) -> None:
        s = ScalingConfig(
            agents={"scout": "auto", "compiler": "auto"},
        )
        assert s.is_scalable("scout")
        assert s.is_scalable("compiler")
        assert not s.is_scalable("captain")
        assert not s.is_scalable("curator")
        assert not s.is_scalable("inspector")


class TestStationedConfig:
    def test_defaults(self) -> None:
        sc = StationedConfig()
        assert sc.resources.daily_token_budget == 100_000
        assert sc.schedule == {}
        assert sc.triggers == {}


class TestExpeditionConfigExtended:
    def test_full_yaml_roundtrip(self, tmp_path: Path) -> None:
        yaml_content = """\
expedition:
  name: autotrader-research
  description: "BTC/USD prediction research"
  phase: build
  scope:
    description: "ML approaches to crypto prediction"
    keywords: [ML, trading, BTC]
  sources:
    local:
      - path: ~/research/papers/
        pattern: "*.pdf"
  stationed:
    resources:
      daily_token_budget: 50000
      max_concurrent_missions: 2
    schedule:
      scout_watch: "*/6 * * * *"
    triggers:
      on_new_source: [compiler]
  scaling:
    agents:
      scout: auto
      compiler: auto
    auto_scale:
      trigger: "queue_depth > 3"
      max_instances: 2
      cooldown_minutes: 5
    budget:
      daily_token_limit: 50000
      warning_threshold: 0.9
"""
        config_file = tmp_path / "expedition.yaml"
        config_file.write_text(yaml_content)

        data = yaml.safe_load(config_file.read_text())
        config = ExpeditionConfig.from_dict(data.get("expedition", {}))

        assert config.name == "autotrader-research"
        assert config.phase == "build"
        assert config.scope.keywords == ["ML", "trading", "BTC"]
        assert len(config.sources.local) == 1
        assert config.stationed.resources.daily_token_budget == 50_000
        assert config.stationed.resources.max_concurrent_missions == 2
        assert config.scaling.auto_scale.max_instances == 2
        assert config.scaling.budget.daily_token_limit == 50_000
        assert config.scaling.budget.warning_threshold == 0.9

    def test_stationed_reporting_parsed(self) -> None:
        data = {
            "name": "rpt-test",
            "stationed": {
                "reporting": {
                    "station_log": "weekly",
                },
            },
        }
        config = ExpeditionConfig.from_dict(data)
        assert config.stationed.reporting == {"station_log": "weekly"}

    def test_minimal_config(self) -> None:
        data = {"name": "test", "description": "test expedition"}
        config = ExpeditionConfig.from_dict(data)
        assert config.name == "test"
        assert config.phase == "build"
        assert config.stationed.resources.daily_token_budget == 100_000
        assert config.scaling.auto_scale.max_instances == 3

    def test_unknown_source_types_ignored(self) -> None:
        data = {
            "name": "test",
            "sources": {
                "local": [{"path": "/tmp", "pattern": "*.md"}],
                "rss": [{"url": "https://arxiv.org/rss"}],
                "github": [{"repo": "owner/repo"}],
            },
        }
        config = ExpeditionConfig.from_dict(data)
        assert len(config.sources.local) == 1

    def test_unknown_source_types_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="assistonauts.models.config"):
            data = {
                "name": "test",
                "sources": {
                    "local": [{"path": "/tmp", "pattern": "*.md"}],
                    "rss": [{"url": "https://example.com"}],
                    "github": [{"repo": "a/b"}, {"repo": "c/d"}],
                },
            }
            ExpeditionConfig.from_dict(data)

        assert any("rss" in r.message.lower() for r in caplog.records)
        assert any("github" in r.message.lower() for r in caplog.records)
        assert any("2 entries" in r.message for r in caplog.records)


# --- Expedition directory creation ---


class TestExpeditionCreate:
    def test_create_expedition_dirs(self, tmp_path: Path) -> None:
        from assistonauts.expeditions.lifecycle import (
            create_expedition,
        )

        config = ExpeditionConfig.from_dict(
            {
                "name": "test-exp",
                "description": "A test expedition",
            }
        )
        exp_dir = create_expedition(config, tmp_path)

        assert exp_dir.exists()
        assert (exp_dir / "expedition.yaml").exists()
        assert (exp_dir / "missions").is_dir()
        assert (exp_dir / "review").is_dir()

        # Verify expedition.yaml has full config
        loaded = yaml.safe_load(
            (exp_dir / "expedition.yaml").read_text(),
        )
        assert loaded["expedition"]["name"] == "test-exp"
        assert "sources" in loaded["expedition"]
        assert "stationed" in loaded["expedition"]
        assert "scaling" in loaded["expedition"]
        assert loaded["expedition"]["scaling"]["budget"]["daily_token_limit"] == 100_000

    def test_create_expedition_from_file(
        self,
        tmp_path: Path,
    ) -> None:
        from assistonauts.expeditions.lifecycle import (
            create_expedition_from_file,
        )

        yaml_content = """\
expedition:
  name: from-file
  description: "Created from file"
  scope:
    description: "Test scope"
    keywords: [test]
"""
        config_file = tmp_path / "input.yaml"
        config_file.write_text(yaml_content)

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "expeditions").mkdir()

        exp_dir = create_expedition_from_file(
            config_file,
            workspace,
        )
        assert exp_dir.exists()
        assert (exp_dir / "expedition.yaml").exists()

    def test_create_expedition_already_exists(
        self,
        tmp_path: Path,
    ) -> None:
        from assistonauts.expeditions.lifecycle import (
            create_expedition,
        )

        config = ExpeditionConfig.from_dict({"name": "dup"})
        (tmp_path / "expeditions").mkdir()
        exp_base = tmp_path / "expeditions"
        create_expedition(config, exp_base)
        with pytest.raises(FileExistsError):
            create_expedition(config, exp_base)
