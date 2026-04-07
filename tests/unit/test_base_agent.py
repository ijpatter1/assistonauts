"""Tests for the base agent class."""

from pathlib import Path

import pytest

from assistonauts.agents.base import Agent, OwnershipError


class FakeResponse:
    """Minimal fake LLM response for testing."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fake-model"
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5}


class FakeLLMClient:
    """Fake LLM client that returns canned responses."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ["default response"])
        self._call_count = 0
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FakeResponse:
        self.calls.append({"messages": messages, "model": model, "system": system})
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return FakeResponse(self._responses[idx])


class TestAgentConstruction:
    """Test agent creation and field assignment."""

    def test_create_agent(self, tmp_workspace: Path) -> None:
        """Agent can be created with required fields."""
        owned = [tmp_workspace / "raw"]
        readable = [tmp_workspace / "wiki"]
        owned[0].mkdir(parents=True)
        readable[0].mkdir(parents=True)

        agent = Agent(
            role="scout",
            system_prompt="You are a scout agent.",
            llm_client=FakeLLMClient(),
            owned_dirs=owned,
            readable_dirs=readable,
        )

        assert agent.role == "scout"
        assert agent.system_prompt == "You are a scout agent."
        assert len(agent.owned_dirs) == 1
        assert len(agent.readable_dirs) == 1

    def test_toolkit_registration(self, tmp_workspace: Path) -> None:
        """Agent can register and retrieve toolkit functions."""

        def my_tool(text: str) -> str:
            return text.upper()

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[],
            readable_dirs=[],
            toolkit={"my_tool": my_tool},
        )

        assert "my_tool" in agent.toolkit
        assert agent.toolkit["my_tool"]("hello") == "HELLO"

    def test_default_toolkit_is_empty(self, tmp_workspace: Path) -> None:
        """Default toolkit is an empty dict."""
        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[],
            readable_dirs=[],
        )
        assert agent.toolkit == {}


class TestOwnershipEnforcement:
    """Test read/write boundary enforcement."""

    def test_write_to_owned_dir(self, tmp_workspace: Path) -> None:
        """Agent can write files in owned directories."""
        owned = tmp_workspace / "raw"
        owned.mkdir(parents=True)

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[owned],
            readable_dirs=[],
        )

        target = owned / "test.md"
        agent.write_file(target, "hello")
        assert target.read_text() == "hello"

    def test_write_to_owned_subdir(self, tmp_workspace: Path) -> None:
        """Agent can write to subdirectories of owned dirs."""
        owned = tmp_workspace / "raw"
        sub = owned / "papers"
        sub.mkdir(parents=True)

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[owned],
            readable_dirs=[],
        )

        target = sub / "paper.md"
        agent.write_file(target, "content")
        assert target.read_text() == "content"

    def test_write_outside_owned_raises(self, tmp_workspace: Path) -> None:
        """Agent cannot write outside owned directories."""
        owned = tmp_workspace / "raw"
        owned.mkdir(parents=True)
        forbidden = tmp_workspace / "wiki"
        forbidden.mkdir(parents=True)

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[owned],
            readable_dirs=[forbidden],
        )

        with pytest.raises(OwnershipError, match="scout"):
            agent.write_file(forbidden / "bad.md", "nope")

    def test_read_from_readable_dir(self, tmp_workspace: Path) -> None:
        """Agent can read files in readable directories."""
        readable = tmp_workspace / "wiki"
        readable.mkdir(parents=True)
        (readable / "article.md").write_text("article content")

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[],
            readable_dirs=[readable],
        )

        content = agent.read_file(readable / "article.md")
        assert content == "article content"

    def test_read_from_owned_dir(self, tmp_workspace: Path) -> None:
        """Agent can also read files in owned directories."""
        owned = tmp_workspace / "raw"
        owned.mkdir(parents=True)
        (owned / "source.md").write_text("source content")

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[owned],
            readable_dirs=[],
        )

        content = agent.read_file(owned / "source.md")
        assert content == "source content"

    def test_read_outside_allowed_raises(self, tmp_workspace: Path) -> None:
        """Agent cannot read outside owned+readable directories."""
        owned = tmp_workspace / "raw"
        owned.mkdir(parents=True)
        forbidden = tmp_workspace / "secret"
        forbidden.mkdir(parents=True)
        (forbidden / "data.txt").write_text("secret")

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[owned],
            readable_dirs=[],
        )

        with pytest.raises(OwnershipError, match="scout"):
            agent.read_file(forbidden / "data.txt")


class TestLLMCalls:
    """Test LLM client integration."""

    def test_call_llm_returns_content(self, tmp_workspace: Path) -> None:
        """call_llm returns the response content string."""
        client = FakeLLMClient(["test response"])

        agent = Agent(
            role="scout",
            system_prompt="You are a scout.",
            llm_client=client,
            owned_dirs=[],
            readable_dirs=[],
        )

        result = agent.call_llm([{"role": "user", "content": "hello"}])
        assert result == "test response"

    def test_call_llm_passes_system_prompt(self, tmp_workspace: Path) -> None:
        """call_llm passes the agent's system prompt to the client."""
        client = FakeLLMClient(["ok"])

        agent = Agent(
            role="scout",
            system_prompt="You are a scout.",
            llm_client=client,
            owned_dirs=[],
            readable_dirs=[],
        )

        agent.call_llm([{"role": "user", "content": "hello"}])
        assert client.calls[0]["system"] == "You are a scout."

    def test_call_llm_records_calls(self, tmp_workspace: Path) -> None:
        """Each call_llm invocation is recorded on the client."""
        client = FakeLLMClient(["r1", "r2"])

        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=client,
            owned_dirs=[],
            readable_dirs=[],
        )

        agent.call_llm([{"role": "user", "content": "first"}])
        agent.call_llm([{"role": "user", "content": "second"}])

        assert len(client.calls) == 2


class TestRunMission:
    """Test that base agent run_mission raises NotImplementedError."""

    def test_run_mission_not_implemented(self, tmp_workspace: Path) -> None:
        """Base agent.run_mission raises NotImplementedError."""
        agent = Agent(
            role="scout",
            system_prompt="Test",
            llm_client=FakeLLMClient(),
            owned_dirs=[],
            readable_dirs=[],
        )

        with pytest.raises(NotImplementedError):
            agent.run_mission({})  # type: ignore[arg-type]
