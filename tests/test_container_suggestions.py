"""Tests for get_container_suggestions — the Details-tab empty-state list.

Containers here mean any node with ``time_mode='inherited'`` (broader than
``Node.is_container`` which also requires ``value_mode='inherited'``). The
helper feeds the Details tab's "Top Recommendations" section, which is meant
to surface structurally rich nodes worth examining, not leaf actions.
"""

from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD
from graph_manager import GraphManager
from config import ConfigManager


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = False
    database.init_db()
    yield tmp_db_path


@pytest.fixture
def mgr():
    return GraphManager()


def _make_node(name: str = "TestNode", **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="A test node",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


def _build_container_with_children(mgr, container_name="Container", n_children=3,
                                    container_type="Learn"):
    """Create a container (time_mode='inherited') with N hard-prereq children."""
    mgr.add_node(_make_node(container_name, type=container_type,
                            time_mode='inherited'))
    for i in range(n_children):
        child_name = f"{container_name}_Child{i}"
        mgr.add_node(_make_node(child_name, value=8, interest=8))
        mgr.add_edge(child_name, container_name, EDGE_NEEDS_HARD)


class TestGetContainerSuggestions:

    def test_returns_only_containers(self, mgr):
        """Only nodes with time_mode='inherited' are returned."""
        from next_callbacks import get_container_suggestions
        _build_container_with_children(mgr, "TopGoal")
        mgr.add_node(_make_node("PlainLeaf", value=9, interest=9))

        results = get_container_suggestions(count=10)
        names = [n.name for n in results]
        assert "TopGoal" in names
        assert "PlainLeaf" not in names
        for n in results:
            assert n.time_mode == 'inherited'

    def test_ranked_by_total_value(self, mgr):
        """Container with richer descendant cascade ranks higher."""
        from next_callbacks import get_container_suggestions
        _build_container_with_children(mgr, "Rich", n_children=4)
        _build_container_with_children(mgr, "Sparse", n_children=1)

        results = get_container_suggestions(count=10)
        names = [n.name for n in results]
        assert names.index("Rich") < names.index("Sparse")

    def test_excludes_done_containers(self, mgr):
        """Containers with status=Done are filtered out."""
        from next_callbacks import get_container_suggestions
        mgr.add_node(_make_node("DoneContainer", time_mode='inherited',
                                status="Done"))
        _build_container_with_children(mgr, "OpenContainer")

        results = get_container_suggestions(count=10)
        names = [n.name for n in results]
        assert "DoneContainer" not in names
        assert "OpenContainer" in names

    def test_excludes_dormant(self, mgr):
        """Dormant containers are filtered out."""
        from next_callbacks import get_container_suggestions
        mgr.add_node(_make_node("Dormant", time_mode='inherited', dormant=1))
        _build_container_with_children(mgr, "Active")

        results = get_container_suggestions(count=10)
        names = [n.name for n in results]
        assert "Dormant" not in names
        assert "Active" in names

    def test_respects_exclude_names(self, mgr):
        """Names in exclude_names are filtered out (for dedup against pinned/priority)."""
        from next_callbacks import get_container_suggestions
        _build_container_with_children(mgr, "Pinned")
        _build_container_with_children(mgr, "Other")

        results = get_container_suggestions(count=10, exclude_names={"Pinned"})
        names = [n.name for n in results]
        assert "Pinned" not in names
        assert "Other" in names

    def test_count_caps_results(self, mgr):
        """count limits the number of returned containers."""
        from next_callbacks import get_container_suggestions
        for i in range(7):
            _build_container_with_children(mgr, f"C{i}", n_children=2)

        results = get_container_suggestions(count=3)
        assert len(results) == 3

    def test_total_value_populated(self, mgr):
        """Returned containers have a total_value attribute set by scoring."""
        from next_callbacks import get_container_suggestions
        _build_container_with_children(mgr, "G")

        results = get_container_suggestions(count=10)
        assert len(results) >= 1
        for n in results:
            assert hasattr(n, 'total_value')
            assert n.total_value > 0

    def test_strict_container_included(self, mgr):
        """Strict is_container (both modes inherited) is still surfaced."""
        from next_callbacks import get_container_suggestions
        mgr.add_node(_make_node("Strict", time_mode='inherited',
                                value_mode='inherited'))
        mgr.add_node(_make_node("Strict_Child", value=8, interest=8))
        mgr.add_edge("Strict_Child", "Strict", EDGE_NEEDS_HARD)

        results = get_container_suggestions(count=10)
        names = [n.name for n in results]
        assert "Strict" in names

    def test_milestones_excluded(self, mgr):
        """Milestones with time_mode='inherited' are excluded — they are
        single-event checkpoints, not capacity containers."""
        from next_callbacks import get_container_suggestions
        mgr.add_node(_make_node("ChkPoint", type="Milestone",
                                time_mode='inherited', value=9, interest=9))
        _build_container_with_children(mgr, "RealGoal", container_type="Goal")

        results = get_container_suggestions(count=10)
        names = [n.name for n in results]
        assert "ChkPoint" not in names
        assert "RealGoal" in names
