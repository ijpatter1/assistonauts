"""Tests for mission-level git commits."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from assistonauts.missions.runner import (
    Mission,
    MissionRunner,
)

_FAKE_ARTICLE = (
    "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent."
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fake-model"
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5}


class FakeLLMClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ["default"])
        self._call_count = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FakeResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return FakeResponse(self._responses[idx])


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """Create a workspace with git initialized."""
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    # Configure git user for test commits
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    # init_workspace already creates a git repo, but make an initial commit
    subprocess.run(
        ["git", "add", "-A"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    # Create raw source
    raw_dir = root / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "test-source.md"
    source.write_text(
        "---\nsource: test-source.md\ningested_by: scout\n---\n\n"
        "# Git Test\n\nContent for git test.\n"
    )
    subprocess.run(
        ["git", "add", "-A"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "add source"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return root


class TestMissionGitCommits:
    """Test that completed missions produce git commits."""

    def test_successful_mission_creates_commit(self, git_workspace: Path) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "Summary of git test.",
            ]
        )
        missions_dir = git_workspace / ".assistonauts" / "missions"
        missions_dir.mkdir(parents=True, exist_ok=True)
        runner = MissionRunner(
            workspace_root=git_workspace,
            missions_dir=missions_dir,
            auto_commit=True,
        )
        mission = Mission(
            mission_id="m-git-001",
            agent="compiler",
            params={
                "source_path": str(
                    git_workspace / "raw" / "articles" / "test-source.md"
                ),
                "article_type": "concept",
                "title": "Git Test",
            },
        )
        result = runner.run(mission, llm_client=llm)
        assert result.success is True

        # Check git log for mission commit
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        assert "m-git-001" in log.stdout
        assert "compiler" in log.stdout

    def test_failed_mission_no_commit(self, git_workspace: Path) -> None:
        llm = FakeLLMClient()
        missions_dir = git_workspace / ".assistonauts" / "missions"
        missions_dir.mkdir(parents=True, exist_ok=True)
        runner = MissionRunner(
            workspace_root=git_workspace,
            missions_dir=missions_dir,
            auto_commit=True,
        )
        # Get commit count before
        before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        mission = Mission(
            mission_id="m-git-002",
            agent="compiler",
            params={
                "source_path": "/nonexistent/path.md",
                "article_type": "concept",
                "title": "Bad",
            },
        )
        result = runner.run(mission, llm_client=llm)
        assert result.success is False

        # Commit count should not have increased
        after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        assert before.stdout.strip() == after.stdout.strip()

    def test_commit_message_format(self, git_workspace: Path) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "Summary.",
            ]
        )
        missions_dir = git_workspace / ".assistonauts" / "missions"
        missions_dir.mkdir(parents=True, exist_ok=True)
        runner = MissionRunner(
            workspace_root=git_workspace,
            missions_dir=missions_dir,
            auto_commit=True,
        )
        mission = Mission(
            mission_id="m-git-003",
            agent="compiler",
            params={
                "source_path": str(
                    git_workspace / "raw" / "articles" / "test-source.md"
                ),
                "article_type": "concept",
                "title": "Msg Test",
            },
        )
        runner.run(mission, llm_client=llm)

        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        msg = log.stdout.strip()
        # Format: [mission-<id>] <agent>: <description>
        assert msg.startswith("[mission-m-git-003]")
        assert "compiler:" in msg

    def test_auto_commit_disabled_by_default(self, git_workspace: Path) -> None:
        """When auto_commit is False (default), no commit is made."""
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "Summary.",
            ]
        )
        missions_dir = git_workspace / ".assistonauts" / "missions"
        missions_dir.mkdir(parents=True, exist_ok=True)
        runner = MissionRunner(
            workspace_root=git_workspace,
            missions_dir=missions_dir,
            # auto_commit defaults to False
        )
        before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        mission = Mission(
            mission_id="m-git-004",
            agent="compiler",
            params={
                "source_path": str(
                    git_workspace / "raw" / "articles" / "test-source.md"
                ),
                "article_type": "concept",
                "title": "No Commit",
            },
        )
        runner.run(mission, llm_client=llm)

        after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=git_workspace,
            capture_output=True,
            text=True,
        )
        assert before.stdout.strip() == after.stdout.strip()
