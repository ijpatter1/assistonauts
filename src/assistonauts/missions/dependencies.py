"""Task dependency resolution — graph construction and topological sort."""

from __future__ import annotations

from collections import defaultdict

from assistonauts.missions.models import Mission


class DependencyGraph:
    """Directed acyclic graph for mission dependency resolution.

    Edges go from dependency to dependent: add_edge(A, B) means
    B depends on A (A must complete before B can start).
    """

    def __init__(self) -> None:
        # dependency -> set of dependents
        self._forward: dict[str, set[str]] = defaultdict(set)
        # dependent -> set of dependencies
        self._reverse: dict[str, set[str]] = defaultdict(set)

    def add_edge(self, depends_on: str, dependent: str) -> None:
        """Record that `dependent` requires `depends_on` to complete."""
        self._forward[depends_on].add(dependent)
        self._reverse[dependent].add(depends_on)

    def dependencies(self, mission_id: str) -> set[str]:
        """What must complete before this mission can start."""
        return set(self._reverse.get(mission_id, set()))

    def dependents(self, mission_id: str) -> set[str]:
        """What is blocked by this mission."""
        return set(self._forward.get(mission_id, set()))

    def is_ready(
        self,
        mission_id: str,
        completed: set[str],
    ) -> bool:
        """Check if all dependencies are in the completed set."""
        return self.dependencies(mission_id).issubset(completed)

    def ready_missions(
        self,
        pending: set[str],
        completed: set[str],
    ) -> set[str]:
        """Return all pending missions whose dependencies are met."""
        return {mid for mid in pending if self.is_ready(mid, completed)}

    def topological_order(
        self,
        mission_ids: list[str],
    ) -> list[str]:
        """Return mission_ids in dependency order (Kahn's algorithm)."""
        id_set = set(mission_ids)
        in_degree: dict[str, int] = {mid: 0 for mid in id_set}
        adj: dict[str, list[str]] = {mid: [] for mid in id_set}

        for mid in id_set:
            for dep in self._reverse.get(mid, set()):
                if dep in id_set:
                    in_degree[mid] += 1
                    adj[dep].append(mid)

        queue = sorted(mid for mid in id_set if in_degree[mid] == 0)
        result: list[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(adj[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(id_set):
            msg = "Cycle detected in mission dependencies"
            raise ValueError(msg)
        return result


def build_graph_from_plan(
    missions: list[Mission],
    dependencies: list[tuple[str, str]],
) -> DependencyGraph:
    """Build a DependencyGraph from a Captain plan result.

    dependencies is a list of (depends_on, dependent) tuples.
    """
    graph = DependencyGraph()
    for depends_on, dependent in dependencies:
        graph.add_edge(depends_on, dependent)
    return graph
