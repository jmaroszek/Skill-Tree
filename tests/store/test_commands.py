"""The commands the editor and the node menu run: save, delete, Done."""
import pytest
from skilltree.domain.models import EDGE_NEEDS_HARD
from skilltree.ui.canvas.elements import generate_elements
from skilltree.store.commands import (
    handle_save, handle_delete, handle_toggle_done, handle_group_delete,
)
from skilltree.store.graph.manager import GraphManager
from support.graphs import make_node


manager = GraphManager()


# ============================================================================
# handle_save
# ============================================================================

class TestHandleSave:
    def test_creates_new_node(self):
        msg = handle_save(manager,
            "NewNode", "Learn", "desc", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None,
            [], [], [], [], []
        )
        assert "Added" in msg
        assert manager.get_node("NewNode") is not None

    def test_updates_existing_node(self):
        manager.add_node(make_node("Existing", value=3))
        msg = handle_save(manager,
            "Existing", "Learn", "updated desc", 9, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None,
            [], [], [], [], []
        )
        assert "Updated" in msg
        assert manager.get_node("Existing").value == 9

    def test_syncs_edges(self):
        manager.add_node(make_node("A"))
        manager.add_node(make_node("B", status="Done"))
        handle_save(manager,
            "A", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None,
            ["B"], [], [], [], []  # B is a hard prereq of A
        )
        edges = manager.get_edges()
        hard = [e for e in edges if e['type'] == EDGE_NEEDS_HARD]
        assert len(hard) == 1
        assert hard[0]['source'] == "B"
        assert hard[0]['target'] == "A"


# ============================================================================
# handle_delete
# ============================================================================

class TestHandleDelete:
    def test_deletes_node(self):
        manager.add_node(make_node("ToDelete"))
        msg = handle_delete(manager,"ToDelete")
        assert "Deleted" in msg
        assert manager.get_node("ToDelete") is None

    def test_returns_message_with_name(self):
        manager.add_node(make_node("MyNode"))
        msg = handle_delete(manager,"MyNode")
        assert "MyNode" in msg

    def test_a_missing_node_is_an_error_not_a_success(self):
        with pytest.raises(ValueError, match="nothing was deleted"):
            handle_delete(manager, "Nobody")


# ============================================================================
# handle_toggle_done
# ============================================================================

class TestHandleToggleDone:
    def test_toggle_open_to_done(self):
        manager.add_node(make_node("A", status="Open"))
        msg = handle_toggle_done(manager,{"id": "A"})
        assert manager.get_node("A").status == "Done"
        assert "Done" in msg

    def test_toggle_done_to_open(self):
        manager.add_node(make_node("A", status="Done"))
        msg = handle_toggle_done(manager,{"id": "A"})
        assert manager.get_node("A").status == "Open"
        assert "Open" in msg


# ============================================================================
# handle_group_delete
# ============================================================================

class TestHandleGroupDelete:
    def test_deletes_multiple(self):
        manager.add_node(make_node("A"))
        manager.add_node(make_node("B"))
        manager.add_node(make_node("C"))
        msg = handle_group_delete(manager, ["A", "B"])
        assert manager.get_node("A") is None
        assert manager.get_node("B") is None
        assert manager.get_node("C") is not None
        assert "2" in msg

    def test_empty_list_no_error(self):
        msg = handle_group_delete(manager, [])
        assert msg == ""


# ============================================================================
# handle_save — no resources parameter
# ============================================================================

class TestHandleSaveNoResources:
    """Tests that handle_save works without a resources edge parameter."""

    def test_save_with_needs_edges_only(self):
        manager.add_node(make_node("Prereq", status="Done"))
        msg = handle_save(manager,
            "NewRes", "Resource", "A resource", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None,
            ["Prereq"], [], [], [], []
        )
        assert "Added" in msg
        edges = manager.get_edges()
        assert len(edges) == 1
        assert edges[0]['type'] == EDGE_NEEDS_HARD
        assert edges[0]['source'] == "Prereq"


# ============================================================================
# Regression tests for Bug 1-3: node save round-trip accuracy
# The original bugs caused edited values to revert after save because the
# populate_editor callback re-fired with stale Cytoscape data. The DB-level
# contract is: handle_save must always write the exact values it receives,
# and get_node must return those exact values on the next read.
# ============================================================================

