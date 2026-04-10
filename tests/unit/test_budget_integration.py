"""Tests for budget system integration with orchestration."""

from pathlib import Path

from assistonauts.expeditions.budget import (
    BudgetEnforcer,
    BudgetNotification,
)
from assistonauts.models.config import BudgetConfig
from assistonauts.tools.captain import BudgetTracker


class TestBudgetEnforcer:
    def test_check_ok(self, tmp_path: Path) -> None:
        tracker = BudgetTracker(
            db_path=tmp_path / "budget.db",
            daily_token_limit=100_000,
            warning_threshold=0.8,
        )
        enforcer = BudgetEnforcer(tracker)
        notification = enforcer.check()
        assert notification.can_proceed
        assert not notification.is_warning

    def test_check_warning(self, tmp_path: Path) -> None:
        tracker = BudgetTracker(
            db_path=tmp_path / "budget.db",
            daily_token_limit=100_000,
            warning_threshold=0.8,
        )
        tracker.record(
            agent="compiler",
            expedition="test",
            tokens=85_000,
        )
        enforcer = BudgetEnforcer(tracker)
        notification = enforcer.check()
        assert notification.can_proceed
        assert notification.is_warning
        assert "85%" in notification.message

    def test_check_exceeded(self, tmp_path: Path) -> None:
        tracker = BudgetTracker(
            db_path=tmp_path / "budget.db",
            daily_token_limit=100_000,
            warning_threshold=0.8,
        )
        tracker.record(
            agent="compiler",
            expedition="test",
            tokens=100_001,
        )
        enforcer = BudgetEnforcer(tracker)
        notification = enforcer.check()
        assert not notification.can_proceed
        assert notification.is_exceeded
        assert "exceeded" in notification.message.lower()

    def test_remaining(self, tmp_path: Path) -> None:
        tracker = BudgetTracker(
            db_path=tmp_path / "budget.db",
            daily_token_limit=100_000,
        )
        tracker.record(
            agent="compiler",
            expedition="test",
            tokens=40_000,
        )
        enforcer = BudgetEnforcer(tracker)
        assert enforcer.remaining() == 60_000

    def test_from_config(self, tmp_path: Path) -> None:
        config = BudgetConfig(
            daily_token_limit=50_000,
            warning_threshold=0.9,
        )
        enforcer = BudgetEnforcer.from_config(
            config,
            tmp_path / "budget.db",
        )
        enforcer.tracker.record(
            agent="scout",
            expedition="e",
            tokens=46_000,
        )
        notification = enforcer.check()
        assert notification.is_warning
        assert notification.can_proceed


class TestBudgetNotification:
    def test_ok_notification(self) -> None:
        n = BudgetNotification(
            can_proceed=True,
            is_warning=False,
            is_exceeded=False,
            usage_percent=50.0,
            remaining=50_000,
            message="Budget OK: 50% used",
        )
        assert n.can_proceed
        assert not n.is_warning

    def test_exceeded_notification(self) -> None:
        n = BudgetNotification(
            can_proceed=False,
            is_warning=False,
            is_exceeded=True,
            usage_percent=100.1,
            remaining=0,
            message="Budget exceeded",
        )
        assert not n.can_proceed
        assert n.is_exceeded
