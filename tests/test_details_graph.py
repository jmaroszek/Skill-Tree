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
        )
        assert _node_ids(elements) == {"Selected"}

    def test_done_shown_does_not_chain_through_downstream_helps(self, mgr):
        """Under seed-only Helps semantics, a Helps edge from a downstream
        Hard prereq (Bridge --Helps-- Orphan1) must NOT cascade into the
        partner's own prereq tree. Helps only fires at the goal's seed step,
        and Selected has no direct Helps partners."""
        self._setup_bridge_scenario(mgr)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=["include"],
            global_filters={},
        )
        assert _node_ids(elements) == {"Selected", "Bridge"}

    def test_synergies_off_prunes_helps_leak(self, mgr):
        """Turning off Synergies disables Helps traversal, which independently
        prevents the orphan cluster from being pulled in."""
        self._setup_bridge_scenario(mgr)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=[],
            global_filters={},
        )
        assert _node_ids(elements) == {"Selected", "Bridge"}

    def test_reachability_uses_enabled_edge_types_only(self, mgr):
        """If Synergies is off, a Helps-only edge between two otherwise-
        filtered-in nodes must NOT count toward reachability — otherwise a
        hidden toggle would silently reintroduce the very nodes it's meant
        to exclude."""
        mgr.add_node(_make_node("Selected"))
        mgr.add_node(_make_node("Mid"))
        mgr.add_node(_make_node("Tail", status="Done"))
        mgr.add_edge("Mid", "Selected", EDGE_NEEDS_HARD)
        # Tail is only linked to Mid via Helps; Synergies off should exclude it.
        mgr.add_edge("Mid", "Tail", EDGE_HELPS)
        elements = _build_graph_elements(
            selected_node="Selected",
            include_soft_val=["include"],
            include_synergies_val=[],
            global_filters={},
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
        )
        assert _node_ids(elements) == {"Target", "HardDep"}

    def test_depth_one_restricts_to_direct_children(self, mgr):
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
            max_depth=1,
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
        )
        nodes = _node_ids(elements)
        for el in elements:
            if 'source' in el['data']:
                assert el['data']['source'] in nodes
                assert el['data']['target'] in nodes


