"""Contract tests for Compiler agent output structure.

These tests validate the structural contracts of compiled wiki articles:
- Valid YAML frontmatter with required fields
- Schema-conformant section headings
- Content summary present and non-empty
- Source citations included

Uses recorded LLM fixtures for deterministic, fast execution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from assistonauts.agents.compiler import CompilerAgent
from assistonauts.models.schema import ArticleType, get_default_schema
from tests.helpers import FakeLLMClient

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "compiler"


class FixtureLLMClient(FakeLLMClient):
    """LLM client that loads responses from fixture files on disk."""

    def __init__(self, fixture_names: list[str]) -> None:
        responses: list[str] = []
        for name in fixture_names:
            fixture_path = _FIXTURES_DIR / f"{name}.json"
            data = json.loads(fixture_path.read_text())
            responses.append(data["content"])
        super().__init__(responses=responses)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Create workspace with a raw source file."""
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    raw_dir = root / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "ml-basics.md"
    source.write_text(
        "---\n"
        "source: ml-basics.md\n"
        "ingested_by: scout\n"
        "category: articles\n"
        "---\n\n"
        "# Machine Learning Basics\n\n"
        "Machine learning is a branch of artificial intelligence.\n"
        "It focuses on building systems that learn from data.\n"
    )
    return root


@pytest.fixture
def compiled_result(workspace: Path):
    """Compile a source and return the result."""
    llm = FixtureLLMClient(["compile_concept", "compile_summary"])
    compiler = CompilerAgent(llm_client=llm, workspace_root=workspace)
    return compiler.compile(
        source_path=workspace / "raw" / "articles" / "ml-basics.md",
        article_type=ArticleType.CONCEPT,
        title="Machine Learning Fundamentals",
    )


@pytest.fixture
def compiled_content(compiled_result) -> str:
    """Read the compiled article content once for all tests."""
    assert compiled_result.output_path is not None
    return compiled_result.output_path.read_text()


@pytest.fixture
def compiled_frontmatter(compiled_content: str) -> dict[str, object]:
    """Parse frontmatter from the compiled article."""
    return _extract_frontmatter(compiled_content)


@pytest.fixture
def compiled_body(compiled_content: str) -> str:
    """Extract body (after frontmatter) from the compiled article."""
    return _extract_body(compiled_content)


class TestCompiledArticleFrontmatter:
    """Validate frontmatter structure of compiled articles."""

    def test_article_has_yaml_frontmatter(self, compiled_content: str) -> None:
        assert compiled_content.startswith("---\n")
        end = compiled_content.find("---", 3)
        assert end > 3, "No closing frontmatter delimiter"

    def test_frontmatter_has_title(
        self, compiled_frontmatter: dict[str, object]
    ) -> None:
        assert "title" in compiled_frontmatter
        assert isinstance(compiled_frontmatter["title"], str)
        assert len(compiled_frontmatter["title"]) > 0

    def test_frontmatter_has_type(
        self, compiled_frontmatter: dict[str, object]
    ) -> None:
        assert "type" in compiled_frontmatter
        valid_types = {t.value for t in ArticleType}
        assert compiled_frontmatter["type"] in valid_types

    def test_frontmatter_has_sources(
        self, compiled_frontmatter: dict[str, object]
    ) -> None:
        assert "sources" in compiled_frontmatter
        assert isinstance(compiled_frontmatter["sources"], list)
        assert len(compiled_frontmatter["sources"]) > 0

    def test_frontmatter_has_created_at(
        self, compiled_frontmatter: dict[str, object]
    ) -> None:
        assert "created_at" in compiled_frontmatter

    def test_frontmatter_has_status(
        self, compiled_frontmatter: dict[str, object]
    ) -> None:
        assert "status" in compiled_frontmatter


class TestCompiledArticleSections:
    """Validate section structure of compiled articles."""

    def test_has_h1_title(self, compiled_body: str) -> None:
        lines = compiled_body.split("\n")
        h1_lines = [line for line in lines if line.startswith("# ")]
        assert len(h1_lines) >= 1

    def test_concept_has_required_sections(self, compiled_body: str) -> None:
        schema = get_default_schema()
        template = schema.get_template(ArticleType.CONCEPT)
        required_headings = [s.heading for s in template.sections if s.required]
        for heading in required_headings:
            assert f"## {heading}" in compiled_body, (
                f"Missing required section: {heading}"
            )

    def test_sources_section_has_citations(self, compiled_body: str) -> None:
        sources_idx = compiled_body.find("## Sources")
        assert sources_idx >= 0, "No Sources section found"
        sources_section = compiled_body[sources_idx:]
        assert "ml-basics.md" in sources_section


class TestContentSummary:
    """Validate content summary generation."""

    def test_content_summary_present(self, compiled_result) -> None:
        assert compiled_result.content_summary != ""

    def test_content_summary_is_concise(self, compiled_result) -> None:
        # Summary should be 1-4 sentences, roughly under 500 chars
        assert len(compiled_result.content_summary) < 500

    def test_content_summary_mentions_topic(self, compiled_result) -> None:
        summary_lower = compiled_result.content_summary.lower()
        assert "machine learning" in summary_lower


class TestCompilationResult:
    """Validate the compilation result object."""

    def test_result_success(self, compiled_result) -> None:
        assert compiled_result.success is True

    def test_result_not_skipped(self, compiled_result) -> None:
        assert compiled_result.skipped is False

    def test_output_path_under_wiki(self, compiled_result) -> None:
        assert compiled_result.output_path is not None
        assert "wiki" in str(compiled_result.output_path)

    def test_manifest_key_format(self, compiled_result) -> None:
        assert compiled_result.manifest_key.startswith("wiki/")
        assert compiled_result.manifest_key.endswith(".md")


# --- Helpers ---


def _extract_frontmatter(content: str) -> dict[str, object]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---\n"):
        return {}
    end = content.find("---", 3)
    if end < 0:
        return {}
    fm_text = content[4:end]
    return yaml.safe_load(fm_text) or {}


def _extract_body(content: str) -> str:
    """Extract body (after frontmatter) from markdown content."""
    if not content.startswith("---\n"):
        return content
    end = content.find("---", 3)
    if end < 0:
        return content
    return content[end + 3 :].strip()
