"""Contract tests for Scout agent output structure.

These tests validate the structural contract of Scout output:
- Valid YAML frontmatter present
- Required frontmatter fields
- Content is valid markdown
- Assets referenced correctly (when applicable)
"""

from pathlib import Path

import yaml

from assistonauts.agents.scout import ScoutAgent
from tests.conftest import FakeLLMClient


def _setup_workspace(tmp_path: Path) -> Path:
    """Create a workspace with required directories."""
    (tmp_path / "raw" / "papers").mkdir(parents=True)
    (tmp_path / "raw" / "articles").mkdir(parents=True)
    (tmp_path / "index").mkdir(parents=True)
    (tmp_path / "index" / "manifest.json").write_text("{}\n")
    return tmp_path


class TestScoutOutputContract:
    """Contract tests: Scout output must conform to structural requirements."""

    def test_output_has_yaml_frontmatter(self, tmp_path: Path) -> None:
        """Scout output starts with valid YAML frontmatter delimiters."""
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "input.md"
        source.write_text("# Test Document\n\nContent here.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.output_path is not None
        content = result.output_path.read_text()

        # Must start with --- and have closing ---
        lines = content.split("\n")
        assert lines[0] == "---"
        # Find closing delimiter
        closing_idx = None
        for i, line in enumerate(lines[1:], start=1):
            if line == "---":
                closing_idx = i
                break
        assert closing_idx is not None, "No closing frontmatter delimiter"

    def test_frontmatter_has_required_fields(self, tmp_path: Path) -> None:
        """Scout frontmatter contains all required metadata fields."""
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "paper.md"
        source.write_text("# ML Paper\n\nAbstract content.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.output_path is not None
        content = result.output_path.read_text()

        # Parse frontmatter
        parts = content.split("---\n", 2)
        assert len(parts) >= 3, "Frontmatter not properly delimited"
        frontmatter = yaml.safe_load(parts[1])

        required_fields = [
            "source",
            "source_path",
            "ingested_by",
            "ingested_at",
            "category",
        ]
        for field in required_fields:
            assert field in frontmatter, f"Missing required field: {field}"

    def test_frontmatter_ingested_by_is_scout(self, tmp_path: Path) -> None:
        """Frontmatter ingested_by field is 'scout'."""
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "doc.txt"
        source.write_text("Document content.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.output_path is not None
        content = result.output_path.read_text()
        parts = content.split("---\n", 2)
        frontmatter = yaml.safe_load(parts[1])
        assert frontmatter["ingested_by"] == "scout"

    def test_output_contains_source_content(self, tmp_path: Path) -> None:
        """Scout output preserves the original source content after frontmatter."""
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "article.md"
        source.write_text("# Important Findings\n\nKey result: 42.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.output_path is not None
        content = result.output_path.read_text()

        # Content after frontmatter should contain original text
        parts = content.split("---\n", 2)
        body = parts[2]
        assert "Important Findings" in body
        assert "Key result: 42." in body

    def test_output_is_markdown_file(self, tmp_path: Path) -> None:
        """Scout output file has .md extension."""
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "notes.txt"
        source.write_text("Some notes.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.output_path is not None
        assert result.output_path.suffix == ".md"

    def test_output_in_raw_directory(self, tmp_path: Path) -> None:
        """Scout output is placed within the raw/ directory."""
        ws = _setup_workspace(tmp_path)
        source = tmp_path / "data.txt"
        source.write_text("Data content.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        result = agent.ingest(source)

        assert result.output_path is not None
        assert "raw" in result.output_path.parts