class TestDependencyViewTraversal:
    def test_synergy_seeds_only_from_root_then_follows_needs(self, mgr):
        for name in ("Root", "Partner", "PartnerNeed", "Other", "OtherNeed"):
            mgr.add_node(_make_node(name))
        mgr.add_edge("Root", "Partner", EDGE_HELPS)
        mgr.add_edge("PartnerNeed", "Partner", EDGE_NEEDS_HARD)
        mgr.add_edge("Partner", "Other", EDGE_HELPS)
        mgr.add_edge("OtherNeed", "Other", EDGE_NEEDS_HARD)

        view = mgr.get_dependency_view(
            "Root", include_soft=True, include_synergies=True)

        assert view["node_names"] == {"Root", "Partner", "PartnerNeed"}
        assert view["depth_by_name"] == {
            "Root": 0, "Partner": 1, "PartnerNeed": 2}

    def test_depth_uses_enabled_relationships_only(self, mgr):
        for name in ("Root", "Direct", "Grand"):
            mgr.add_node(_make_node(name))
        mgr.add_edge("Direct", "Root", EDGE_NEEDS_HARD)
        mgr.add_edge("Grand", "Direct", EDGE_NEEDS_HARD)
        mgr.add_edge("Grand", "Root", EDGE_NEEDS_SOFT)

        hard_only = mgr.get_dependency_view(
            "Root", include_soft=False, max_depth=1)
        with_soft = mgr.get_dependency_view(
            "Root", include_soft=True, max_depth=1)

        assert hard_only["node_names"] == {"Root", "Direct"}
        assert with_soft["node_names"] == {"Root", "Direct", "Grand"}

    def test_filtered_bridge_prunes_descendants(self, mgr):
        mgr.add_node(_make_node("Root"))
        mgr.add_node(_make_node("Bridge", status="Done"))
        mgr.add_node(_make_node("Tail", status="Done"))
        mgr.add_edge("Bridge", "Root", EDGE_NEEDS_HARD)
        mgr.add_edge("Tail", "Bridge", EDGE_NEEDS_HARD)

        view = mgr.get_dependency_view("Root", filters={"hide_done": True})

        assert view["node_names"] == {"Root"}
        assert view["discovery_edges"] == set()

    def test_cross_links_change_edges_not_nodes(self, mgr):
        for name in ("Root", "A", "B"):
            mgr.add_node(_make_node(name))
        mgr.add_edge("A", "Root", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Root", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)

        without = _build_graph_elements(
            "Root", ["include"], [], show_cross_links=False)
        with_links = _build_graph_elements(
            "Root", ["include"], [], show_cross_links=True)

        assert _node_ids(without) == _node_ids(with_links) == {"Root", "A", "B"}
        assert _edge_ids(without) == {
            "A_Root_Needs_Hard", "B_Root_Needs_Hard"}
        assert _edge_ids(with_links) == {
            "A_Root_Needs_Hard", "B_Root_Needs_Hard", "A_B_Needs_Hard"}

    def test_depth_limited_goal_progress_remains_hard_only(self, mgr):
        mgr.add_node(_make_node("Goal", type="Goal", time_mode="inherited"))
        mgr.add_node(_make_node("DoneDirect"))
        mgr.add_node(_make_node("OpenGrand", status="Done"))
        mgr.add_node(_make_node("SoftDirect", status="Done"))
        mgr.add_edge("DoneDirect", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("OpenGrand", "DoneDirect", EDGE_NEEDS_HARD)
        mgr.add_edge("SoftDirect", "Goal", EDGE_NEEDS_SOFT)

        depth_one = mgr.get_goal_completion(
            "Goal", include_soft=False, max_depth=1)
        all_depths = mgr.get_goal_completion(
            "Goal", include_soft=False, max_depth=None)

        assert (depth_one["done"], depth_one["total"], depth_one["pct"]) == (0, 1, 0)
        assert (all_depths["done"], all_depths["total"], all_depths["pct"]) == (1, 2, 50)


# ============================================================================
# Details-tab Milestones roster
# ============================================================================

from details_callbacks import _build_milestones_section
from details_layout import build_milestone_tile


class TestBuildMilestonesSection:
    """The (section_style, bottom_toggles_style, tiles) tuple — picks
    Milestones out of the already-filtered subtree the caller built, and
    flips the canonical bottom-toggle wrapper visibility opposite to the
    milestones section so the toggles always sit with the topmost header."""

    def test_hidden_when_no_milestones(self, mgr):
        # subtask list contains no Milestones → strip hidden, bottom toggles
        # take over (visible).
        mgr.add_node(_make_node("L1", type="Learn"))
        mgr.add_node(_make_node("L2", type="Learn"))
        section_style, bottom_style, tiles = _build_milestones_section(
            [mgr.get_node("L1"), mgr.get_node("L2")],
            parent_name="L1", edges=[])
        assert section_style == {"display": "none"}
        assert bottom_style == {}  # default = visible
        assert tiles == []

    def test_hidden_for_empty_subtree(self, mgr):
        section_style, bottom_style, tiles = _build_milestones_section(
            [], parent_name=None, edges=[])
        assert section_style == {"display": "none"}
        assert bottom_style == {}
        assert tiles == []

    def test_visible_with_tiles(self, mgr):
        # Milestones present → section visible AND bottom toggles hidden
        # (top toggles inside the milestones header take over).
        mgr.add_node(_make_node("Goal", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("M1", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("M2", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("L", type="Learn"))
        for src in ("M1", "M2", "L"):
            mgr.add_edge(src, "Goal", EDGE_NEEDS_HARD)
        section_style, bottom_style, tiles = _build_milestones_section(
            [mgr.get_node("M1"), mgr.get_node("M2"), mgr.get_node("L")],
            parent_name="Goal", edges=mgr.get_edges())
        assert section_style == {"display": "block"}
        assert bottom_style == {"display": "none"}
        assert len(tiles) == 2

    def test_picks_only_milestone_type(self, mgr):
        mgr.add_node(_make_node("M", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("L", type="Learn"))
        mgr.add_node(_make_node("A", type="Action"))
        mgr.add_node(_make_node("R", type="Resource"))
        subtask_nodes = [mgr.get_node(n) for n in ("M", "G", "L", "A", "R")]
        _section_style, _bottom_style, tiles = _build_milestones_section(
            subtask_nodes, parent_name=None, edges=[])
        assert len(tiles) == 1

    def test_includes_every_milestone_in_resolved_view(self, mgr):
        mgr.add_node(_make_node("Goal", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("Direct", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("Grand", type="Milestone", time_mode='inherited'))
        mgr.add_edge("Direct", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("Grand", "Direct", EDGE_NEEDS_HARD)
        subtask_nodes = [mgr.get_node("Direct"), mgr.get_node("Grand")]
        _section_style, _bottom_style, tiles = _build_milestones_section(
            subtask_nodes, parent_name="Goal", edges=mgr.get_edges())
        assert len(tiles) == 2

    def test_depth_limited_caller_can_supply_only_direct_milestones(self, mgr):
        mgr.add_node(_make_node("Goal", type="Goal", time_mode='inherited'))
        mgr.add_node(_make_node("Direct", type="Milestone", time_mode='inherited'))
        mgr.add_node(_make_node("Grand", type="Milestone", time_mode='inherited'))
        mgr.add_edge("Direct", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("Grand", "Direct", EDGE_NEEDS_HARD)
        subtask_nodes = [mgr.get_node("Direct")]
        _section_style, _bottom_style, tiles = _build_milestones_section(
            subtask_nodes, parent_name="Goal", edges=mgr.get_edges())
        assert len(tiles) == 1
        assert tiles[0].id["index"] == "Direct"

    def test_excludes_done_milestone_when_filtered_out(self, mgr):
        mgr.add_node(_make_node("OpenMS", type="Milestone", time_mode='inherited'))
        _section_style, _bottom_style, tiles = _build_milestones_section(
            [mgr.get_node("OpenMS")],
            parent_name=None, edges=[])
        assert len(tiles) == 1

    def test_sorts_open_before_blocked_before_done(self, mgr):
        mgr.add_node(_make_node("DoneA", type="Milestone",
                                time_mode='inherited', status="Done"))
        mgr.add_node(_make_node("OpenB", type="Milestone",
                                time_mode='inherited', status="Open"))
        mgr.add_node(_make_node("BlockedA", type="Milestone",
                                time_mode='inherited', status="Blocked"))
        mgr.add_node(_make_node("OpenA", type="Milestone",
                                time_mode='inherited', status="Open"))
        subtask_nodes = [mgr.get_node(n)
                         for n in ("DoneA", "OpenB", "BlockedA", "OpenA")]
        _section_style, _bottom_style, tiles = _build_milestones_section(
            subtask_nodes, parent_name=None, edges=[])
        ordered = [t.id["index"] for t in tiles]
        assert ordered == ["OpenA", "OpenB", "BlockedA", "DoneA"]


class TestBuildMilestoneTile:
    """The tile renderer — progress bar present/absent, status pill, glyph."""

    def test_with_progress_bar(self, mgr):
        ms = _make_node("M", type="Milestone", time_mode='inherited')
        completion = {"total": 4, "done": 2, "pct": 50, "remaining_time": 6.0}
        tile = build_milestone_tile(ms, completion)
        # Tile is an html.Div with a pattern-matched id for the click callback.
        assert tile.id == {"type": "details-milestone-tile", "index": "M"}
        # Rendered as a string the percentage and "·" separator should appear.
        rendered = str(tile)
        assert "50%" in rendered
        assert "·" in rendered

    def test_no_progress_bar_when_no_prereqs(self, mgr):
        ms = _make_node("Squat 1.5x BW", type="Milestone", time_mode='inherited')
        completion = {"total": 0, "done": 0, "pct": 0, "remaining_time": 0.0}
        tile = build_milestone_tile(ms, completion)
        rendered = str(tile)
        # No progress bar text — the "X% · Yh" stats row is gated on total > 0.
        assert "0% ·" not in rendered

    def test_handles_none_completion(self, mgr):
        # Defensive: if completion is None or empty, treat as no-prereqs leaf.
        ms = _make_node("M", type="Milestone", time_mode='inherited')
        tile_none = build_milestone_tile(ms, None)
        tile_empty = build_milestone_tile(ms, {})
        assert tile_none.id == {"type": "details-milestone-tile", "index": "M"}
        assert tile_empty.id == {"type": "details-milestone-tile", "index": "M"}