class TestSaveRoundTrip:
    """Regression tests verifying that saved values are faithfully stored and returned."""

    def test_time_estimates_stored_and_retrieved_accurately(self):
        """Exact time_o/m/p values round-trip through add → get_node."""
        handle_save(manager,
            "TimedNode", "Learn", "", 5, 40.0, 80.0, 160.0, 5, 5,
            [], "Mind", None, None,
            [], [], [], [], []
        )
        node = manager.get_node("TimedNode")
        assert node is not None
        assert node.time_o == 40.0
        assert node.time_m == 80.0
        assert node.time_p == 160.0

    def test_updated_time_estimates_replace_old_values(self):
        """Saving updated time estimates overwrites the previous values in the DB.
        This directly guards against the stale-data bug where the form appeared
        to save but the DB retained the original values."""
        handle_save(manager,
            "Node", "Learn", "", 5, 16.0, 32.0, 64.0, 5, 5,
            [], "Mind", None, None,
            [], [], [], [], []
        )
        assert manager.get_node("Node").time_p == 64.0

        # Simulate the user changing pessimistic from 64 to 80 and saving
        handle_save(manager,
            "Node", "Learn", "", 5, 16.0, 32.0, 80.0, 5, 5,
            [], "Mind", None, None,
            [], [], [], [], []
        )
        node = manager.get_node("Node")
        assert node.time_p == 80.0, (
            "Pessimistic estimate should be 80.0 after update, not the old value 64.0"
        )

    def test_all_scalar_fields_persisted_accurately(self):
        """Every user-editable field is faithfully stored and retrieved."""
        handle_save(manager,
            "FullNode", "Goal", "A description", 9, 10.0, 20.0, 40.0, 7, 3,
            ["Done"], "Mind", "Mindfulness", None,
            [], [], [], [], [], 0
        )
        node = manager.get_node("FullNode")
        assert node.type == "Goal"
        assert node.description == "A description"
        assert node.value == 9
        assert node.time_o == 10.0
        assert node.time_m == 20.0
        assert node.time_p == 40.0
        assert node.interest == 7
        assert node.difficulty == 3
        assert node.status == "Done"
        assert node.context == "Mind"
        assert node.subcontext == "Mindfulness"

    def test_invalid_subcontext_for_context_is_cleared(self):
        """Saving a node with a subcontext that doesn't belong to the chosen
        context drops the subcontext rather than persisting an orphan pair."""
        handle_save(manager,
            "Orphan", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", "Life Skills", None,
            [], [], [], [], []
        )
        node = manager.get_node("Orphan")
        assert node.context == "Mind"
        assert node.subcontext is None

    def test_second_save_does_not_revert_to_first_save_values(self):
        """Two successive saves with different values — the second must win.
        Guards against any caching or no-op update path."""
        handle_save(manager,"N", "Learn", "v1", 3, 1.0, 2.0, 4.0, 3, 3,
                     [], "Mind", None, None, [], [], [], [], [])
        handle_save(manager,"N", "Learn", "v2", 8, 5.0, 10.0, 20.0, 8, 8,
                     [], "Mind", None, None, [], [], [], [], [])
        node = manager.get_node("N")
        assert node.description == "v2"
        assert node.value == 8
        assert node.time_o == 5.0
        assert node.time_m == 10.0
        assert node.time_p == 20.0

    def test_edge_list_update_replaces_previous_edges(self):
        """When edges change on save, the new edge list fully replaces the old one.
        Guards against edges accumulating instead of being replaced."""
        manager.add_node(make_node("A", status="Done"))
        manager.add_node(make_node("B", status="Done"))
        manager.add_node(make_node("C", status="Done"))

        # First save: C is a hard prereq
        handle_save(manager,"Target", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None,
                     ["C"], [], [], [], [])
        edges = manager.get_edges()
        hard_prereqs = [e['source'] for e in edges
                        if e['target'] == "Target" and e['type'] == EDGE_NEEDS_HARD]
        assert hard_prereqs == ["C"]

        # Second save: user removes C and adds A, B
        handle_save(manager,"Target", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None,
                     ["A", "B"], [], [], [], [])
        edges = manager.get_edges()
        hard_prereqs = sorted(e['source'] for e in edges
                              if e['target'] == "Target" and e['type'] == EDGE_NEEDS_HARD)
        assert hard_prereqs == ["A", "B"], (
            "Edge list after second save must be exactly [A, B], not include stale C"
        )


