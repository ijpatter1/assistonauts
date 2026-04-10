"""Budget enforcement for build phase orchestration.

Wraps BudgetTracker with enforcement logic: warning notifications
at configurable threshold, hard cap that halts execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from assistonauts.models.config import BudgetConfig
from assistonauts.tools.captain import BudgetTracker


@dataclass
class BudgetNotification:
    """Result of a budget check."""

    can_proceed: bool
    is_warning: bool
    is_exceeded: bool
    usage_percent: float
    remaining: int
    message: str


class BudgetEnforcer:
    """Enforces budget limits with warning and hard cap."""

    def __init__(self, tracker: BudgetTracker) -> None:
        self.tracker = tracker

    @classmethod
    def from_config(
        cls,
        config: BudgetConfig,
        db_path: Path,
    ) -> BudgetEnforcer:
        tracker = BudgetTracker(
            db_path=db_path,
            daily_token_limit=config.daily_token_limit,
            warning_threshold=config.warning_threshold,
        )
        return cls(tracker)

    def check(self) -> BudgetNotification:
        """Check current budget status."""
        total = self.tracker.get_daily_total()
        limit = self.tracker.daily_token_limit
        pct = (total / limit * 100) if limit > 0 else 0
        remaining = self.tracker.remaining()

        if self.tracker.is_exceeded():
            return BudgetNotification(
                can_proceed=False,
                is_warning=False,
                is_exceeded=True,
                usage_percent=pct,
                remaining=0,
                message=(f"Budget exceeded: {total:,} tokens used (limit: {limit:,})"),
            )
        elif self.tracker.is_warning():
            return BudgetNotification(
                can_proceed=True,
                is_warning=True,
                is_exceeded=False,
                usage_percent=pct,
                remaining=remaining,
                message=(
                    f"Budget warning: {pct:.0f}% used ({remaining:,} tokens remaining)"
                ),
            )
        else:
            return BudgetNotification(
                can_proceed=True,
                is_warning=False,
                is_exceeded=False,
                usage_percent=pct,
                remaining=remaining,
                message=f"Budget OK: {pct:.0f}% used",
            )

    def remaining(self) -> int:
        return self.tracker.remaining()
