"""Tests for Bug 1: absolute paths should not leak into artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from assistonauts.agents.compiler import (
    ArticleType,
    CompilationPlan,
    CompilerAgent,
    PlannedArticle,
)
from assistonauts.agents.scout import ScoutAgent
from assistonauts.tasks.runner import Task, TaskRunner
from tests.helpers import FakeLLMClient

_FAKE_ARTICLE = """\
---
title: Test
type: concept
sources:
  - test-source.md
---

# Test

## Overview

Content here.
"""

_FAKE_SUMMARY = "A summary of the test article."


def _setup_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace structure."""
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    raw_dir = root / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "test-source.md"
    source.write_text(
        "---\nsource: test-source.md\ningested_by: scout\n---\n\n# Test\n\nContent.\n"
    )
    return root


class TestScoutSourcePathNotAbsolute:
    """Bug 1a: Scout should not write absolute paths in frontmatter."""

    def test_source_path_is_not_absolute(self, tmp_path: Path) -> None:
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "input.txt"
        source.write_text("Some content.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.success is True
        assert result.output_path is not None
        content = result.output_path.read_text()
        # source_path should NOT contain an absolute path
        for line in content.splitlines():
            if line.startswith("source_path:"):
                value = line.split(":", 1)[1].strip()
                assert not value.startswith("/"), (
                    f"source_path should not be absolute, got: {value}"
                )
                break
        else:
            raise AssertionError("source_path not found in frontmatter")


class TestCompilerSummaryPathNotAbsolute:
    """Bug 1b: Compiler summary JSON article_path should be relative."""

    def test_summary_article_path_is_relative(self, tmp_path: Path) -> None:
        ws = _setup_workspace(tmp_path)
        llm = FakeLLMClient([_FAKE_ARTICLE, _FAKE_SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=ws)

        result = compiler.compile(
            source_path=ws / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test",
        )
        assert result.output_path is not None
        summary_path = result.output_path.with_suffix(".summary.json")
        data = json.loads(summary_path.read_text())
        assert not data["article_path"].startswith("/"), (
            f"article_path should be relative, got: {data['article_path']}"
        )

    def test_compile_multi_summary_article_path_is_relative(
        self, tmp_path: Path
    ) -> None:
        ws = _setup_workspace(tmp_path)
        llm = FakeLLMClient([_FAKE_ARTICLE, _FAKE_SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=ws)

        result = compiler.compile_multi(
            source_paths=[ws / "raw" / "articles" / "test-source.md"],
            article_type=ArticleType.CONCEPT,
            title="Test",
        )
        assert result.output_path is not None
        summary_path = result.output_path.with_suffix(".summary.json")
        data = json.loads(summary_path.read_text())
        assert not data["article_path"].startswith("/"), (
            f"article_path should be relative, got: {data['article_path']}"
        )


class TestCompilationPlanSourcesNotAbsolute:
    """Bug 1c: CompilationPlan.save() should store relative paths."""

    def test_plan_sources_are_relative(self, tmp_path: Path) -> None:
        ws = _setup_workspace(tmp_path)
        plans_dir = ws / ".assistonauts" / "plans"

        # Use absolute paths as they'd come from resolved sources
        plan = CompilationPlan(
            articles=[
                PlannedArticle(
                    title="Test Article",
                    article_type=ArticleType.CONCEPT,
                    source_paths=[ws / "raw" / "articles" / "test-source.md"],
                )
            ]
        )
        plan_path = plan.save(plans_dir, workspace_root=ws)
        data = yaml.safe_load(plan_path.read_text())

        for article in data["articles"]:
            for source in article["sources"]:
                assert not source.startswith("/"), (
                    f"Plan source should be relative, got: {source}"
                )


class TestTaskRunnerAuditPathsNotAbsolute:
    """Bug 1d: Task runner audit trails should relativize paths."""

    def test_audit_params_have_relative_paths(self, tmp_path: Path) -> None:
        ws = _setup_workspace(tmp_path)
        tasks_dir = ws / ".assistonauts" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)

        llm = FakeLLMClient([_FAKE_ARTICLE, _FAKE_SUMMARY])
        runner = TaskRunner(workspace_root=ws, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-rel-001",
            agent="compiler",
            params={
                "source_path": str(ws / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test",
            },
        )
        runner.run(task, llm_client=llm)

        audit_file = tasks_dir / "t-rel-001.yaml"
        assert audit_file.exists()
        audit = yaml.safe_load(audit_file.read_text())
        params = audit["params"]
        # source_path should not be absolute
        if "source_path" in params:
            assert not params["source_path"].startswith("/"), (
                f"source_path in audit should be relative, got: {params['source_path']}"
            )
        if "source_paths" in params:
            for p in params["source_paths"].split(","):
                assert not p.strip().startswith("/"), (
                    f"source_paths in audit should be relative, got: {p.strip()}"
                )
