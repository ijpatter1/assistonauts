"""Tests for Compiler plan mode — editorial triage for compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.agents.compiler import CompilationPlan, CompilerAgent
from assistonauts.models.schema import ArticleType
from tests.helpers import FakeLLMClient

_PLAN_YAML_RESPONSE = """\
articles:
  - title: "Introduction"
    type: concept
    sources:
      - page-008-009.md
      - page-010-011.md
      - page-012-013.md
    rationale: "These pages form the book's introduction section."
  - title: "Theres Treasure Inside by Jon Collins-Black"
    type: entity
    sources:
      - cover.md
    rationale: "Cover page with book metadata."
  - title: "Publication and Dedication"
    type: log
    sources:
      - front-01-02.md
    rationale: "Copyright, dedication, and publishing details."
"""

_PLAN_SINGLE_ARTICLE = """\
articles:
  - title: "Chapter 1"
    type: concept
    sources:
      - source.md
    rationale: "Single source document."
"""

_PLAN_GARBLED = """\
This is not valid YAML at all {{{
some random LLM output that didn't follow instructions
"""


@pytest.fixture
def workspace(initialized_workspace: Path) -> Path:
    return initialized_workspace


def _write_source(workspace: Path, name: str, content: str) -> Path:
    path = workspace / "raw" / "articles" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


class TestCompilerPlan:
    """Test Compiler plan mode — editorial triage."""

    def test_plan_returns_compilation_plan(self, workspace: Path) -> None:
        # Provide all sources referenced in _PLAN_YAML_RESPONSE
        src1 = _write_source(workspace, "page-008-009.md", "Intro page 1.")
        src2 = _write_source(workspace, "page-010-011.md", "Intro page 2.")
        src3 = _write_source(workspace, "page-012-013.md", "Intro page 3.")
        src4 = _write_source(workspace, "cover.md", "Book cover.")
        src5 = _write_source(workspace, "front-01-02.md", "Front matter.")

        llm = FakeLLMClient(responses=[_PLAN_YAML_RESPONSE])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        plan = compiler.plan([src1, src2, src3, src4, src5])
        assert isinstance(plan, CompilationPlan)
        assert len(plan.articles) == 3

    def test_plan_article_fields(self, workspace: Path) -> None:
        src = _write_source(workspace, "page-008-009.md", "Content.")

        llm = FakeLLMClient(responses=[_PLAN_YAML_RESPONSE])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        plan = compiler.plan([src])
        article = plan.articles[0]
        assert article.title == "Introduction"
        assert article.article_type == ArticleType.CONCEPT
        assert len(article.source_paths) > 0
        assert article.rationale != ""

    def test_plan_maps_source_names_to_paths(self, workspace: Path) -> None:
        """Source filenames in LLM response are resolved to full paths."""
        src1 = _write_source(workspace, "page-008-009.md", "Content 1.")
        src2 = _write_source(workspace, "page-010-011.md", "Content 2.")
        src3 = _write_source(workspace, "page-012-013.md", "Content 3.")
        src4 = _write_source(workspace, "cover.md", "Cover.")
        src5 = _write_source(workspace, "front-01-02.md", "Front.")

        llm = FakeLLMClient(responses=[_PLAN_YAML_RESPONSE])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        plan = compiler.plan([src1, src2, src3, src4, src5])
        intro = plan.articles[0]
        # Should have resolved the filenames to actual paths
        assert all(isinstance(p, Path) for p in intro.source_paths)
        assert len(intro.source_paths) == 3

    def test_plan_sends_source_content_to_llm(self, workspace: Path) -> None:
        src = _write_source(workspace, "test.md", "Unique content here.")

        llm = FakeLLMClient(responses=[_PLAN_SINGLE_ARTICLE])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        compiler.plan([src])
        assert len(llm.calls) == 1
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "Unique content here" in prompt

    def test_plan_includes_schema_info(self, workspace: Path) -> None:
        src = _write_source(workspace, "test.md", "Content.")

        llm = FakeLLMClient(responses=[_PLAN_SINGLE_ARTICLE])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        compiler.plan([src])
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "concept" in prompt
        assert "entity" in prompt
        assert "log" in prompt

    def test_plan_includes_expedition_scope(self, workspace: Path) -> None:
        src = _write_source(workspace, "test.md", "Content.")

        llm = FakeLLMClient(responses=[_PLAN_SINGLE_ARTICLE])
        compiler = CompilerAgent(
            llm_client=llm,
            workspace_root=workspace,
            expedition_scope="Treasure hunting books",
        )

        compiler.plan([src])
        prompt = llm.calls[0]["messages"][0]["content"]
        assert "Treasure hunting books" in prompt

    def test_plan_fallback_on_parse_error(self, workspace: Path) -> None:
        """Garbled LLM output → one article per source fallback."""
        src1 = _write_source(workspace, "a.md", "Content A.")
        src2 = _write_source(workspace, "b.md", "Content B.")

        llm = FakeLLMClient(responses=[_PLAN_GARBLED])
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        plan = compiler.plan([src1, src2])
        # Fallback: one article per source, all concept type
        assert len(plan.articles) == 2
        assert all(a.article_type == ArticleType.CONCEPT for a in plan.articles)

    def test_plan_empty_sources(self, workspace: Path) -> None:
        llm = FakeLLMClient()
        compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)

        plan = compiler.plan([])
        assert len(plan.articles) == 0
        # Should not have called LLM
        assert len(llm.calls) == 0


class TestCompilationPlanPersistence:
    """Test plan artifact persistence."""

    def test_save_creates_yaml_file(self, workspace: Path) -> None:
        from assistonauts.agents.compiler import CompilationPlan, PlannedArticle

        plan = CompilationPlan(
            articles=[
                PlannedArticle(
                    title="Test Article",
                    article_type=ArticleType.CONCEPT,
                    source_paths=[workspace / "raw/articles/test.md"],
                    rationale="Test rationale.",
                ),
            ]
        )
        plans_dir = workspace / ".assistonauts" / "plans"
        path = plan.save(plans_dir)
        assert path.exists()
        assert path.suffix == ".yaml"
        assert plans_dir.exists()

    def test_save_contains_article_data(self, workspace: Path) -> None:
        import yaml as pyyaml

        from assistonauts.agents.compiler import CompilationPlan, PlannedArticle

        plan = CompilationPlan(
            articles=[
                PlannedArticle(
                    title="My Article",
                    article_type=ArticleType.ENTITY,
                    source_paths=[workspace / "raw/articles/a.md"],
                    rationale="Some reason.",
                ),
            ]
        )
        path = plan.save(workspace / ".assistonauts" / "plans")
        data = pyyaml.safe_load(path.read_text())
        assert data["article_count"] == 1
        assert data["articles"][0]["title"] == "My Article"
        assert data["articles"][0]["type"] == "entity"
        assert "created_at" in data


class TestCompilerPlanCLI:
    """Test CLI for plan mode."""

    def test_plan_command_exists(self, workspace: Path) -> None:
        from click.testing import CliRunner

        from assistonauts.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["plan", "--help"])
        assert result.exit_code == 0
        assert "plan" in result.output.lower()
