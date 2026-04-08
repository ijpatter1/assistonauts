"""Tests for Bug 2: index() should load summaries from .summary.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistonauts.archivist.service import Archivist


@pytest.fixture
def workspace(initialized_workspace: Path) -> Path:
    return initialized_workspace


@pytest.fixture
def archivist(workspace: Path) -> Archivist:
    return Archivist(workspace, embedding_dimensions=4)


_ARTICLE = """\
---
title: Test Article
type: concept
sources:
  - source.md
---

# Test Article

Some content about testing.
"""


class TestIndexLoadsSummaries:
    """Bug 2: index() should load summaries from .summary.json files."""

    def test_index_loads_summary_json(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        """When a .summary.json exists alongside an article, index() should load it."""
        # Write article
        article_path = workspace / "wiki" / "concept" / "test-article.md"
        article_path.parent.mkdir(parents=True, exist_ok=True)
        article_path.write_text(_ARTICLE)

        # Write summary JSON
        summary_path = article_path.with_suffix(".summary.json")
        summary_data = {
            "summary": "A test article about testing concepts.",
            "article_path": "wiki/concept/test-article.md",
            "manifest_key": "wiki/concept/test-article.md",
            "generated_at": "2026-01-01T00:00:00+00:00",
        }
        summary_path.write_text(json.dumps(summary_data))

        # Index the article
        changed = archivist.index("wiki/concept/test-article.md")
        assert changed is True

        # Verify the summary was loaded into the DB
        summary = archivist.db.get_summary("wiki/concept/test-article.md")
        assert summary is not None
        assert "testing concepts" in str(summary["content_summary"])

    def test_index_works_without_summary_json(
        self, archivist: Archivist, workspace: Path
    ) -> None:
        """index() should still work when no .summary.json exists."""
        article_path = workspace / "wiki" / "concept" / "no-summary.md"
        article_path.parent.mkdir(parents=True, exist_ok=True)
        article_path.write_text(_ARTICLE)

        changed = archivist.index("wiki/concept/no-summary.md")
        assert changed is True

        # No summary should be stored
        summary = archivist.db.get_summary("wiki/concept/no-summary.md")
        assert summary is None
