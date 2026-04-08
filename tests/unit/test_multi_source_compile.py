"""Tests for multi-source compilation — Compiler accepts multiple sources."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.agents.compiler import CompilerAgent
from assistonauts.cache.content import Manifest
from tests.helpers import FakeLLMClient

_COMPILED_ARTICLE = """\
---
title: Introduction
type: concept
sources:
  - page-008-009.md
  - page-010-011.md
  - page-012-013.md
created_at: 2026-01-01T00:00:00
status: draft
---

# Introduction

Content compiled from multiple sources about the hidden treasure.

## Key Concepts

The treasure is hidden somewhere in the United States.

## Sources

- page-008-009.md
- page-010-011.md
- page-012-013.md
"""

_SUMMARY = "An introduction to the hidden treasure hunt."


@pytest.fixture
def workspace(initialized_workspace: Path) -> Path:
    return initialized_workspace


def _write_source(workspace: Path, name: str, content: str) -> Path:
    path = workspace / "raw" / "articles" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestMultiSourceCompile:
    """Test Compiler with multiple source files."""

    def test_compile_multiple_sources(self, workspace: Path) -> None:
        src1 = _write_source(workspace, "page-008-009.md", "Page 8-9 content.")
        src2 = _write_source(workspace, "page-010-011.md", "Page 10-11 content.")
        src3 = _write_source(workspace, "page-012-013.md", "Page 12-13 content.")

        llm = FakeLLMClient(responses=[_COMPILED_ARTICLE, _SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        result = compiler.compile_multi(
            source_paths=[src1, src2, src3],
            article_type="concept",
            title="Introduction",
        )
        assert result.success is True
        assert not result.skipped
        assert result.output_path is not None
        assert result.output_path.exists()

    def test_all_sources_in_prompt(self, workspace: Path) -> None:
        """LLM should receive concatenated content from all sources."""
        src1 = _write_source(workspace, "part1.md", "First part content.")
        src2 = _write_source(workspace, "part2.md", "Second part content.")

        llm = FakeLLMClient(responses=[_COMPILED_ARTICLE, _SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        compiler.compile_multi(
            source_paths=[src1, src2],
            article_type="concept",
            title="Test",
        )

        # Check the LLM received both sources
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "First part content" in prompt
        assert "Second part content" in prompt

    def test_all_sources_listed_in_template(self, workspace: Path) -> None:
        src1 = _write_source(workspace, "a.md", "Content A.")
        src2 = _write_source(workspace, "b.md", "Content B.")

        llm = FakeLLMClient(responses=[_COMPILED_ARTICLE, _SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        compiler.compile_multi(
            source_paths=[src1, src2],
            article_type="concept",
            title="Test",
        )

        # Template in prompt should list both sources
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "a.md" in prompt
        assert "b.md" in prompt

    def test_manifest_tracks_all_sources(self, workspace: Path) -> None:
        src1 = _write_source(workspace, "p1.md", "Content 1.")
        src2 = _write_source(workspace, "p2.md", "Content 2.")

        llm = FakeLLMClient(responses=[_COMPILED_ARTICLE, _SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        compiler.compile_multi(
            source_paths=[src1, src2],
            article_type="concept",
            title="Test",
        )

        manifest = Manifest(workspace / "index" / "manifest.json")
        entry = manifest.get("wiki/concept/test.md")
        assert entry is not None
        # Source tracking: downstream from each raw source
        src1_entry = manifest.get("raw/articles/p1.md")
        src2_entry = manifest.get("raw/articles/p2.md")
        if src1_entry:
            assert "wiki/concept/test.md" in src1_entry.downstream
        if src2_entry:
            assert "wiki/concept/test.md" in src2_entry.downstream

    def test_skip_if_no_sources_changed(self, workspace: Path) -> None:
        src1 = _write_source(workspace, "s1.md", "Stable content.")

        llm = FakeLLMClient(
            responses=[_COMPILED_ARTICLE, _SUMMARY, _COMPILED_ARTICLE, _SUMMARY]
        )
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        # First compile
        result1 = compiler.compile_multi(
            source_paths=[src1],
            article_type="concept",
            title="Test",
        )
        assert not result1.skipped

        # Second compile — same sources, should skip
        result2 = compiler.compile_multi(
            source_paths=[src1],
            article_type="concept",
            title="Test",
        )
        assert result2.skipped

    def test_recompile_if_any_source_changed(self, workspace: Path) -> None:
        src1 = _write_source(workspace, "s1.md", "Original.")
        src2 = _write_source(workspace, "s2.md", "Also original.")

        llm = FakeLLMClient(
            responses=[_COMPILED_ARTICLE, _SUMMARY, _COMPILED_ARTICLE, _SUMMARY]
        )
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        compiler.compile_multi(
            source_paths=[src1, src2],
            article_type="concept",
            title="Test",
        )

        # Modify one source
        _write_source(workspace, "s2.md", "Updated content.")

        result = compiler.compile_multi(
            source_paths=[src1, src2],
            article_type="concept",
            title="Test",
        )
        assert not result.skipped

    def test_single_source_still_works(self, workspace: Path) -> None:
        """compile_multi with one source should behave like compile."""
        src = _write_source(workspace, "only.md", "Solo content.")

        llm = FakeLLMClient(responses=[_COMPILED_ARTICLE, _SUMMARY])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        result = compiler.compile_multi(
            source_paths=[src],
            article_type="concept",
            title="Solo Article",
        )
        assert result.success is True


class TestMultiSourceCLI:
    """Test CLI --source repeated for multi-source compilation."""

    def test_multiple_source_flags(self, workspace: Path) -> None:
        from click.testing import CliRunner

        from assistonauts.cli.main import cli

        _write_source(workspace, "a.md", "Content A.")
        _write_source(workspace, "b.md", "Content B.")

        runner = CliRunner()
        # Just verify CLI accepts multiple --source without a parsing error.
        # The actual LLM call will fail (no API available), but we check
        # that the error is NOT "no such option" or similar Click error.
        result = runner.invoke(
            cli,
            [
                "task",
                "run",
                "--agent",
                "compiler",
                "--source",
                str(workspace / "raw/articles/a.md"),
                "--source",
                str(workspace / "raw/articles/b.md"),
                "--title",
                "Multi Test",
                "-w",
                str(workspace),
            ],
        )
        # Click parsing errors return exit code 2
        assert result.exit_code != 2, f"CLI parsing error: {result.output}"
