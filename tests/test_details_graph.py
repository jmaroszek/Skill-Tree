"""
Tests for the Details tab dependency graph builder (`_build_graph_elements`).

Focus is on the post-filter reachability invariant: the mini-graph must never
show nodes that are only connected to the selected node via a filtered-out
bridge. Without this invariant, hiding a Done node whose Helps edge is the
only link to a downstream cluster leaves the cluster floating as an apparent
"unrelated" subgraph.
"""

from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from graph_manager import GraphManager
from details_callbacks import _build_graph_elements


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


def _make_node(name: str, **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind",
    )
    defaults.update(overrides)
    return Node(**defaults)


def _node_ids(elements):
    return {el['data']['id'] for el in elements if 'source' not in el['data']}


def _edge_ids(elements):
    return {el['data']['id'] for el in elements if 'source' in el['data']}


# ============================================================================
# Post-filter reachability regression tests
# ============================================================================


class TestPostFilterReachability:
    """The bug: a Done `Bridge` node has a Helps edge to a cluster unrelated
    to the selected node's own hard-need subtree. Hiding Done nodes removes
    the bridge from the render, but the cluster would still be returned by
    `get_goal_subtree` (which walks the raw graph, ignoring filters). The
    mini-graph then shows the cluster as floating islands — exactly what the
    user reported. The fix: after filtering, drop any node no longer reachable
    from the selected node through the remaining edges.
    """

    def _setup_bridge_scenario(self, mgr):
        """Replicates the sandbox scenario that surfaced the bug.

        Selected -> Bridge (hard, Bridge is Done)
        Bridge <-Helps-> Orphan1
        Orphan2 -> Orphan1 (hard)
        Orphan3 -> Orphan2 (soft)
        """
        mgr.add_node(_make_node("Selected"))
        mgr.add_node(_make_node("Bridge", status="Done"))
        mgr.add_node(_make_node("Orphan1"))
        mgr.add_node(_make_node("Orphan2"))
        mgr.add_node(_make_node("Orphan3"))
        mgr.add_edge("Bridge", "Selected", EDGE_NEEDS_HARD)
        mgr.add_edge("Bridge", "Orphan1", EDGE_HELPS)
        mgr.add_edge("Orphan2", "Orphan1", EDGE_NEEDS_HARD)
        mgr.add_edge("Orphan3", "Orphan2", EDGE_NEEDS_SOFT)

    def test_hide_done_drops_orphans_when_bridge_filtered(self, mgr):
        """With hide_done active the Done Bridge disappears, and since it's
        the only path from Selected to the Orphan cluster, the orphans must
        also disappear."""
        self._setup_bridge_scenario(mgr)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=["include"],
            global_filters={"hide_done": True},
            include_transitive_val=["include"],
        )
        assert _node_ids(elements) == {"Selected"}

    def test_done_shown_keeps_full_chain(self, mgr):
        """Without hide_done, the bridge is visible and the full Helps-linked
        chain is correctly surfaced."""
        self._setup_bridge_scenario(mgr)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=["include"],
            global_filters={},
            include_transitive_val=["include"],
        )
        assert _node_ids(elements) == {
            "Selected", "Bridge", "Orphan1", "Orphan2", "Orphan3",
        }

    def test_synergies_off_prunes_helps_leak(self, mgr):
        """Turning off Synergies disables Helps traversal, which independently
        prevents the orphan cluster from being pulled in."""
        self._setup_bridge_scenario(mgr)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=[],
            global_filters={},
            include_transitive_val=["include"],
        )
        assert _node_ids(elements) == {"Selected", "Bridge"}

    def test_reachability_uses_enabled_edge_types_only(self, mgr):
        """If Synergies is off, a Helps-only edge between two otherwise-
        filtered-in nodes must NOT count toward reachability — otherwise a
        hidden toggle would silently reintroduce the very nodes it's meant
        to exclude."""
        mgr.add_node(_make_node("Selected"))
        mgr.add_node(_make_node("Mid"))
        mgr.add_node(_make_node("Tail"))
        mgr.add_edge("Mid", "Selected", EDGE_NEEDS_HARD)
        # Tail is only linked to Mid via Helps; Synergies off should exclude it.
        mgr.add_edge("Mid", "Tail", EDGE_HELPS)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=[],
            global_filters={},
            include_transitive_val=["include"],
        )
        assert _node_ids(elements) == {"Selected", "Mid"}


# ============================================================================
# General `_build_graph_elements` invariants
# ============================================================================


class TestBuildGraphElementsInvariants:
    def test_selected_node_always_present(self, mgr):
        """Even a selected node with no prereqs and filters that would normally
        hide it still appears — it's the anchor of the view."""
        mgr.add_node(_make_node("Solo", status="Done"))
        elements = _build_graph_elements(
            selected_node="Solo",
            include_soft_val=["include"],
            include_synergies_val=["include"],
            global_filters={"hide_done": True},
            include_transitive_val=["include"],
        )
        assert _node_ids(elements) == {"Solo"}

    def test_soft_toggle_off_excludes_soft_chain(self, mgr):
        mgr.add_node(_make_node("Target"))
        mgr.add_node(_make_node("HardDep"))
        mgr.add_node(_make_node("SoftDep"))
        mgr.add_edge("HardDep", "Target", EDGE_NEEDS_HARD)
        mgr.add_edge("SoftDep", "Target", EDGE_NEEDS_SOFT)
        elements = _build_graph_elements(
            selected_node="Target",
            include_soft_val=[],
            include_synergies_val=[],
            global_filters={},
            include_transitive_val=["include"],
        )
        assert _node_ids(elements) == {"Target", "HardDep"}

    def test_transitive_off_restricts_to_direct_children(self, mgr):
        mgr.add_node(_make_node("Root"))
        mgr.add_node(_make_node("Child"))
        mgr.add_node(_make_node("Grandchild"))
        mgr.add_edge("Child", "Root", EDGE_NEEDS_HARD)
        mgr.add_edge("Grandchild", "Child", EDGE_NEEDS_HARD)
        elements = _build_graph_elements(
            selected_node="Root",
            include_soft_val=["include"],
            include_synergies_val=["include"],
            global_filters={},
            include_transitive_val=[],
        )
        assert _node_ids(elements) == {"Root", "Child"}

    def test_edges_only_between_included_nodes(self, mgr):
        """No dangling edges: every rendered edge must connect two rendered
        nodes. Guards against a filter dropping a node but leaving its edge
        behind."""
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B", status="Done"))
        mgr.add_node(_make_node("C"))
        mgr.add_edge("B", "A", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "A", EDGE_NEEDS_HARD)
        elements = _build_graph_elements(
            selected_node="A",
            include_soft_val=["include"],
            include_synergies_val=["include"],
            global_filters={"hide_done": True},
            include_transitive_val=["include"],
        )
        nodes = _node_ids(elements)
        for el in elements:
            if 'source' in el['data']:
                assert el['data']['source'] in nodes
                assert el['data']['target'] in nodes
