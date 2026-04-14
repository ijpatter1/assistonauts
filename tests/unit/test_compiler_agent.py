"""Tests for the Compiler agent."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.agents.compiler import (
    CompilationResult,
    CompilerAgent,
    _slugify,
)
from assistonauts.models.schema import ArticleType
from tests.helpers import FakeLLMClient

# --- Fake LLM responses ---

_FAKE_COMPILED_ARTICLE = """\
---
title: Test Concept
type: concept
sources:
  - test-source.md
created_at: 2026-01-01T00:00:00+00:00
compiled_by: compiler
status: draft
---

# Test Concept

## Overview

This is a test concept about machine learning fundamentals.

## Key Concepts

- Neural networks are computing systems inspired by biological neural networks.
- Training involves adjusting weights based on error signals.

## Details

Deep learning uses multiple layers of neural networks to learn representations.

## Related Work

See also: deep-learning, backpropagation.

## Sources

- test-source.md
"""

_FAKE_CONTENT_SUMMARY = """\
A concept article covering machine learning fundamentals including neural networks, \
training processes, and deep learning. Key topics: neural networks, weight adjustment, \
hierarchical representations."""

_FAKE_RECOMPILED_ARTICLE = """\
---
title: Test Concept
type: concept
sources:
  - test-source.md
created_at: 2026-01-01T00:00:00+00:00
compiled_by: compiler
status: draft
---

# Test Concept

## Overview

This is an updated concept about machine learning fundamentals with new information.

## Key Concepts

- Neural networks are computing systems inspired by biological neural networks.
- Training involves adjusting weights based on error signals.
- Attention mechanisms allow selective focus on input parts.

## Details

Deep learning uses multiple layers. Transformer architectures have revolutionized NLP.

## Related Work

See also: deep-learning, backpropagation, transformers.

## Sources

- test-source.md
"""


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with raw source and wiki dirs."""
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    # Create a raw source file
    raw_dir = root / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "test-source.md"
    source.write_text(
        "---\n"
        "source: test-source.md\n"
        "ingested_by: scout\n"
        "category: articles\n"
        "---\n\n"
        "# Machine Learning Basics\n\n"
        "Machine learning is a subset of artificial intelligence.\n"
    )
    return root


class TestSlugify:
    """Test the _slugify helper function."""

    def test_basic_slugify(self) -> None:
        assert _slugify("Machine Learning") == "machine-learning"

    def test_special_characters_removed(self) -> None:
        assert _slugify("What's New?") == "whats-new"

    def test_max_length_enforced(self) -> None:
        long_title = "a" * 100
        result = _slugify(long_title, max_length=20)
        assert len(result) == 20

    def test_empty_string(self) -> None:
        assert _slugify("") == ""

    def test_custom_separator(self) -> None:
        assert _slugify("Hello World", separator="_") == "hello_world"

    def test_unicode_preserved(self) -> None:
        result = _slugify("Résumé of Work")
        assert "résumé" in result


