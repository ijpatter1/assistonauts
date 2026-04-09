"""Tests for the Captain toolkit — 5 deterministic tools."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from assistonauts.missions.models import Mission, MissionStatus
from assistonauts.tools.captain import (
    BudgetTracker,
    MissionLedger,
    MissionQueueManager,
    ScheduleRunner,
    StatusAggregator,
)

# ================================================================
# 1. Mission Queue Manager — priority queue + dependency graph
# ================================================================


class TestMissionQueueManager:
    def _make_mission(
        self,
        mid: str,
        priority: str = "normal",
        status: MissionStatus = MissionStatus.PENDING,
    ) -> Mission:
        m = Mission(
            mission_id=mid,
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
            priority=priority,
        )
        m.status = status
        return m

    def test_enqueue_and_dequeue(self) -> None:
        mgr = MissionQueueManager()
        m1 = self._make_mission("m1")
        m2 = self._make_mission("m2")
        mgr.enqueue(m1)
        mgr.enqueue(m2)
        assert mgr.size() == 2
        assert mgr.dequeue().mission_id == "m1"
        assert mgr.size() == 1

    def test_priority_ordering(self) -> None:
        mgr = MissionQueueManager()
        low = self._make_mission("low", priority="low")
        normal = self._make_mission("normal", priority="normal")
        high = self._make_mission("high", priority="high")
        critical = self._make_mission("crit", priority="critical")
        mgr.enqueue(low)
        mgr.enqueue(normal)
        mgr.enqueue(high)
        mgr.enqueue(critical)
        assert mgr.dequeue().mission_id == "crit"
        assert mgr.dequeue().mission_id == "high"
        assert mgr.dequeue().mission_id == "normal"
        assert mgr.dequeue().mission_id == "low"

    def test_dequeue_empty_returns_none(self) -> None:
        mgr = MissionQueueManager()
        assert mgr.dequeue() is None

    def test_peek(self) -> None:
        mgr = MissionQueueManager()
        m = self._make_mission("m1", priority="high")
        mgr.enqueue(m)
        assert mgr.peek() is not None
        assert mgr.peek().mission_id == "m1"
        assert mgr.size() == 1  # peek doesn't remove

    def test_add_dependency(self) -> None:
        mgr = MissionQueueManager()
        mgr.add_dependency(depends_on="m1", dependent="m2")
        assert mgr.get_dependencies("m2") == {"m1"}

    def test_is_ready_no_deps(self) -> None:
        mgr = MissionQueueManager()
        m = self._make_mission("m1")
        mgr.enqueue(m)
        assert mgr.is_ready("m1")

    def test_is_ready_with_unmet_deps(self) -> None:
        mgr = MissionQueueManager()
        mgr.add_dependency(depends_on="m1", dependent="m2")
        m2 = self._make_mission("m2")
        mgr.enqueue(m2)
        assert not mgr.is_ready("m2")

    def test_is_ready_with_met_deps(self) -> None:
        mgr = MissionQueueManager()
        mgr.add_dependency(depends_on="m1", dependent="m2")
        mgr.mark_completed("m1")
        m2 = self._make_mission("m2")
        mgr.enqueue(m2)
        assert mgr.is_ready("m2")

    def test_dequeue_ready_skips_blocked(self) -> None:
        mgr = MissionQueueManager()
        m1 = self._make_mission("m1", priority="high")
        m2 = self._make_mission("m2", priority="normal")
        mgr.enqueue(m1)
        mgr.enqueue(m2)
        mgr.add_dependency(depends_on="m3", dependent="m1")
        # m1 is blocked (depends on m3), m2 is ready
        result = mgr.dequeue_ready()
        assert result is not None
        assert result.mission_id == "m2"

    def test_topological_sort(self) -> None:
        mgr = MissionQueueManager()
        # m3 depends on m2, m2 depends on m1
        mgr.add_dependency(depends_on="m1", dependent="m2")
        mgr.add_dependency(depends_on="m2", dependent="m3")
        order = mgr.topological_sort(["m1", "m2", "m3"])
        assert order.index("m1") < order.index("m2")
        assert order.index("m2") < order.index("m3")

    def test_topological_sort_cycle_raises(self) -> None:
        mgr = MissionQueueManager()
        mgr.add_dependency(depends_on="m1", dependent="m2")
        mgr.add_dependency(depends_on="m2", dependent="m1")
        with pytest.raises(ValueError, match=r"[Cc]ycle"):
            mgr.topological_sort(["m1", "m2"])

    def test_topological_sort_independent_nodes(self) -> None:
        mgr = MissionQueueManager()
        order = mgr.topological_sort(["a", "b", "c"])
        assert set(order) == {"a", "b", "c"}


# ================================================================
# 2. Mission Ledger — SQLite source of truth + YAML audit
# ================================================================


class TestMissionLedger:
    @pytest.fixture()
    def ledger(self, tmp_path: Path) -> MissionLedger:
        return MissionLedger(db_path=tmp_path / "ledger.db")

    @pytest.fixture()
    def ledger_with_yaml(self, tmp_path: Path) -> MissionLedger:
        yaml_dir = tmp_path / "missions"
        yaml_dir.mkdir()
        return MissionLedger(
            db_path=tmp_path / "ledger.db",
            yaml_dir=yaml_dir,
        )

    def _make_mission(self, mid: str = "m-001") -> Mission:
        return Mission(
            mission_id=mid,
            agent="compiler",
            mission_type="compile_article",
            inputs={"sources": ["raw/test.md"]},
            acceptance_criteria=["Article written"],
            created_by="captain",
        )

    def test_save_and_get(self, ledger: MissionLedger) -> None:
        m = self._make_mission()
        ledger.save(m)
        loaded = ledger.get("m-001")
        assert loaded is not None
        assert loaded.mission_id == "m-001"
        assert loaded.agent == "compiler"
        assert loaded.status == MissionStatus.PENDING

    def test_get_missing_returns_none(
        self,
        ledger: MissionLedger,
    ) -> None:
        assert ledger.get("nonexistent") is None

    def test_update_status(self, ledger: MissionLedger) -> None:
        m = self._make_mission()
        ledger.save(m)
        m.start()
        ledger.save(m)
        loaded = ledger.get("m-001")
        assert loaded is not None
        assert loaded.status == MissionStatus.RUNNING

    def test_list_by_status(self, ledger: MissionLedger) -> None:
        m1 = self._make_mission("m-001")
        m2 = self._make_mission("m-002")
        m2.start()
        ledger.save(m1)
        ledger.save(m2)
        pending = ledger.list_by_status(MissionStatus.PENDING)
        running = ledger.list_by_status(MissionStatus.RUNNING)
        assert len(pending) == 1
        assert len(running) == 1
        assert pending[0].mission_id == "m-001"
        assert running[0].mission_id == "m-002"

    def test_list_all(self, ledger: MissionLedger) -> None:
        ledger.save(self._make_mission("m-001"))
        ledger.save(self._make_mission("m-002"))
        all_missions = ledger.list_all()
        assert len(all_missions) == 2

    def test_dual_write_yaml(
        self,
        ledger_with_yaml: MissionLedger,
    ) -> None:
        m = self._make_mission()
        ledger_with_yaml.save(m)
        yaml_file = ledger_with_yaml.yaml_dir / "m-001.yaml"
        assert yaml_file.exists()
        content = yaml_file.read_text()
        assert "m-001" in content
        assert "compiler" in content

    def test_db_is_source_of_truth(
        self,
        ledger_with_yaml: MissionLedger,
    ) -> None:
        """Verify data is loaded from DB, not YAML."""
        m = self._make_mission()
        ledger_with_yaml.save(m)
        # Corrupt the YAML file
        yaml_file = ledger_with_yaml.yaml_dir / "m-001.yaml"
        yaml_file.write_text("corrupted")
        # DB still returns correct data
        loaded = ledger_with_yaml.get("m-001")
        assert loaded is not None
        assert loaded.mission_id == "m-001"

    def test_wal_mode_enabled(self, ledger: MissionLedger) -> None:
        conn = sqlite3.connect(str(ledger.db_path))
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


# ================================================================
# 3. Token Budget Tracker
# ================================================================


class TestBudgetTracker:
    @pytest.fixture()
    def tracker(self, tmp_path: Path) -> BudgetTracker:
        return BudgetTracker(
            db_path=tmp_path / "budget.db",
            daily_token_limit=100_000,
            warning_threshold=0.8,
        )

    def test_record_usage(self, tracker: BudgetTracker) -> None:
        tracker.record(
            agent="compiler",
            expedition="test-exp",
            tokens=5000,
        )
        assert tracker.get_daily_total() == 5000

    def test_get_by_agent(self, tracker: BudgetTracker) -> None:
        tracker.record(agent="compiler", expedition="e", tokens=3000)
        tracker.record(agent="scout", expedition="e", tokens=2000)
        tracker.record(agent="compiler", expedition="e", tokens=1000)
        assert tracker.get_agent_total("compiler") == 4000
        assert tracker.get_agent_total("scout") == 2000

    def test_get_by_expedition(self, tracker: BudgetTracker) -> None:
        tracker.record(agent="compiler", expedition="e1", tokens=3000)
        tracker.record(agent="compiler", expedition="e2", tokens=2000)
        assert tracker.get_expedition_total("e1") == 3000
        assert tracker.get_expedition_total("e2") == 2000

    def test_warning_threshold_not_exceeded(
        self,
        tracker: BudgetTracker,
    ) -> None:
        tracker.record(agent="compiler", expedition="e", tokens=50_000)
        assert not tracker.is_warning()

    def test_warning_threshold_exceeded(
        self,
        tracker: BudgetTracker,
    ) -> None:
        tracker.record(
            agent="compiler",
            expedition="e",
            tokens=85_000,
        )
        assert tracker.is_warning()

    def test_budget_not_exceeded(
        self,
        tracker: BudgetTracker,
    ) -> None:
        tracker.record(
            agent="compiler",
            expedition="e",
            tokens=90_000,
        )
        assert not tracker.is_exceeded()

    def test_budget_exceeded(self, tracker: BudgetTracker) -> None:
        tracker.record(
            agent="compiler",
            expedition="e",
            tokens=100_001,
        )
        assert tracker.is_exceeded()

    def test_remaining_budget(self, tracker: BudgetTracker) -> None:
        tracker.record(agent="compiler", expedition="e", tokens=40_000)
        assert tracker.remaining() == 60_000

    def test_daily_reset_via_date(self, tmp_path: Path) -> None:
        tracker = BudgetTracker(
            db_path=tmp_path / "budget.db",
            daily_token_limit=100_000,
        )
        # Record for a specific past date
        tracker.record(
            agent="compiler",
            expedition="e",
            tokens=50_000,
            date="2026-01-01",
        )
        # Today's total should be 0
        assert tracker.get_daily_total() == 0


# ================================================================
# 4. Schedule Runner — cron expression evaluation
# ================================================================


class TestScheduleRunner:
    def test_matches_every_minute(self) -> None:
        runner = ScheduleRunner()
        dt = datetime(2026, 4, 9, 12, 30, tzinfo=UTC)
        assert runner.matches("* * * * *", dt)

    def test_matches_specific_minute(self) -> None:
        runner = ScheduleRunner()
        dt = datetime(2026, 4, 9, 12, 30, tzinfo=UTC)
        assert runner.matches("30 * * * *", dt)
        assert not runner.matches("15 * * * *", dt)

    def test_matches_specific_hour(self) -> None:
        runner = ScheduleRunner()
        dt = datetime(2026, 4, 9, 8, 0, tzinfo=UTC)
        assert runner.matches("0 8 * * *", dt)
        assert not runner.matches("0 9 * * *", dt)

    def test_matches_day_of_week(self) -> None:
        runner = ScheduleRunner()
        # 2026-04-09 is Thursday (day 4 in cron, 0=Sunday)
        dt = datetime(2026, 4, 9, 0, 0, tzinfo=UTC)
        assert runner.matches("0 0 * * 4", dt)
        assert not runner.matches("0 0 * * 1", dt)

    def test_matches_day_of_month(self) -> None:
        runner = ScheduleRunner()
        dt = datetime(2026, 4, 15, 0, 0, tzinfo=UTC)
        assert runner.matches("0 0 15 * *", dt)
        assert not runner.matches("0 0 16 * *", dt)

    def test_matches_month(self) -> None:
        runner = ScheduleRunner()
        dt = datetime(2026, 4, 1, 0, 0, tzinfo=UTC)
        assert runner.matches("0 0 1 4 *", dt)
        assert not runner.matches("0 0 1 5 *", dt)

    def test_step_expression(self) -> None:
        runner = ScheduleRunner()
        dt = datetime(2026, 4, 9, 6, 0, tzinfo=UTC)
        assert runner.matches("0 */6 * * *", dt)
        dt2 = datetime(2026, 4, 9, 7, 0, tzinfo=UTC)
        assert not runner.matches("0 */6 * * *", dt2)

    def test_next_run(self) -> None:
        runner = ScheduleRunner()
        now = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
        nxt = runner.next_run("0 0 * * *", now)
        assert nxt is not None
        assert nxt.hour == 0
        assert nxt.day == 10  # next midnight


# ================================================================
# 5. Status Aggregator
# ================================================================


class TestStatusAggregator:
    def test_aggregate_missions(self) -> None:
        missions = [
            Mission(
                mission_id="m1",
                agent="compiler",
                mission_type="compile",
                inputs={},
                acceptance_criteria=[],
                created_by="captain",
            ),
            Mission(
                mission_id="m2",
                agent="scout",
                mission_type="ingest",
                inputs={},
                acceptance_criteria=[],
                created_by="captain",
            ),
        ]
        missions[0].start()
        missions[0].complete()
        agg = StatusAggregator()
        summary = agg.aggregate(missions)
        assert summary["total"] == 2
        assert summary["by_status"]["completed"] == 1
        assert summary["by_status"]["pending"] == 1
        assert summary["by_agent"]["compiler"] == 1
        assert summary["by_agent"]["scout"] == 1

    def test_aggregate_empty(self) -> None:
        agg = StatusAggregator()
        summary = agg.aggregate([])
        assert summary["total"] == 0
        assert summary["by_status"] == {}

    def test_format_for_llm(self) -> None:
        missions = [
            Mission(
                mission_id="m1",
                agent="compiler",
                mission_type="compile",
                inputs={},
                acceptance_criteria=["Article written"],
                created_by="captain",
            ),
        ]
        missions[0].start()
        agg = StatusAggregator()
        text = agg.format_for_llm(missions)
        assert isinstance(text, str)
        assert "m1" in text
        assert "running" in text.lower()
        assert "compiler" in text.lower()
