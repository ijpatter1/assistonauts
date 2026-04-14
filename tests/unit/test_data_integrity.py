"""Tests for data integrity fixes found during UAT audit.

Bug #1: Rejected article outputs persist on disk
Bug #2: Curator edits invalidate manifest hashes
Bug #4: Build report inflated mission count
Bug #5: Unquoted colons in YAML frontmatter
QI #3: Mission-level events in LLM trace
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

        client = FakeLLMClient(responses=["REJECTED — bad"] * 5)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        orch._cleanup_rejected_outputs(
            [
                str(article),
                str(summary),
            ]
        )

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
        orch._cleanup_rejected_outputs(
            [
                str(workspace / "nonexistent.md"),
            ]
        )

    def test_cleanup_skips_outside_workspace(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Cleanup refuses to delete files outside workspace boundary."""
        # Create a file in /tmp — clearly outside workspace
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
            f.write("do not delete")
            outside_path = Path(f.name)

        try:
            client = FakeLLMClient()
            orch = BuildOrchestrator(
                workspace_root=workspace,
                config=config,
                llm_client=client,
            )
            orch._cleanup_rejected_outputs([str(outside_path)])
            assert outside_path.exists(), "File outside workspace must not be deleted"
        finally:
            outside_path.unlink(missing_ok=True)

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
        client = FakeLLMClient(
            responses=[
                "```yaml\nmissions:\n"
                "  - id: m-001\n"
                "    agent: scout\n"
                "    type: ingest_sources\n"
                "    inputs: {paths: [a.md]}\n"
                "    acceptance_criteria: [Done]\n"
                "    priority: normal\n```\n",
            ]
            * 5
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        result = orch.run_build()
        # With dedup, each iteration gets unique IDs, but total_missions
        # should count unique missions not double-count
        assert result.total_missions == len(
            {m.mission_id for it in result.iterations for m in it.missions}
        )


# ── Bug #5: Frontmatter title quoting ─────────────────


class TestFrontmatterTitleQuoting:
    """Titles with colons must be quoted in YAML frontmatter."""

    def test_title_with_colon_parseable(self, workspace: Path) -> None:
        """Compiled article with colon in title has valid frontmatter.

        The LLM returns an UNQUOTED title — _fix_frontmatter_quoting must
        fix it before writing to disk.
        """
        from assistonauts.agents.compiler import CompilerAgent

        # Create a source file
        raw_dir = workspace / "raw" / "articles"
        source = raw_dir / "test-source.md"
        source.write_text(
            "---\nsource: test-source.md\ningested_by: scout\n---\n\n"
            "# Topic: Subtopic\n\nSome content.\n"
        )
        (workspace / "index" / "manifest.json").write_text("{}")

        # LLM returns UNQUOTED colon — exercises the fix path
        fake_article = (
            "---\n"
            "title: Topic: Subtopic\n"
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

        assert result.output_path is not None, "Compilation should produce output"
        content = result.output_path.read_text()
        parts = content.split("---", 2)
        assert len(parts) >= 3, "Article should have frontmatter delimiters"
        fm = yaml.safe_load(parts[1])
        assert fm is not None, "Frontmatter should parse as valid YAML"
        assert fm["title"] == "Topic: Subtopic"

    def test_fix_frontmatter_quoting_function(self) -> None:
        """_fix_frontmatter_quoting handles various colon cases."""
        from assistonauts.agents.compiler import _fix_frontmatter_quoting

        # Unquoted colon gets quoted
        content = "---\ntitle: A: B\ntype: concept\n---\n\n# A: B\n"
        fixed = _fix_frontmatter_quoting(content)
        assert 'title: "A: B"' in fixed

        # Already quoted — unchanged
        content2 = '---\ntitle: "A: B"\ntype: concept\n---\n'
        assert _fix_frontmatter_quoting(content2) == content2

        # No colon — unchanged
        content3 = "---\ntitle: Simple Title\ntype: concept\n---\n"
        assert _fix_frontmatter_quoting(content3) == content3

    def test_template_engine_quotes_colons(self) -> None:
        """render_template quotes titles that contain colons."""
        from assistonauts.models.schema import ArticleType, get_default_schema
        from assistonauts.templates.engine import render_template

        schema = get_default_schema()
        output = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Topic: Subtopic",
            sources=["a.md"],
        )
        # Extract frontmatter and verify it parses
        parts = output.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert fm["title"] == "Topic: Subtopic"


# ── QI #3: Mission lifecycle events in trace ──────────


class TestMissionLifecycleTrace:
    """Missions that complete without LLM calls should still appear
    in the trace file via mission_start/mission_complete events."""

    def test_mission_events_in_trace(self, workspace: Path) -> None:
        """run_build writes mission_start and mission_completed events."""
        import json

        from assistonauts.expeditions.orchestrator import BuildOrchestrator
        from assistonauts.models.config import ExpeditionConfig

        cfg = ExpeditionConfig.from_dict(
            {
                "name": "test-exp",
                "description": "Test",
                "scope": {"description": "Test", "keywords": ["test"]},
                "sources": {"local": [{"path": "/tmp/t", "pattern": "*.md"}]},
            }
        )

        # Create a source so scout has something to ingest
        source = workspace / "test-sources" / "a.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# Test\n\nContent.")

        # Scout ingests, auto-approved — no verification LLM call
        plan = (
            "```yaml\nmissions:\n"
            "  - id: m-scout-1\n"
            "    agent: scout\n"
            "    type: ingest_sources\n"
            "    inputs:\n"
            "      paths:\n"
            f"        - {source}\n"
            "    acceptance_criteria: [Ingested]\n"
            "    priority: normal\n```\n"
        )
        client = FakeLLMClient(responses=[plan] * 5)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=cfg,
            llm_client=client,
        )
        orch.run_build()

        trace_file = workspace / "expeditions" / "test-exp" / "llm-trace.jsonl"
        assert trace_file.exists()
        entries = [
            json.loads(line)
            for line in trace_file.read_text().splitlines()
            if line.strip()
        ]

        events = [e.get("event") for e in entries if "event" in e]
        assert "mission_start" in events
        # Should have a completion event (mission_completed or mission_failed)
        completion_events = [
            e for e in events if e and e.startswith("mission_") and e != "mission_start"
        ]
        assert len(completion_events) > 0