class TestCompilerAgent:
    """Test the Compiler agent compilation pipeline."""

    def test_compile_new_source(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result.success is True
        assert result.output_path is not None
        assert result.output_path.exists()
        assert result.content_summary != ""

    def test_compile_writes_to_wiki(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result.output_path is not None
        content = result.output_path.read_text()
        assert "# Test Concept" in content
        assert "## Overview" in content

    def test_compile_produces_content_summary(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert "machine learning" in result.content_summary.lower()

    def test_compile_persists_summary_to_disk(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result.output_path is not None
        summary_path = result.output_path.with_suffix(".summary.json")
        assert summary_path.exists()
        import json

        data = json.loads(summary_path.read_text())
        assert "summary" in data
        assert len(data["summary"]) > 0
        assert "article_path" in data

    def test_compile_updates_manifest(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        from assistonauts.cache.content import Manifest

        manifest = Manifest(workspace / "index" / "manifest.json")
        # Should have a wiki entry
        keys = list(manifest.entries.keys())
        wiki_keys = [k for k in keys if k.startswith("wiki/")]
        assert len(wiki_keys) > 0

    def test_compile_llm_called_with_source_content(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        # LLM should have been called (compile + summary = 2 calls)
        assert len(llm.calls) == 2
        # First call should include source content in the message
        first_msg = str(llm.calls[0]["messages"])
        assert "Machine Learning Basics" in first_msg

    def test_summary_uses_dedicated_system_prompt(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        # Second call (summary) should use summary system prompt
        summary_call = llm.calls[1]
        assert "summarizer" in str(summary_call["system"]).lower()

    def test_compile_skips_unchanged(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result1 = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result1.success is True
        assert result1.skipped is False

        # Second compile of same source should skip
        result2 = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result2.success is True
        assert result2.skipped is True

    def test_recompile_on_source_change(self, workspace: Path) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_COMPILED_ARTICLE,
                _FAKE_CONTENT_SUMMARY,
                _FAKE_RECOMPILED_ARTICLE,
                _FAKE_CONTENT_SUMMARY,
            ]
        )
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        # First compile
        compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        # Modify source
        source = workspace / "raw" / "articles" / "test-source.md"
        source.write_text(source.read_text() + "\nNew content added.\n")

        # Second compile should recompile (source changed)
        result = compiler.compile(
            source_path=source,
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result.success is True
        assert result.skipped is False

    def test_run_task_delegates_to_compile(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        task = {
            "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
            "article_type": "concept",
            "title": "Test Concept",
        }
        result = compiler.run_task(task)
        assert isinstance(result, CompilationResult)
        assert result.success is True

    def test_run_task_resolves_relative_path_against_workspace(
        self, workspace: Path
    ) -> None:
        """Workspace-relative source paths resolve against workspace_root."""
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        # Pass workspace-relative path (what Captain generates)
        task = {
            "source_path": "raw/articles/test-source.md",
            "article_type": "concept",
            "title": "Test Concept",
        }
        result = compiler.run_task(task)
        assert isinstance(result, CompilationResult)
        assert result.success is True

    def test_run_task_resolves_relative_multi_paths(self, workspace: Path) -> None:
        """Workspace-relative paths in source_paths resolve correctly."""
        # Create a second source file
        second_source = workspace / "raw" / "articles" / "second-source.md"
        second_source.write_text("---\ntitle: Second\nsource: b\n---\nMore content.")

        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        task = {
            "source_paths": "raw/articles/test-source.md,raw/articles/second-source.md",
            "article_type": "concept",
            "title": "Multi Source",
        }
        result = compiler.run_task(task)
        assert isinstance(result, CompilationResult)
        assert result.success is True

    def test_compile_result_has_article_path_under_wiki(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result.output_path is not None
        # Output should be under wiki/
        assert "wiki" in str(result.output_path)

    def test_compile_strips_code_fences(self, workspace: Path) -> None:
        """LLM output wrapped in ```markdown fences should be stripped."""
        fenced_article = "```markdown\n" + _FAKE_COMPILED_ARTICLE + "\n```"
        llm = FakeLLMClient([fenced_article, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = compiler.compile(
            source_path=workspace / "raw" / "articles" / "test-source.md",
            article_type=ArticleType.CONCEPT,
            title="Test Concept",
        )
        assert result.output_path is not None
        content = result.output_path.read_text()
        assert not content.startswith("```")
        assert "---\n" in content  # frontmatter should start clean

    def test_expedition_scope_in_system_prompt(self, workspace: Path) -> None:
        llm = FakeLLMClient([_FAKE_COMPILED_ARTICLE, _FAKE_CONTENT_SUMMARY])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
            expedition_scope="Focus on machine learning algorithms",
        )
        assert "machine learning algorithms" in compiler.system_prompt

    def test_ownership_enforced(self, workspace: Path) -> None:
        from assistonauts.agents.base import OwnershipError

        llm = FakeLLMClient()
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        # Should not be able to write outside wiki/
        with pytest.raises(OwnershipError):
            compiler.write_file(workspace / "raw" / "evil.md", "bad")
