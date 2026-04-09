"""Captain toolkit — deterministic tools for expedition orchestration.

Five tools, all zero-inference (no LLM calls):
1. MissionQueueManager — priority queue + dependency graph + topological sort
2. MissionLedger — SQLite source of truth, dual-write with YAML audit
3. BudgetTracker — token usage tracking per (agent, expedition, date)
4. ScheduleRunner — cron expression evaluation
5. StatusAggregator — mission status summaries for Captain LLM reasoning
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import yaml

from assistonauts.missions.dependencies import DependencyGraph
from assistonauts.missions.models import Mission, MissionStatus
from assistonauts.tasks.runner import TaskStatus

# ================================================================
# 1. Mission Queue Manager
# ================================================================


class MissionQueueManager:
    """Priority queue with dependency graph for mission sequencing."""

    PRIORITY_ORDER: ClassVar[dict[str, int]] = {
        "critical": 0,
        "high": 1,
        "normal": 2,
        "low": 3,
    }

    def __init__(self) -> None:
        self._queue: list[Mission] = []
        self._graph = DependencyGraph()
        self._completed: set[str] = set()

    def enqueue(self, mission: Mission) -> None:
        self._queue.append(mission)
        self._sort()

    def dequeue(self) -> Mission | None:
        if not self._queue:
            return None
        return self._queue.pop(0)

    def dequeue_ready(self) -> Mission | None:
        """Dequeue the highest-priority mission whose deps are met."""
        for i, m in enumerate(self._queue):
            if self.is_ready(m.mission_id):
                return self._queue.pop(i)
        return None

    def peek(self) -> Mission | None:
        return self._queue[0] if self._queue else None

    def size(self) -> int:
        return len(self._queue)

    # --- Dependencies (delegates to DependencyGraph) ---

    def add_dependency(
        self,
        depends_on: str,
        dependent: str,
    ) -> None:
        """Record that `dependent` cannot start until `depends_on` completes."""
        self._graph.add_edge(depends_on, dependent)

    def get_dependencies(self, mission_id: str) -> set[str]:
        return self._graph.dependencies(mission_id)

    def mark_completed(self, mission_id: str) -> None:
        self._completed.add(mission_id)

    def is_ready(self, mission_id: str) -> bool:
        return self._graph.is_ready(mission_id, self._completed)

    def topological_sort(self, mission_ids: list[str]) -> list[str]:
        """Return mission_ids in dependency order."""
        return self._graph.topological_order(mission_ids)

    # --- Internal ---

    def _sort(self) -> None:
        self._queue.sort(
            key=lambda m: self.PRIORITY_ORDER.get(m.priority, 2),
        )


# ================================================================
# 2. Mission Ledger — SQLite + YAML dual-write
# ================================================================


class MissionLedger:
    """SQLite-backed mission state persistence with YAML audit trail.

    The SQLite database is the source of truth for mission state.
    YAML files are written alongside as human-readable audit records.
    """

    def __init__(
        self,
        db_path: Path,
        yaml_dir: Path | None = None,
    ) -> None:
        self.db_path = db_path
        self.yaml_dir = yaml_dir
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS missions (
                mission_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status TEXT NOT NULL,
                agent TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def save(self, mission: Mission) -> None:
        """Save mission to SQLite (source of truth) and YAML (audit)."""
        data = json.dumps(mission.to_dict(), default=str)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO missions
                (mission_id, data, status, agent, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                mission.mission_id,
                data,
                mission.status.value,
                mission.agent,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()

        # Dual-write: YAML audit trail
        if self.yaml_dir:
            self._write_yaml(mission)

    def get(self, mission_id: str) -> Mission | None:
        """Load mission from SQLite (source of truth)."""
        row = self._conn.execute(
            "SELECT data FROM missions WHERE mission_id = ?",
            (mission_id,),
        ).fetchone()
        if row is None:
            return None
        return Mission.from_dict(json.loads(row[0]))

    def list_by_status(
        self,
        status: MissionStatus,
    ) -> list[Mission]:
        rows = self._conn.execute(
            "SELECT data FROM missions WHERE status = ?",
            (status.value,),
        ).fetchall()
        return [Mission.from_dict(json.loads(r[0])) for r in rows]

    def list_all(self) -> list[Mission]:
        rows = self._conn.execute(
            "SELECT data FROM missions",
        ).fetchall()
        return [Mission.from_dict(json.loads(r[0])) for r in rows]

    def _write_yaml(self, mission: Mission) -> None:
        if self.yaml_dir is None:
            return
        path = self.yaml_dir / f"{mission.mission_id}.yaml"
        path.write_text(
            yaml.dump(mission.to_dict(), default_flow_style=False),
        )


# ================================================================
# 3. Token Budget Tracker
# ================================================================


class BudgetTracker:
    """Tracks token usage per (agent, expedition, date).

    Supports a warning threshold (default 0.8) and a hard cap
    at daily_token_limit.
    """

    def __init__(
        self,
        db_path: Path,
        daily_token_limit: int = 100_000,
        warning_threshold: float = 0.8,
    ) -> None:
        self.db_path = db_path
        self.daily_token_limit = daily_token_limit
        self.warning_threshold = warning_threshold
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def close(self) -> None:
        """Close the SQLite connection."""
        self._conn.close()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent TEXT NOT NULL,
                expedition TEXT NOT NULL,
                tokens INTEGER NOT NULL,
                date TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def record(
        self,
        agent: str,
        expedition: str,
        tokens: int,
        date: str | None = None,
    ) -> None:
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")
        self._conn.execute(
            """
            INSERT INTO token_usage
                (agent, expedition, tokens, date, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent, expedition, tokens, date, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()

    def get_daily_total(
        self,
        date: str | None = None,
    ) -> int:
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM token_usage WHERE date = ?",
            (date,),
        ).fetchone()
        return int(row[0])

    def get_agent_total(
        self,
        agent: str,
        date: str | None = None,
    ) -> int:
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM token_usage "
            "WHERE agent = ? AND date = ?",
            (agent, date),
        ).fetchone()
        return int(row[0])

    def get_expedition_total(
        self,
        expedition: str,
        date: str | None = None,
    ) -> int:
        if date is None:
            date = datetime.now(UTC).strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COALESCE(SUM(tokens), 0) FROM token_usage "
            "WHERE expedition = ? AND date = ?",
            (expedition, date),
        ).fetchone()
        return int(row[0])

    def is_warning(self, date: str | None = None) -> bool:
        total = self.get_daily_total(date)
        return total >= self.daily_token_limit * self.warning_threshold

    def is_exceeded(self, date: str | None = None) -> bool:
        return self.get_daily_total(date) >= self.daily_token_limit

    def remaining(self, date: str | None = None) -> int:
        return max(
            0,
            self.daily_token_limit - self.get_daily_total(date),
        )


