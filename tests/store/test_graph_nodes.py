"""Adding, reading, updating, deleting and renaming nodes."""
import pytest
from skilltree.store import database
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from skilltree.store.graph.manager import GraphManager
from skilltree.store import settings
from support.graphs import make_node


# ============================================================================
# Node CRUD
# ============================================================================

class TestNodeCRUD:
    def test_add_and_get_node(self, mgr):
        mgr.add_node(make_node("Alpha"))
        result = mgr.get_node("Alpha")
        assert result is not None
        assert result.name == "Alpha"
        assert result.type == "Learn"

    def test_add_duplicate_raises(self, mgr):
        mgr.add_node(make_node("Alpha"))
        with pytest.raises(ValueError, match="already exists"):
            mgr.add_node(make_node("Alpha"))

    def test_update_node(self, mgr):
        mgr.add_node(make_node("Alpha", value=3))
        mgr.update_node(make_node("Alpha", value=9))
        result = mgr.get_node("Alpha")
        assert result.value == 9

    def test_delete_node(self, mgr):
        mgr.add_node(make_node("Alpha"))
        mgr.delete_node("Alpha")
        assert mgr.get_node("Alpha") is None

    def test_delete_node_removes_edges(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.delete_node("A")
        assert len(mgr.get_edges()) == 0

    def test_delete_node_full_reference_cleanup(self, mgr):
        """Pinning the implicit FK-CASCADE + settings.NODE_NAME_SETTINGS
        contract: every table or settings list that references the deleted node
        must have no trace of it after delete_node returns."""
        from skilltree.store.events import EventManager
        from skilltree.domain.models import Event
        em = EventManager(GraphManager())

        # Set up X with edges in/out, an alias, an event triggered by X,
        # an EventNode attachment, and X as a priority goal — covering every
        # reference path delete_node has to clean.
        mgr.add_node(make_node("X", type="Goal"))
        mgr.add_node(make_node("U"))
        mgr.add_node(make_node("D"))
        mgr.add_edge("U", "X", EDGE_NEEDS_HARD)   # incoming
        mgr.add_edge("X", "D", EDGE_NEEDS_HARD)   # outgoing
        mgr.set_aliases("X", ["X-Alias"])
        em.add_event(Event(name="EvtX", trigger_nodes=["X"]))
        mgr.add_node(make_node("Dormant", status="Open"))
        em.add_node_to_event("EvtX", "Dormant", delay_days=0)
        settings.PRIORITY_GOALS.set(["X"])

        mgr.delete_node("X")

        # Node row gone
        assert mgr.get_node("X") is None
        # Edges referencing X (in either direction) gone
        assert all(e['source'] != "X" and e['target'] != "X" for e in mgr.get_edges())
        # Aliases gone (FK CASCADE)
        with mgr.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Aliases WHERE node_name=?", ("X",))
            assert cursor.fetchone()[0] == 0
            # EventNodes referencing X (none in this test, but ensure none leak)
            cursor.execute("SELECT COUNT(*) FROM EventNodes WHERE node_name=?", ("X",))
            assert cursor.fetchone()[0] == 0
        # Trigger set is emptied by FK cascade (event demotes to manual)
        evt = em.get_event("EvtX")
        assert evt is not None
        assert evt.trigger_nodes == []
        # Priority goals list cleaned
        assert "X" not in settings.PRIORITY_GOALS.get()

    def test_get_all_nodes(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        assert len(mgr.get_all_nodes()) == 3

    def test_get_nonexistent_returns_none(self, mgr):
        assert mgr.get_node("DoesNotExist") is None

    # Written around the Resource sections new databases used to start with.
    @pytest.mark.usefixtures("legacy_resource_sections")
    def test_update_preserves_resource_links(self, mgr):
        links = {"obsidian": ["notes/a.md"], "drive": ["https://drive.google.com/x"]}
        mgr.add_node(make_node("A", resource_links=links))
        assert mgr.get_node("A").resource_links == links
        # An update carries no links of its own and must not clear them.
        mgr.update_node(make_node("A", value=9))
        result = mgr.get_node("A")
        assert result.value == 9
        assert result.resource_links == links

    def test_add_node_rejects_none_context(self, mgr):
        with pytest.raises(ValueError, match="must have a context"):
            mgr.add_node(make_node("NoCtx", context=None))

    def test_add_node_rejects_empty_context(self, mgr):
        with pytest.raises(ValueError, match="must have a context"):
            mgr.add_node(make_node("EmptyCtx", context=""))

    def test_update_node_rejects_none_context(self, mgr):
        mgr.add_node(make_node("A"))
        with pytest.raises(ValueError, match="must have a context"):
            mgr.update_node(make_node("A", context=None))


# ============================================================================
# Node Rename (delete old + re-add under new name)
# ============================================================================

class TestNodeRename:
    """Tests the rename_node flow used by both Nodes and Goals tab renames."""

    def _rename(self, mgr, old_name, new_name, edges_from_form=None):
        """Helper that mirrors what confirm_rename_node does in callbacks.py."""
        old = mgr.get_node(old_name)
        assert old is not None
        mgr.rename_node(old_name, new_name)
        new_node = make_node(new_name, type=old.type, description=old.description,
                              value=old.value, interest=old.interest, difficulty=old.difficulty,
                              status=old.status, context=old.context,
                              time_o=old.time_o, time_m=old.time_m, time_p=old.time_p)
        mgr.update_node(new_node)
        if edges_from_form:
            mgr.sync_edges(new_name, **edges_from_form)

    def test_rename_preserves_attributes(self, mgr):
        mgr.add_node(make_node("OldName", description="desc", value=8,
                                interest=3, difficulty=7, context="Mind"))
        self._rename(mgr, "OldName", "NewName")
        assert mgr.get_node("OldName") is None
        new = mgr.get_node("NewName")
        assert new is not None
        assert new.description == "desc"
        assert new.value == 8
        assert new.interest == 3
        assert new.difficulty == 7
        assert new.context == "Mind"

    def test_rename_rewires_outgoing_edges(self, mgr):
        """When B is renamed to B2, B2 should still hard-need A."""
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # The UI form would still list A as a hard prerequisite
        self._rename(mgr, "B", "B2", edges_from_form={
            'needs_hard': ["A"], 'needs_soft': [], 'supports_hard': [],
            'supports_soft': [], 'helps': []})
        edges = mgr.get_edges()
        assert any(e['source'] == "A" and e['target'] == "B2" for e in edges)
        assert not any(e['target'] == "B" for e in edges)

    def test_rename_rewires_incoming_edges(self, mgr):
        """When A is renamed to A2, B should still hard-need A2 (via sync on B)."""
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # Rename A — the supports direction is handled by the form
        self._rename(mgr, "A", "A2", edges_from_form={
            'needs_hard': [], 'needs_soft': [], 'supports_hard': ["B"],
            'supports_soft': [], 'helps': []})
        edges = mgr.get_edges()
        assert any(e['source'] == "A2" and e['target'] == "B" for e in edges)
        assert not any(e['source'] == "A" for e in edges)

    def test_rename_preserves_state_cascade(self, mgr):
        """Renaming a Done prereq should keep the dependent Open, not Blocked."""
        mgr.add_node(make_node("Prereq", status="Done"))
        mgr.add_node(make_node("Dep"))
        mgr.add_edge("Prereq", "Dep", EDGE_NEEDS_HARD)
        assert mgr.get_node("Dep").status == "Open"
        self._rename(mgr, "Prereq", "Prereq2", edges_from_form={
            'needs_hard': [], 'needs_soft': [], 'supports_hard': ["Dep"],
            'supports_soft': [], 'helps': []})
        assert mgr.get_node("Dep").status == "Open"

    def test_rename_undone_prereq_blocks_dependent(self, mgr):
        """Renaming an incomplete prereq should keep the dependent Blocked."""
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("Dep"))
        mgr.add_edge("Prereq", "Dep", EDGE_NEEDS_HARD)
        assert mgr.get_node("Dep").status == "Blocked"
        self._rename(mgr, "Prereq", "Prereq2", edges_from_form={
            'needs_hard': [], 'needs_soft': [], 'supports_hard': ["Dep"],
            'supports_soft': [], 'helps': []})
        assert mgr.get_node("Dep").status == "Blocked"

    def test_rename_old_node_removed(self, mgr):
        mgr.add_node(make_node("Old"))
        self._rename(mgr, "Old", "New")
        assert mgr.get_node("Old") is None
        assert mgr.get_node("New") is not None

    def test_rename_without_sync_preserves_edges(self, mgr):
        """Goal tab rename path: rename_node + update_node without sync_edges.
        All edges must survive the rename."""
        mgr.add_node(make_node("Goal1", type="Goal"))
        mgr.add_node(make_node("SubA"))
        mgr.add_node(make_node("SubB"))
        mgr.add_edge("SubA", "Goal1", EDGE_NEEDS_HARD)
        mgr.add_edge("SubB", "Goal1", EDGE_NEEDS_HARD)

        # Rename without sync_edges (Goal tab path)
        mgr.rename_node("Goal1", "Goal2")
        new_node = make_node("Goal2", type="Goal")
        mgr.update_node(new_node)

        edges = mgr.get_edges()
        assert any(e['source'] == "SubA" and e['target'] == "Goal2" for e in edges)
        assert any(e['source'] == "SubB" and e['target'] == "Goal2" for e in edges)
        assert not any(e['target'] == "Goal1" for e in edges)
        assert mgr.get_node("Goal1") is None
        assert mgr.get_node("Goal2") is not None


    def test_rename_preserves_soft_edges(self, mgr):
        """Soft-need edges (source→renamed) and (renamed→target) both survive."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)   # B soft-needs A
        mgr.add_edge("B", "C", EDGE_NEEDS_SOFT)   # C soft-needs B

        mgr.rename_node("B", "B2")
        mgr.update_node(make_node("B2"))

        edges = mgr.get_edges()
        assert any(e['source'] == "A" and e['target'] == "B2" for e in edges), \
            "A→B2 soft edge must survive rename"
        assert any(e['source'] == "B2" and e['target'] == "C" for e in edges), \
            "B2→C soft edge must survive rename"
        assert not any(e['source'] == "B" or e['target'] == "B" for e in edges), \
            "Old name B must not appear in any edge after rename"

    def test_rename_preserves_helps_edges(self, mgr):
        """Helps edges referencing the renamed node are updated on both sides."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_HELPS)

        mgr.rename_node("A", "A2")
        mgr.update_node(make_node("A2"))

        edges = mgr.get_edges()
        assert any(e['source'] == "A2" and e['target'] == "B" and e['type'] == EDGE_HELPS
                   for e in edges), "A2→B Helps edge must survive rename"
        assert not any(e['source'] == "A" or e['target'] == "A" for e in edges), \
            "Old name A must not appear in any edge after rename"

    def test_rename_preserves_deep_goal_subtree(self, mgr):
        """Renaming a goal preserves edges across multiple levels of the subtree.
        This is the exact scenario from the goal-tab rename bug: all subtasks
        were deleted because delete_node removed edges."""
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_node(make_node("Mid"))
        mgr.add_node(make_node("Leaf"))
        mgr.add_edge("Mid", "Goal", EDGE_NEEDS_HARD)   # Mid is a direct subtask
        mgr.add_edge("Leaf", "Mid", EDGE_NEEDS_HARD)   # Leaf is a transitive subtask

        # Goal-tab rename path: no sync_edges
        mgr.rename_node("Goal", "Goal2")
        mgr.update_node(make_node("Goal2", type="Goal"))

        subtree = mgr.get_goal_subtree("Goal2")
        assert "Mid" in subtree, "Direct subtask Mid must be in Goal2's subtree"
        assert "Leaf" in subtree, "Transitive subtask Leaf must be in Goal2's subtree"
        assert mgr.get_node("Goal") is None
        assert mgr.get_node("Goal2") is not None

    def test_rename_event_trigger_reference_updated(self, mgr):
        """If an Event's trigger set references the renamed node, it is updated."""
        from skilltree.store.events import EventManager
        from skilltree.domain.models import Event

        mgr.add_node(make_node("TriggerNode"))
        em = EventManager(GraphManager())
        em.add_event(Event(
            name="TestEvent",
            trigger_nodes=["TriggerNode"],
            status="Pending"
        ))

        mgr.rename_node("TriggerNode", "TriggerRenamed")

        # Read the trigger table directly to verify the reference moved
        with database.get_connection() as conn:
            rows = conn.execute(
                "SELECT node_name FROM EventTriggerNodes WHERE event_name='TestEvent'"
            ).fetchall()
        assert [r[0] for r in rows] == ["TriggerRenamed"], \
            "Event trigger nodes must be updated when the referenced node is renamed"
