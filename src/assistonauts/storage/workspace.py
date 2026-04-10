"""Workspace initialization and directory management."""

import subprocess
from pathlib import Path

# Default config template written on first init
_DEFAULT_CONFIG = """\
llm:
  providers:
    anthropic:
      model: claude-haiku-4-5-20251001
      api_key_env: ANTHROPIC_API_KEY
    anthropic_sonnet:
      model: claude-sonnet-4-6-20250514
      api_key_env: ANTHROPIC_API_KEY
  roles:
    scout: anthropic
    compiler: anthropic
    curator: anthropic
    captain: anthropic_sonnet
    inspector: anthropic
    explorer: anthropic

embedding:
  active: gemini
  providers:
    gemini:
      model: gemini-embedding-2-preview
      dimensions: 3072
    ollama:
      model: nomic-embed-text
      base_url: http://localhost:11434
      dimensions: 384

cache:
  llm_responses:
    enabled: true
    backend: sqlite
    ttl_hours: 168
    max_size_mb: 500
"""

_GITIGNORE = """\
.assistonauts/cache/
.assistonauts/logs/
.assistonauts/explorer/
.assistonauts/curator/
index/assistonauts.db
__pycache__/
*.pyc
.env
"""

# All directories that init creates (relative to workspace root)
_DIRECTORIES: list[str] = [
    "raw/papers",
    "raw/articles",
    "raw/repos",
    "raw/datasets",
    "raw/assets",
    "wiki/concept",
    "wiki/entity",
    "wiki/log",
    "wiki/explorations",
    "index",
    "audits/findings",
    "expeditions",
    "station-logs",
    ".assistonauts/agents",
    ".assistonauts/cache",
    ".assistonauts/hooks",
]


def init_workspace(root: Path) -> Path:
    """Initialize an Assistonauts workspace at the given root path.

    Creates the full directory structure, default config, empty manifest,
    and .gitignore. Idempotent — safe to call on an existing workspace
    without destroying content.

    Returns the workspace root path.
    """
    root = Path(root)

    # Create all directories
    for dir_path in _DIRECTORIES:
        (root / dir_path).mkdir(parents=True, exist_ok=True)

    # Write manifest.json only if it doesn't exist
    manifest = root / "index" / "manifest.json"
    if not manifest.exists():
        manifest.write_text("{}\n")

    # Write default config only if it doesn't exist
    config = root / ".assistonauts" / "config.yaml"
    if not config.exists():
        config.write_text(_DEFAULT_CONFIG)

    # Write .gitignore only if it doesn't exist
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_GITIGNORE)

    # Initialize git repo if not already one
    if not (root / ".git").exists():
        subprocess.run(
            ["git", "init"],
            cwd=root,
            capture_output=True,
            check=True,
        )

    return root
