"""Tests for the LLM client wrapper."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from assistonauts.llm.client import LLMClient, LLMResponse


class TestLLMResponse:
    """Test the LLMResponse data class."""

    def test_response_fields(self) -> None:
        """LLMResponse stores content, model, and usage."""
        resp = LLMResponse(
            content="hello",
            model="claude-sonnet-4-20250514",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )
        assert resp.content == "hello"
        assert resp.model == "claude-sonnet-4-20250514"
        assert resp.usage["prompt_tokens"] == 10


class TestReplayMode:
    """Test LLM client in replay mode."""

    def test_replay_returns_recorded_response(self, tmp_path: Path) -> None:
        """Replay mode returns responses from fixture files."""
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()

        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=fixture_dir,
        )

        # Record a fixture manually
        messages = [{"role": "user", "content": "hello"}]
        fixture_key = client._fixture_key(messages, system="test system")
        fixture_file = fixture_dir / f"{fixture_key}.json"
        fixture_file.write_text(
            json.dumps(
                {
                    "content": "replay response",
                    "model": "test-model",
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                }
            )
        )

        resp = client.complete(messages, system="test system")
        assert resp.content == "replay response"
        assert resp.model == "test-model"

    def test_replay_missing_fixture_raises(self, tmp_path: Path) -> None:
        """Replay mode raises FileNotFoundError when fixture is missing."""
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()

        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=fixture_dir,
        )

        with pytest.raises(FileNotFoundError, match="fixture"):
            client.complete(
                [{"role": "user", "content": "no fixture for this"}],
                system="test",
            )

    def test_fixture_key_is_deterministic(self, tmp_path: Path) -> None:
        """Same messages + system produce the same fixture key."""
        client = LLMClient(provider_config={}, mode="replay", fixture_dir=tmp_path)

        messages = [{"role": "user", "content": "test"}]
        key1 = client._fixture_key(messages, system="sys")
        key2 = client._fixture_key(messages, system="sys")
        assert key1 == key2

    def test_fixture_key_differs_by_system(self, tmp_path: Path) -> None:
        """Different system prompts produce different fixture keys."""
        client = LLMClient(provider_config={}, mode="replay", fixture_dir=tmp_path)

        messages = [{"role": "user", "content": "test"}]
        key1 = client._fixture_key(messages, system="sys1")
        key2 = client._fixture_key(messages, system="sys2")
        assert key1 != key2


class TestRecordMode:
    """Test LLM client in record mode."""

    @patch("assistonauts.llm.client._call_litellm")
    def test_record_saves_fixture(
        self, mock_litellm: MagicMock, tmp_path: Path
    ) -> None:
        """Record mode saves the response to a fixture file."""
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()

        mock_litellm.return_value = LLMResponse(
            content="recorded response",
            model="claude-sonnet-4-20250514",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

        client = LLMClient(
            provider_config={},
            mode="record",
            fixture_dir=fixture_dir,
        )

        messages = [{"role": "user", "content": "record this"}]
        resp = client.complete(messages, system="test system")

        assert resp.content == "recorded response"

        # Verify fixture was saved
        fixture_key = client._fixture_key(messages, system="test system")
        fixture_file = fixture_dir / f"{fixture_key}.json"
        assert fixture_file.exists()

        saved = json.loads(fixture_file.read_text())
        assert saved["content"] == "recorded response"

    @patch("assistonauts.llm.client._call_litellm")
    def test_record_calls_litellm(
        self, mock_litellm: MagicMock, tmp_path: Path
    ) -> None:
        """Record mode actually calls litellm."""
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()

        mock_litellm.return_value = LLMResponse(
            content="ok",
            model="test",
            usage={},
        )

        client = LLMClient(
            provider_config={},
            mode="record",
            fixture_dir=fixture_dir,
        )

        client.complete([{"role": "user", "content": "hello"}], system="sys")
        assert mock_litellm.called


class TestLiveMode:
    """Test LLM client in live mode."""

    @patch("assistonauts.llm.client._call_litellm")
    def test_live_calls_litellm(self, mock_litellm: MagicMock) -> None:
        """Live mode calls litellm and returns the response."""
        mock_litellm.return_value = LLMResponse(
            content="live response",
            model="claude-sonnet-4-20250514",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

        client = LLMClient(provider_config={}, mode="live")

        resp = client.complete([{"role": "user", "content": "hello"}], system="test")
        assert resp.content == "live response"
        assert mock_litellm.called

    @patch("assistonauts.llm.client._call_litellm")
    def test_live_does_not_save_fixture(
        self, mock_litellm: MagicMock, tmp_path: Path
    ) -> None:
        """Live mode does not write fixture files."""
        mock_litellm.return_value = LLMResponse(content="ok", model="test", usage={})

        client = LLMClient(
            provider_config={},
            mode="live",
            fixture_dir=tmp_path,
        )

        client.complete([{"role": "user", "content": "hello"}], system="test")

        # No .json files should be created
        json_files = list(tmp_path.glob("*.json"))
        assert len(json_files) == 0


class TestCacheIntegration:
    """Test LLM client with response cache."""

    @patch("assistonauts.llm.client._call_litellm")
    def test_cache_stores_and_returns_responses(
        self, mock_litellm: MagicMock, tmp_path: Path
    ) -> None:
        """Cached responses should be returned without calling litellm."""
        cache_path = tmp_path / "llm_cache.db"

        mock_litellm.return_value = LLMResponse(
            content="cached response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

        client = LLMClient(
            provider_config={},
            mode="live",
            cache_path=cache_path,
        )

        messages = [{"role": "user", "content": "hello cache"}]

        # First call — should hit litellm and store in cache
        resp1 = client.complete(messages, system="test")
        assert resp1.content == "cached response"
        assert mock_litellm.call_count == 1

        # Second call — should return from cache without calling litellm
        resp2 = client.complete(messages, system="test")
        assert resp2.content == "cached response"
        assert mock_litellm.call_count == 1  # Not called again


class TestProviderConfig:
    """Test provider configuration mapping."""

    def test_invalid_mode_raises(self) -> None:
        """Invalid mode raises ValueError."""
        with pytest.raises(ValueError, match="mode"):
            LLMClient(provider_config={}, mode="invalid")

    def test_replay_without_fixture_dir_raises(self) -> None:
        """Replay mode without fixture_dir raises ValueError."""
        with pytest.raises(ValueError, match="fixture_dir"):
            LLMClient(provider_config={}, mode="replay")

    def test_record_without_fixture_dir_raises(self) -> None:
        """Record mode without fixture_dir raises ValueError."""
        with pytest.raises(ValueError, match="fixture_dir"):
            LLMClient(provider_config={}, mode="record")


class TestTokenTracking:
    """Test cumulative token usage tracking."""

    def test_total_tokens_used_initialized_to_zero(self) -> None:
        client = LLMClient(provider_config={})
        assert client.total_tokens_used == 0

    def test_total_tokens_accumulates_on_replay(
        self,
        tmp_path: Path,
    ) -> None:
        """Replay mode tracks tokens from fixture usage data."""
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()

        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=fixture_dir,
        )

        # Create fixture with known usage for a specific message
        messages = [{"role": "user", "content": "hello replay"}]
        key = client._fixture_key(messages, system="sys")
        (fixture_dir / f"{key}.json").write_text(
            json.dumps(
                {
                    "content": "replayed",
                    "model": "test",
                    "usage": {
                        "prompt_tokens": 20,
                        "completion_tokens": 10,
                    },
                }
            ),
        )

        resp = client.complete(messages, system="sys")
        assert resp.content == "replayed"
        assert client.total_tokens_used == 30

    @patch("assistonauts.llm.client._call_litellm")
    def test_total_tokens_accumulates_on_cache_hit(
        self,
        mock_litellm: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Cache hits track tokens from cached usage data."""
        cache_path = tmp_path / "cache.db"
        mock_litellm.return_value = LLMResponse(
            content="cached",
            model="test",
            usage={"prompt_tokens": 40, "completion_tokens": 20},
        )

        client = LLMClient(
            provider_config={},
            mode="live",
            cache_path=cache_path,
        )

        messages = [{"role": "user", "content": "cache test"}]
        # First call: live (tokens tracked)
        client.complete(messages, system="sys")
        assert client.total_tokens_used == 60

        # Second call: cache hit (tokens should also be tracked)
        client.complete(messages, system="sys")
        assert client.total_tokens_used == 120

    @patch("assistonauts.llm.client._call_litellm")
    def test_total_tokens_accumulates_on_live(
        self,
        mock_litellm: MagicMock,
    ) -> None:
        mock_litellm.return_value = LLMResponse(
            content="test",
            model="test-model",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

        client = LLMClient(provider_config={}, mode="live")
        client.complete([{"role": "user", "content": "hello"}])
        assert client.total_tokens_used == 150

        client.complete([{"role": "user", "content": "world"}])
        assert client.total_tokens_used == 300