# ============================================================================
# handle_save — time_mode persistence
# ============================================================================

class TestHandleSaveTimeMode:
    def test_default_time_mode_is_manual(self):
        """Saving without explicit time_mode defaults to 'manual'."""
        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None,
                     [], [], [], [], [])
        node = manager.get_node("Node")
        assert node.time_mode == 'manual'

    def test_inherited_time_mode_persisted(self):
        """Saving with time_mode='inherited' stores it in the DB."""
        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None,
                     [], [], [], [], [], time_mode='inherited')
        node = manager.get_node("Node")
        assert node.time_mode == 'inherited'

    def test_time_mode_updated_on_save(self):
        """Changing time_mode from manual to inherited on update persists."""
        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None,
                     [], [], [], [], [], time_mode='manual')
        assert manager.get_node("Node").time_mode == 'manual'

        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None,
                     [], [], [], [], [], time_mode='inherited')
        assert manager.get_node("Node").time_mode == 'inherited'

    def test_goal_node_with_inherited_time(self):
        """Goal nodes can use inherited time mode."""
        handle_save(manager,"MyGoal", "Goal", "a goal", 5, 0, 0, 0, 5, 5,
                     [], "Mind", None, None,
                     [], [], [], [], [], time_mode='inherited')
        node = manager.get_node("MyGoal")
        assert node.type == "Goal"
        assert node.time_mode == 'inherited'

    def test_milestone_node_with_inherited_time(self):
        """Milestone nodes use inherited time mode (mirrors Goal)."""
        handle_save(manager, "MyMilestone", "Milestone", "a milestone",
                    8, 0, 0, 0, 7, 5,
                    [], "Body", None, None,
                    [], [], [], [], [], time_mode='inherited')
        node = manager.get_node("MyMilestone")
        assert node is not None
        assert node.type == "Milestone"
        assert node.time_mode == 'inherited'

    def test_convert_learn_to_milestone_via_save(self):
        """Saving an existing Learn again with type='Milestone' converts it.
        The save-layer time_mode resolution upstream forces 'inherited' for
        Milestones — here we just confirm the type-flip persists cleanly.
        """
        handle_save(manager, "Convertible", "Learn", "starts as learn",
                    5, 1.0, 2.0, 4.0, 5, 5,
                    [], "Mind", None, None,
                    [], [], [], [], [], time_mode='manual')
        assert manager.get_node("Convertible").type == "Learn"

        # Convert-type: same name + new type, time_mode='inherited' as the
        # upstream resolver would supply for a Milestone.
        handle_save(manager, "Convertible", "Milestone", "now a milestone",
                    8, 0, 0, 0, 8, 7,
                    [], "Mind", None, None,
                    [], [], [], [], [], time_mode='inherited')
        node = manager.get_node("Convertible")
        assert node.type == "Milestone"
        assert node.time_mode == 'inherited'


# ============================================================================
# Goal node creation from node editor
# ============================================================================

class TestGoalNodeCreation:
    def test_create_goal_node(self):
        """Goal nodes can be created via handle_save like any other type."""
        msg = handle_save(manager,
            "NewGoal", "Goal", "My goal", 8, 0, 0, 0, 7, 3,
            [], "Mind", None, None,
            [], [], [], [], []
        )
        assert "Added" in msg
        node = manager.get_node("NewGoal")
        assert node is not None
        assert node.type == "Goal"

    def test_goal_node_with_dependencies(self):
        """Goal nodes can have prerequisites just like other types."""
        manager.add_node(make_node("Task1", status="Done"))
        manager.add_node(make_node("Task2"))
        handle_save(manager,
            "MyGoal", "Goal", "", 5, 0, 0, 0, 5, 5,
            [], "Mind", None, None,
            ["Task1", "Task2"], [], [], [], []
        )
        edges = manager.get_edges()
        hard = [e for e in edges if e['target'] == "MyGoal" and e['type'] == EDGE_NEEDS_HARD]
        assert len(hard) == 2

    def test_goal_node_in_generate_elements(self, services):
        """Goal nodes appear in the generated Cytoscape elements."""
        manager.add_node(make_node("GoalNode", type="Goal"))
        elements = generate_elements(services.graph, services.events)
        node_ids = [e['data']['id'] for e in elements if 'source' not in e['data']]
        assert "GoalNode" in node_ids
