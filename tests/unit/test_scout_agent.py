"""Tests for the Scout agent."""

from pathlib import Path

from assistonauts.agents.scout import ScoutAgent
from assistonauts.cache.content import Manifest


class FakeResponse:
    """Minimal fake LLM response."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fake"
        self.usage = {"prompt_tokens": 5, "completion_tokens": 3}


class FakeLLMClient:
    """Fake LLM client for testing."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ["relevant"])
        self._idx = 0
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FakeResponse:
        self.calls.append({"messages": messages, "system": system})
        idx = min(self._idx, len(self._responses) - 1)
        self._idx += 1
        return FakeResponse(self._responses[idx])


class TestScoutAgentCreation:
    """Test Scout agent construction."""

    def test_creates_with_correct_role(self, tmp_path: Path) -> None:
        """Scout agent has role 'scout'."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=tmp_path,
        )
        assert agent.role == "scout"

    def test_owns_raw_directory(self, tmp_path: Path) -> None:
        """Scout agent owns the raw/ directory."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=tmp_path,
        )
        assert any(str(d).endswith("raw") for d in agent.owned_dirs)

    def test_has_toolkit_functions(self, tmp_path: Path) -> None:
        """Scout agent registers toolkit functions."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=tmp_path,
        )
        assert "hash_content" in agent.toolkit
        assert "check_relevance_keywords" in agent.toolkit
        assert "convert_text_file" in agent.toolkit


class TestScoutIngest:
    """Test the Scout ingestion pipeline."""

    def _setup_workspace(self, tmp_path: Path) -> Path:
        """Create a minimal workspace structure."""
        (tmp_path / "raw" / "papers").mkdir(parents=True)
        (tmp_path / "raw" / "articles").mkdir(parents=True)
        (tmp_path / "index").mkdir(parents=True)
        (tmp_path / "index" / "manifest.json").write_text("{}\n")
        return tmp_path

    def test_ingest_text_file(self, tmp_path: Path) -> None:
        """Ingesting a text file copies it to raw/."""
        ws = self._setup_workspace(tmp_path)
        source = tmp_path / "input.txt"
        source.write_text("# Research Paper\n\nSome findings here.")

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
        )

        result = agent.ingest(source)
        assert result.success is True
        assert result.output_path is not None
        assert result.output_path.exists()
        assert "Research Paper" in result.output_path.read_text()

    def test_ingest_markdown_file(self, tmp_path: Path) -> None:
        """Ingesting a markdown file copies it to raw/."""
        ws = self._setup_workspace(tmp_path)
        source = tmp_path / "paper.md"
        source.write_text("# ML Paper\n\n## Abstract\n\nContent here.")

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
        )

        result = agent.ingest(source)
        assert result.success is True
        assert result.output_path is not None
        assert "ML Paper" in result.output_path.read_text()

    def test_ingest_updates_manifest(self, tmp_path: Path) -> None:
        """Ingesting a file adds an entry to the manifest."""
        ws = self._setup_workspace(tmp_path)
        source = tmp_path / "doc.txt"
        source.write_text("content to track")

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
        )

        result = agent.ingest(source)
        assert result.success is True

        manifest = Manifest(ws / "index" / "manifest.json")
        assert manifest.get(str(result.manifest_key)) is not None

    def test_ingest_skips_unchanged_file(self, tmp_path: Path) -> None:
        """Ingesting the same file twice skips on the second run."""
        ws = self._setup_workspace(tmp_path)
        source = tmp_path / "stable.txt"
        source.write_text("stable content")

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
        )

        result1 = agent.ingest(source)
        assert result1.success is True
        assert result1.skipped is False

        result2 = agent.ingest(source)
        assert result2.success is True
        assert result2.skipped is True

    def test_ingest_with_category(self, tmp_path: Path) -> None:
        """Ingesting with a category places file in raw/<category>/."""
        ws = self._setup_workspace(tmp_path)
        source = tmp_path / "paper.md"
        source.write_text("# Paper content")

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
        )

        result = agent.ingest(source, category="papers")
        assert result.success is True
        assert result.output_path is not None
        assert "papers" in str(result.output_path)

    def test_ingest_adds_frontmatter(self, tmp_path: Path) -> None:
        """Ingested files get frontmatter with source metadata."""
        ws = self._setup_workspace(tmp_path)
        source = tmp_path / "doc.txt"
        source.write_text("Some document content.")

        agent = ScoutAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
        )

        result = agent.ingest(source)
        assert result.success is True
        assert result.output_path is not None

        content = result.output_path.read_text()
        assert content.startswith("---\n")
        assert "source:" in content
        assert "ingested_by: scout" in content
