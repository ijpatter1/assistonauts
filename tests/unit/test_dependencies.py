"""Tests for task dependency resolution."""

import pytest

from assistonauts.missions.dependencies import (
    DependencyGraph,
    build_graph_from_plan,
)
from assistonauts.missions.models import Mission


def _make_mission(
    mid: str,
    agent: str = "compiler",
    mtype: str = "compile_article",
) -> Mission:
    return Mission(
        mission_id=mid,
        agent=agent,
        mission_type=mtype,
        inputs={},
        acceptance_criteria=[],
        created_by="captain",
    )


class TestDependencyGraph:
    def test_add_edge(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        assert g.dependencies("m2") == {"m1"}

    def test_no_dependencies(self) -> None:
        g = DependencyGraph()
        assert g.dependencies("m1") == set()

    def test_multiple_dependencies(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m3")
        g.add_edge("m2", "m3")
        assert g.dependencies("m3") == {"m1", "m2"}

    def test_dependents(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        g.add_edge("m1", "m3")
        assert g.dependents("m1") == {"m2", "m3"}

    def test_topological_order(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        g.add_edge("m2", "m3")
        order = g.topological_order(["m1", "m2", "m3"])
        assert order == ["m1", "m2", "m3"]

    def test_topological_order_independent(self) -> None:
        g = DependencyGraph()
        order = g.topological_order(["a", "b", "c"])
        assert set(order) == {"a", "b", "c"}

    def test_cycle_detection(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        g.add_edge("m2", "m1")
        with pytest.raises(ValueError, match=r"[Cc]ycle"):
            g.topological_order(["m1", "m2"])

    def test_is_ready(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        completed = {"m1"}
        assert g.is_ready("m2", completed)
        assert not g.is_ready("m2", set())

    def test_ready_missions(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        g.add_edge("m1", "m3")
        pending = {"m1", "m2", "m3"}
        completed: set[str] = set()
        ready = g.ready_missions(pending, completed)
        assert ready == {"m1"}

    def test_ready_after_completion(self) -> None:
        g = DependencyGraph()
        g.add_edge("m1", "m2")
        g.add_edge("m1", "m3")
        pending = {"m2", "m3"}
        completed = {"m1"}
        ready = g.ready_missions(pending, completed)
        assert ready == {"m2", "m3"}


class TestBuildGraphFromPlan:
    def test_basic(self) -> None:
        missions = [
            _make_mission("m1", agent="scout"),
            _make_mission("m2", agent="compiler"),
            _make_mission("m3", agent="compiler"),
        ]
        deps = [("m1", "m2"), ("m1", "m3")]
        graph = build_graph_from_plan(missions, deps)
        order = graph.topological_order(
            [m.mission_id for m in missions],
        )
        assert order.index("m1") < order.index("m2")
        assert order.index("m1") < order.index("m3")

    def test_empty(self) -> None:
        graph = build_graph_from_plan([], [])
        assert graph.topological_order([]) == []

    def test_cascading_chain(self) -> None:
        """Test compile -> reindex -> link chain."""
        missions = [
            _make_mission("compile", "compiler", "compile_article"),
            _make_mission("reindex", "archivist", "reindex"),
            _make_mission("link", "curator", "cross_reference"),
        ]
        deps = [
            ("compile", "reindex"),
            ("reindex", "link"),
        ]
        graph = build_graph_from_plan(missions, deps)
        order = graph.topological_order(
            [m.mission_id for m in missions],
        )
        assert order == ["compile", "reindex", "link"]
