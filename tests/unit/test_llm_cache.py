"""Tests for the LLM response cache (SQLite backend)."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.cache.llm_cache import LLMResponseCache


@pytest.fixture
def cache(tmp_path: Path) -> LLMResponseCache:
    return LLMResponseCache(tmp_path / "cache" / "llm_cache.db")


class TestLLMCacheBasics:
    """Test basic cache operations."""

    def test_cache_miss(self, cache: LLMResponseCache) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        result = cache.get("model", "system prompt", msgs)
        assert result is None

    def test_cache_hit(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hello"}]
        cache.put("model", "system", messages, "response text", {"prompt_tokens": 10})
        result = cache.get("model", "system", messages)
        assert result is not None
        assert result["content"] == "response text"
        assert result["usage"]["prompt_tokens"] == 10

    def test_same_key_different_model(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hello"}]
        cache.put("model-a", "sys", messages, "response a", {})
        cache.put("model-b", "sys", messages, "response b", {})
        assert cache.get("model-a", "sys", messages)["content"] == "response a"
        assert cache.get("model-b", "sys", messages)["content"] == "response b"

    def test_same_key_different_system(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hello"}]
        cache.put("model", "sys-a", messages, "response a", {})
        cache.put("model", "sys-b", messages, "response b", {})
        assert cache.get("model", "sys-a", messages)["content"] == "response a"
        assert cache.get("model", "sys-b", messages)["content"] == "response b"


class TestLLMCacheTTL:
    """Test TTL expiration."""

    def test_expired_entry_returns_none(self, tmp_path: Path) -> None:
        cache = LLMResponseCache(tmp_path / "cache.db", ttl_seconds=1)
        messages = [{"role": "user", "content": "hi"}]
        cache.put("model", "sys", messages, "response", {})
        # Manually set created_at to the past
        cache._conn.execute(
            "UPDATE llm_cache SET created_at = datetime('now', '-2 seconds')"
        )
        cache._conn.commit()
        assert cache.get("model", "sys", messages) is None

    def test_non_expired_entry_returns_value(self, tmp_path: Path) -> None:
        cache = LLMResponseCache(tmp_path / "cache.db", ttl_seconds=3600)
        messages = [{"role": "user", "content": "hi"}]
        cache.put("model", "sys", messages, "response", {})
        assert cache.get("model", "sys", messages) is not None


class TestLLMCacheFlush:
    """Test cache flush operations."""

    def test_flush_all(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hi"}]
        cache.put("model", "sys", messages, "response", {}, agent="scout")
        cache.flush()
        assert cache.get("model", "sys", messages) is None

    def test_flush_by_agent(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hi"}]
        cache.put("model", "sys", messages, "scout resp", {}, agent="scout")
        cache.put("model", "sys2", messages, "compiler resp", {}, agent="compiler")
        cache.flush(agent="scout")
        assert cache.get("model", "sys", messages) is None
        assert cache.get("model", "sys2", messages) is not None

    def test_flush_by_expedition(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hi"}]
        cache.put(
            "model",
            "sys",
            messages,
            "resp1",
            {},
            expedition="autotrader",
        )
        cache.put(
            "model",
            "sys2",
            messages,
            "resp2",
            {},
            expedition="other",
        )
        cache.flush(expedition="autotrader")
        assert cache.get("model", "sys", messages) is None
        assert cache.get("model", "sys2", messages) is not None


class TestLLMCacheStats:
    """Test cache statistics."""

    def test_stats_empty(self, cache: LLMResponseCache) -> None:
        stats = cache.stats()
        assert stats["total_entries"] == 0
        assert stats["total_size_bytes"] >= 0

    def test_stats_with_entries(self, cache: LLMResponseCache) -> None:
        messages = [{"role": "user", "content": "hi"}]
        cache.put("model", "sys", messages, "response", {})
        stats = cache.stats()
        assert stats["total_entries"] == 1