# ================================================================
# 4. Schedule Runner — cron expression evaluation
# ================================================================


class ScheduleRunner:
    """Evaluates cron expressions against datetimes.

    Supports standard 5-field cron: minute hour day month weekday.
    Supports * (any), specific values, and */N (step).
    """

    def matches(self, cron_expr: str, dt: datetime) -> bool:
        fields = cron_expr.strip().split()
        if len(fields) != 5:
            msg = f"Expected 5-field cron, got {len(fields)}: {cron_expr}"
            raise ValueError(msg)

        return (
            self._matches_field(fields[0], dt.minute, 0, 59)
            and self._matches_field(fields[1], dt.hour, 0, 23)
            and self._matches_field(fields[2], dt.day, 1, 31)
            and self._matches_field(fields[3], dt.month, 1, 12)
            and self._matches_field(
                fields[4],
                dt.weekday() + 1 if dt.weekday() < 6 else 0,
                0,
                6,
            )
        )

    def next_run(
        self,
        cron_expr: str,
        after: datetime,
        max_minutes: int = 1440 * 7,  # 1 week lookahead
    ) -> datetime | None:
        """Find the next datetime matching the cron expression."""
        candidate = after.replace(second=0, microsecond=0) + timedelta(
            minutes=1,
        )
        for _ in range(max_minutes):
            if self.matches(cron_expr, candidate):
                return candidate
            candidate += timedelta(minutes=1)
        return None

    @staticmethod
    def _matches_field(
        field: str,
        value: int,
        min_val: int,
        max_val: int,
    ) -> bool:
        if field == "*":
            return True
        if field.startswith("*/"):
            step = int(field[2:])
            return (value - min_val) % step == 0
        return int(field) == value


# ================================================================
# 5. Status Aggregator
# ================================================================


class StatusAggregator:
    """Produces mission status summaries for Captain LLM reasoning.

    Output is structured for LLM consumption, not console display.
    """

    def aggregate(
        self,
        missions: list[Mission],
    ) -> dict[str, int | dict[str, int]]:
        by_status: dict[str, int] = defaultdict(int)
        by_agent: dict[str, int] = defaultdict(int)

        for m in missions:
            by_status[m.status.value] += 1
            by_agent[m.agent] += 1

        return {
            "total": len(missions),
            "by_status": dict(by_status),
            "by_agent": dict(by_agent),
        }

    def format_for_llm(self, missions: list[Mission]) -> str:
        """Produce LLM-digestible structured text summary."""
        if not missions:
            return "No missions in ledger."

        summary = self.aggregate(missions)
        lines = [
            f"Mission Summary: {summary['total']} total",
        ]

        status_dict = summary["by_status"]
        if isinstance(status_dict, dict) and status_dict:
            status_parts = [f"{v} {k}" for k, v in status_dict.items()]
            lines.append(f"Status: {', '.join(status_parts)}")

        agent_dict = summary["by_agent"]
        if isinstance(agent_dict, dict) and agent_dict:
            agent_parts = [f"{v} {k}" for k, v in agent_dict.items()]
            lines.append(f"By agent: {', '.join(agent_parts)}")

        lines.append("")
        lines.append("Mission Details:")
        for m in missions:
            criteria_str = (
                "; ".join(m.acceptance_criteria) if m.acceptance_criteria else "none"
            )
            lines.append(
                f"  [{m.mission_id}] {m.agent}/{m.mission_type} "
                f"— {m.status.value} "
                f"(criteria: {criteria_str})",
            )
            if m.checklist:
                checked = sum(1 for c in m.checklist if c.startswith("verified_by:"))
                lines.append(
                    f"    Checklist: {len(m.checklist)} items ({checked} verified)",
                )
            if m.tasks:
                done = sum(1 for t in m.tasks if t.status == TaskStatus.COMPLETED)
                lines.append(
                    f"    Tasks: {done}/{len(m.tasks)} completed",
                )
            if m.failure:
                lines.append(
                    f"    FAILED: {m.failure.error_type} — {m.failure.error_message}",
                )

        return "\n".join(lines)
