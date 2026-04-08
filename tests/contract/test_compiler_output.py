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

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "compiler"


class FixtureLLMClient:
    """LLM client that returns responses from fixture files in sequence."""

    def __init__(self, fixture_names: list[str]) -> None:
        self._responses: list[str] = []
        for name in fixture_names:
            fixture_path = _FIXTURES_DIR / f"{name}.json"
            data = json.loads(fixture_path.read_text())
            self._responses.append(data["content"])
        self._call_count = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FixtureResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return FixtureResponse(self._responses[idx])


class FixtureResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fixture-model"
        self.usage = {"prompt_tokens": 100, "completion_tokens": 200}


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


class TestCompiledArticleFrontmatter:
    """Validate frontmatter structure of compiled articles."""

    def test_article_has_yaml_frontmatter(
        self, compiled_result, workspace: Path
    ) -> None:
        assert compiled_result.output_path is not None
        content = compiled_result.output_path.read_text()
        assert content.startswith("---\n")
        # Find closing delimiter
        end = content.find("---", 3)
        assert end > 3, "No closing frontmatter delimiter"

    def test_frontmatter_has_title(self, compiled_result, workspace: Path) -> None:
        content = compiled_result.output_path.read_text()
        fm = _extract_frontmatter(content)
        assert "title" in fm
        assert isinstance(fm["title"], str)
        assert len(fm["title"]) > 0

    def test_frontmatter_has_type(self, compiled_result, workspace: Path) -> None:
        content = compiled_result.output_path.read_text()
        fm = _extract_frontmatter(content)
        assert "type" in fm
        valid_types = {t.value for t in ArticleType}
        assert fm["type"] in valid_types

    def test_frontmatter_has_sources(self, compiled_result, workspace: Path) -> None:
        content = compiled_result.output_path.read_text()
        fm = _extract_frontmatter(content)
        assert "sources" in fm
        assert isinstance(fm["sources"], list)
        assert len(fm["sources"]) > 0

    def test_frontmatter_has_created_at(self, compiled_result, workspace: Path) -> None:
        content = compiled_result.output_path.read_text()
        fm = _extract_frontmatter(content)
        assert "created_at" in fm

    def test_frontmatter_has_status(self, compiled_result, workspace: Path) -> None:
        content = compiled_result.output_path.read_text()
        fm = _extract_frontmatter(content)
        assert "status" in fm


class TestCompiledArticleSections:
    """Validate section structure of compiled articles."""

    def test_has_h1_title(self, compiled_result, workspace: Path) -> None:
        content = compiled_result.output_path.read_text()
        body = _extract_body(content)
        lines = body.split("\n")
        h1_lines = [line for line in lines if line.startswith("# ")]
        assert len(h1_lines) >= 1

    def test_concept_has_required_sections(
        self, compiled_result, workspace: Path
    ) -> None:
        content = compiled_result.output_path.read_text()
        body = _extract_body(content)
        schema = get_default_schema()
        template = schema.get_template(ArticleType.CONCEPT)
        required_headings = [s.heading for s in template.sections if s.required]
        for heading in required_headings:
            assert f"## {heading}" in body, f"Missing required section: {heading}"

    def test_sources_section_has_citations(
        self, compiled_result, workspace: Path
    ) -> None:
        content = compiled_result.output_path.read_text()
        body = _extract_body(content)
        # Find Sources section
        sources_idx = body.find("## Sources")
        assert sources_idx >= 0, "No Sources section found"
        sources_section = body[sources_idx:]
        # Should contain at least one source reference
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
