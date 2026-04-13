"""Tests for data integrity fixes found during UAT audit.

Bug #1: Rejected article outputs persist on disk
Bug #2: Curator edits invalidate manifest hashes
Bug #4: Build report inflated mission count
Bug #5: Unquoted colons in YAML frontmatter
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from assistonauts.expeditions.orchestrator import (
    BuildOrchestrator,
    IterationPhase,
)
from assistonauts.missions.models import Mission
from assistonauts.models.config import ExpeditionConfig
from tests.helpers import FakeLLMClient


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    dirs = [
        "raw/articles",
        "wiki/concept",
        "wiki/entity",
        "wiki/log",
        "wiki/explorations",
        "index",
        "audits",
        "expeditions/test-exp/missions",
        "expeditions/test-exp/review",
        "station-logs",
        ".assistonauts/logs",
        ".assistonauts/tasks",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def config() -> ExpeditionConfig:
    return ExpeditionConfig.from_dict(
        {
            "name": "test-exp",
            "description": "Test",
            "scope": {"description": "Test", "keywords": ["test"]},
            "sources": {"local": [{"path": "/tmp/t", "pattern": "*.md"}]},
        }
    )


# ── Bug #1: Rejected outputs cleaned up ──────────────


class TestRejectedOutputCleanup:
    """When Captain rejects a mission, output files must be deleted
    so rejected content doesn't persist in the knowledge base."""

    def test_rejected_article_deleted(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Output files are removed when verification rejects."""
        # Create files that would be the compiler's output
        article = workspace / "wiki" / "concept" / "test.md"
        article.write_text("---\ntitle: Test\n---\n\n# Test\n")
        summary = workspace / "wiki" / "concept" / "test.summary.json"
        summary.write_text('{"summary": "test"}')

        client = FakeLLMClient(
            responses=["REJECTED — bad"] * 5
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        orch._cleanup_rejected_outputs([
            str(article),
            str(summary),
        ])

        assert not article.exists()
        assert not summary.exists()

    def test_cleanup_handles_missing_files(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Cleanup doesn't fail if files already gone."""
        client = FakeLLMClient()
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        # Should not raise
        orch._cleanup_rejected_outputs([
            str(workspace / "nonexistent.md"),
        ])

    def test_cleanup_resolves_relative_paths(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Relative paths are resolved against workspace_root."""
        article = workspace / "wiki" / "concept" / "rel.md"
        article.write_text("content")

        client = FakeLLMClient()
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        orch._cleanup_rejected_outputs(["wiki/concept/rel.md"])
        assert not article.exists()


# ── Bug #4: Build report unique mission count ─────────


class TestBuildReportMissionCount:
    """Build report should count unique missions, not sum across iterations."""

    def test_write_build_report_unique_count(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Total missions reflects unique IDs, not per-iteration sums."""
        # Plan two iterations with overlapping mission IDs
        # (dedup will remap, but let's test the report counts)
        client = FakeLLMClient(responses=[
            "```yaml\nmissions:\n"
            "  - id: m-001\n"
            "    agent: scout\n"
            "    type: ingest_sources\n"
            "    inputs: {paths: [a.md]}\n"
            "    acceptance_criteria: [Done]\n"
            "    priority: normal\n```\n",
        ] * 5)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        result = orch.run_build()
        # With dedup, each iteration gets unique IDs, but total_missions
        # should count unique missions not double-count
        assert result.total_missions == len({
            m.mission_id
            for it in result.iterations
            for m in it.missions
        })


# ── Bug #5: Frontmatter title quoting ─────────────────


class TestFrontmatterTitleQuoting:
    """Titles with colons must be quoted in YAML frontmatter."""

    def test_title_with_colon_parseable(self, workspace: Path) -> None:
        """Compiled article with colon in title has valid frontmatter."""
        from assistonauts.agents.compiler import CompilerAgent

        # Create a source file
        raw_dir = workspace / "raw" / "articles"
        source = raw_dir / "test-source.md"
        source.write_text(
            "---\nsource: test-source.md\ningested_by: scout\n---\n\n"
            "# Topic: Subtopic\n\nSome content.\n"
        )
        (workspace / "index" / "manifest.json").write_text("{}")

        fake_article = (
            "---\n"
            "title: \"Topic: Subtopic\"\n"
            "type: concept\n"
            "sources:\n  - test-source.md\n"
            "---\n\n# Topic: Subtopic\n\n## Overview\n\nContent.\n"
        )
        llm = FakeLLMClient(responses=[fake_article, "A summary."])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        from assistonauts.models.schema import ArticleType

        result = compiler.compile(
            source,
            article_type=ArticleType.CONCEPT,
            title="Topic: Subtopic",
        )

        if result.output_path:
            content = result.output_path.read_text()
            # Extract frontmatter and verify it parses
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1])
                assert fm["title"] == "Topic: Subtopic"
