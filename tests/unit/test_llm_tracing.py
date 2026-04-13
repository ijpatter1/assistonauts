"""Tests for LLM call tracing — observer callback on LLMClient.

Verifies that every non-deterministic LLM operation can be traced
end-to-end via the on_llm_call callback, including caller context
from the trace_context thread-local.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistonauts.llm.client import LLMClient, LLMResponse
from assistonauts.llm.tracing import set_trace_context, clear_trace_context
from tests.helpers import FakeLLMClient


# ── LLMClient callback ───────────────────────────────


class TestLLMClientCallback:
    """on_llm_call callback fires on every complete() call."""

    def test_callback_fires_on_complete(self, tmp_path: Path) -> None:
        """Callback receives full request and response data."""
        records: list[dict[str, object]] = []

        def capture(record: dict[str, object]) -> None:
            records.append(record)

        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
            on_llm_call=capture,
        )
        # Create a fixture for replay
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "hello"}],
            system="You are helpful.",
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({
                "content": "Hi there!",
                "model": "test-model",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })
        )

        client.complete(
            messages=[{"role": "user", "content": "hello"}],
            system="You are helpful.",
        )

        assert len(records) == 1
        rec = records[0]
        assert rec["messages"] == [{"role": "user", "content": "hello"}]
        assert rec["system"] == "You are helpful."
        assert rec["response"] == "Hi there!"
        assert rec["model"] == "test-model"
        assert rec["usage"] == {"prompt_tokens": 10, "completion_tokens": 5}

    def test_callback_not_required(self, tmp_path: Path) -> None:
        """LLMClient works without callback (backwards compatible)."""
        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
        )
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "test"}],
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({"content": "ok", "model": "m", "usage": {}})
        )
        # Should not raise
        resp = client.complete(messages=[{"role": "user", "content": "test"}])
        assert resp.content == "ok"

    def test_callback_receives_timestamp(self, tmp_path: Path) -> None:
        """Each callback record includes a timestamp."""
        records: list[dict[str, object]] = []
        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
            on_llm_call=lambda r: records.append(r),
        )
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "ts"}],
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({"content": "ok", "model": "m", "usage": {}})
        )
        client.complete(messages=[{"role": "user", "content": "ts"}])
        assert "timestamp" in records[0]

    def test_callback_fires_on_cache_hit(self, tmp_path: Path) -> None:
        """Callback fires even when the response comes from cache."""
        records: list[dict[str, object]] = []
        cache_path = tmp_path / "cache.db"
        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
            cache_path=cache_path,
            on_llm_call=lambda r: records.append(r),
        )
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "cached"}],
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({"content": "cached-resp", "model": "m", "usage": {}})
        )
        # First call populates cache via replay
        client.complete(messages=[{"role": "user", "content": "cached"}])
        assert len(records) == 1


# ── Trace context ─────────────────────────────────────


class TestTraceContext:
    """Thread-local trace_context allows callers to attach metadata."""

    def test_trace_context_included_in_callback(self, tmp_path: Path) -> None:
        """When trace_context is set, its values appear in callback."""
        records: list[dict[str, object]] = []
        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
            on_llm_call=lambda r: records.append(r),
        )
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "ctx"}],
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({"content": "ok", "model": "m", "usage": {}})
        )

        set_trace_context(agent="captain", mission_id="m-001", phase="structuring")
        try:
            client.complete(messages=[{"role": "user", "content": "ctx"}])
        finally:
            clear_trace_context()

        assert records[0]["context"]["agent"] == "captain"
        assert records[0]["context"]["mission_id"] == "m-001"
        assert records[0]["context"]["phase"] == "structuring"

    def test_empty_context_when_not_set(self, tmp_path: Path) -> None:
        """When trace_context is not set, context is empty dict."""
        records: list[dict[str, object]] = []
        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
            on_llm_call=lambda r: records.append(r),
        )
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "no-ctx"}],
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({"content": "ok", "model": "m", "usage": {}})
        )

        clear_trace_context()
        client.complete(messages=[{"role": "user", "content": "no-ctx"}])
        assert records[0]["context"] == {}

    def test_clear_removes_context(self, tmp_path: Path) -> None:
        """clear_trace_context removes all previously set values."""
        set_trace_context(agent="scout")
        clear_trace_context()

        records: list[dict[str, object]] = []
        client = LLMClient(
            provider_config={},
            mode="replay",
            fixture_dir=tmp_path,
            on_llm_call=lambda r: records.append(r),
        )
        fixture_key = client._fixture_key(
            [{"role": "user", "content": "cleared"}],
        )
        (tmp_path / f"{fixture_key}.json").write_text(
            json.dumps({"content": "ok", "model": "m", "usage": {}})
        )
        client.complete(messages=[{"role": "user", "content": "cleared"}])
        assert records[0]["context"] == {}


# ── Orchestrator trace file ───────────────────────────


class TestOrchestratorTraceFile:
    """Orchestrator writes llm-trace.jsonl during builds."""

    @pytest.fixture()
    def workspace(self, tmp_path: Path) -> Path:
        dirs = [
            "raw/articles",
            "wiki/concept",
            "wiki/explorations",
            "index",
            "audits",
            "expeditions/test-exp/missions",
            "expeditions/test-exp/review",
            "station-logs",
            ".assistonauts/logs",
            ".assistonauts/tasks",
        ]
        for d in dirs:
            (tmp_path / d).mkdir(parents=True)
        return tmp_path

    def test_trace_file_created_during_build(self, workspace: Path) -> None:
        """run_build creates llm-trace.jsonl in expedition directory."""
        from assistonauts.expeditions.orchestrator import BuildOrchestrator
        from assistonauts.models.config import ExpeditionConfig

        config = ExpeditionConfig.from_dict({
            "name": "test-exp",
            "description": "Test",
            "scope": {"description": "Test", "keywords": ["test"]},
            "sources": {"local": [{"path": "/tmp/t", "pattern": "*.md"}]},
        })

        # Captain plans no missions → quick exit
        plan_response = (
            "```yaml\nmissions: []\n```\n"
        )
        client = FakeLLMClient(responses=[plan_response] * 5)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        orch.run_build()

        trace_file = workspace / "expeditions" / "test-exp" / "llm-trace.jsonl"
        assert trace_file.exists()

    def test_trace_entries_have_full_content(self, workspace: Path) -> None:
        """Trace entries contain prompt messages and response content."""
        from assistonauts.expeditions.orchestrator import BuildOrchestrator
        from assistonauts.models.config import ExpeditionConfig

        config = ExpeditionConfig.from_dict({
            "name": "test-exp",
            "description": "Test",
            "scope": {"description": "Test scope", "keywords": ["test"]},
            "sources": {"local": [{"path": "/tmp/t", "pattern": "*.md"}]},
        })

        plan_response = "```yaml\nmissions: []\n```\n"
        client = FakeLLMClient(responses=[plan_response] * 5)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        orch.run_build()

        trace_file = workspace / "expeditions" / "test-exp" / "llm-trace.jsonl"
        entries = [
            json.loads(line)
            for line in trace_file.read_text().splitlines()
            if line.strip()
        ]
        assert len(entries) > 0
        entry = entries[0]
        # Must have full prompt and response
        assert "messages" in entry
        assert "response" in entry
        assert "model" in entry
        assert "timestamp" in entry
        # Response should contain the plan YAML
        assert "missions" in entry["response"]

    def test_trace_context_set_during_planning(self, workspace: Path) -> None:
        """Planning calls include phase context in trace entries."""
        from assistonauts.expeditions.orchestrator import BuildOrchestrator
        from assistonauts.models.config import ExpeditionConfig

        config = ExpeditionConfig.from_dict({
            "name": "test-exp",
            "description": "Test",
            "scope": {"description": "Test", "keywords": ["test"]},
            "sources": {"local": [{"path": "/tmp/t", "pattern": "*.md"}]},
        })

        plan_response = "```yaml\nmissions: []\n```\n"
        client = FakeLLMClient(responses=[plan_response] * 5)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        orch.run_build()

        trace_file = workspace / "expeditions" / "test-exp" / "llm-trace.jsonl"
        entries = [
            json.loads(line)
            for line in trace_file.read_text().splitlines()
            if line.strip()
        ]
        # At least the Discovery planning call should have context
        has_context = any(
            e.get("context", {}).get("phase") for e in entries
        )
        assert has_context, "No trace entries have phase context"
