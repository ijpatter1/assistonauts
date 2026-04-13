"""Expedition lifecycle — creation and directory setup."""

from __future__ import annotations

from pathlib import Path

import yaml

from assistonauts.models.config import ExpeditionConfig


def create_expedition(
    config: ExpeditionConfig,
    expeditions_dir: Path,
) -> Path:
    """Create an expedition directory with config and subdirectories.

    Sets up: expeditions/<name>/expedition.yaml, missions/, review/.
    Raises FileExistsError if the expedition already exists.
    """
    exp_dir = expeditions_dir / config.name
    if exp_dir.exists():
        msg = f"Expedition already exists: {exp_dir}"
        raise FileExistsError(msg)

    exp_dir.mkdir(parents=True)
    (exp_dir / "missions").mkdir()
    (exp_dir / "review").mkdir()

    # Write expedition.yaml — persist full config
    exp_data: dict[str, object] = {
        "expedition": {
            "name": config.name,
            "description": config.description,
            "purpose": config.purpose,
            "phase": config.phase,
            "scope": {
                "description": config.scope.description,
                "keywords": config.scope.keywords,
            },
            "sources": {
                "local": [
                    {"path": ls.path, "pattern": ls.pattern}
                    for ls in config.sources.local
                ],
            },
            "stationed": {
                "resources": {
                    "daily_token_budget": (
                        config.stationed.resources.daily_token_budget
                    ),
                    "max_concurrent_missions": (
                        config.stationed.resources.max_concurrent_missions
                    ),
                },
                "schedule": config.stationed.schedule,
                "triggers": config.stationed.triggers,
            },
            "scaling": {
                "agents": config.scaling.agents,
                "auto_scale": {
                    "trigger": config.scaling.auto_scale.trigger,
                    "max_instances": config.scaling.auto_scale.max_instances,
                    "cooldown_minutes": config.scaling.auto_scale.cooldown_minutes,
                },
                "budget": {
                    "daily_token_limit": config.scaling.budget.daily_token_limit,
                    "warning_threshold": config.scaling.budget.warning_threshold,
                },
            },
        },
    }
    (exp_dir / "expedition.yaml").write_text(
        yaml.dump(exp_data, default_flow_style=False),
    )

    return exp_dir


def create_expedition_from_file(
    config_path: Path,
    workspace_root: Path,
) -> Path:
    """Create an expedition from a YAML config file."""
    data = yaml.safe_load(config_path.read_text())
    config = ExpeditionConfig.from_dict(
        data.get("expedition", data),
    )
    expeditions_dir = workspace_root / "expeditions"
    expeditions_dir.mkdir(parents=True, exist_ok=True)
    return create_expedition(config, expeditions_dir)
