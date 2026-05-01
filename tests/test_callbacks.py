"""
Tests for callback helper functions extracted during refactoring.

Tests pure helpers (no DB) and action handlers (need temp DB via the callbacks module's
global `manager` instance).
"""

from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD
from callbacks import generate_elements, manager
from callback_helpers import (
    build_filters, is_filters_active, node_options, handle_save, handle_delete,
    handle_toggle_done, handle_group_delete,
)
from config import DEFAULT_NODE_COLORS


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    """Creates a temporary database for each test, ensuring full isolation."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = False
    database.init_db()
    yield tmp_db_path


def _make_node(name: str = "TestNode", **overrides: Any) -> Node:
    defaults: dict[str, Any] = dict(
        name=name, type="Learn", description="A test node",
        value=5, time_o=1.0, time_m=2.0, time_p=4.0,
        interest=5, difficulty=5, status="Open", context="Mind"
    )
    defaults.update(overrides)
    return Node(**defaults)


# ============================================================================
# build_filters
# ============================================================================

class TestBuildFilters:
    def test_all_defaults_empty_dict(self):
        result = build_filters("All", "All", [])
        assert result == {}

    def test_empty_lists_empty_dict(self):
        result = build_filters([], [], [])
        assert result == {}

    def test_context_filter(self):
        result = build_filters("Mind", "All", [])
        assert result == {"context": ["Mind"]}

    def test_context_filter_multi(self):
        result = build_filters(["Mind", "Body"], [], [])
        assert result == {"context": ["Mind", "Body"]}

    def test_none_context_maps_to_none(self):
        result = build_filters("None", "All", [])
        assert result == {"context": [None]}

    def test_hide_done(self):
        result = build_filters("All", "All", ["hide_done"])
        assert result == {"hide_done": True}

    def test_min_value(self):
        result = build_filters("All", "All", [], f_value=5)
        assert result == {"min_value": 5}

    def test_min_interest(self):
        result = build_filters("All", "All", [], f_interest=3)
        assert result == {"min_interest": 3}

    def test_max_time(self):
        result = build_filters("All", "All", [], f_time=10)
        assert result == {"max_time": 10.0}

    def test_max_difficulty(self):
        result = build_filters("All", "All", [], f_difficulty="7")
        assert result == {"max_difficulty": 7}

    def test_invalid_time_ignored(self):
        result = build_filters("All", "All", [], f_time="abc")
        assert "max_time" not in result

    def test_subcontext_filter(self):
        result = build_filters("All", "Rational", [])
        assert result == {"subcontext": ["Rational"]}

    def test_subcontext_filter_multi(self):
        result = build_filters("All", ["Rational", "Creative"], [])
        assert result == {"subcontext": ["Rational", "Creative"]}

    def test_subcontext_all_ignored(self):
        result = build_filters("All", "All", [])
        assert "subcontext" not in result

    def test_composite_subcontext_multi_context_multi_sub(self):
        # Regression: each composite "ctx::sub" value must be routed to its own
        # context. Previously bare "Rational" values forced a reverse-lookup via
        # ConfigManager which could silently drop an entry and fall back to
        # "show all nodes of that context" for Mind.
        result = build_filters(
            ["Mind", "STEM"],
            ["Mind::Rational", "STEM::Math", "STEM::Data Science"],
            [],
        )
        assert result == {
            "context_subcontext_union": [
                ("Mind", ["Rational"]),
                ("STEM", ["Math", "Data Science"]),
            ]
        }

    def test_composite_subcontext_selective_union_fallback(self):
        # Mind has no subs in the selection → falls back to None (show all Mind).
        result = build_filters(["Mind", "STEM"], ["STEM::Math"], [])
        assert result == {
            "context_subcontext_union": [("Mind", None), ("STEM", ["Math"])]
        }

    def test_composite_subcontext_without_context_flattens(self):
        # No context selected → flatten to a plain subcontext filter (name-only).
        result = build_filters(
            [], ["Mind::Rational", "STEM::Math"], []
        )
        assert result == {"subcontext": ["Rational", "Math"]}

    def test_legacy_plain_subcontext_with_context(self):
        # Legacy state (plain subcontext names, no "::") — apply the list to
        # every selected context.
        result = build_filters(["Mind"], ["Rational"], [])
        assert result == {"context_subcontext_union": [("Mind", ["Rational"])]}


# ============================================================================
# is_filters_active
# ============================================================================

class TestIsFiltersActive:
    def test_all_defaults_inactive(self):
        # Mirrors the "Clear Filters" reset state.
        assert is_filters_active(
            node_type=[], context=[], subcontext=[], goal=[],
            community="All", community_method="components",
            value=1, interest=1, difficulty=10, time=None,
            done=["hide_done"],
        ) is False

    def test_no_args_inactive(self):
        # Defensive: when a caller (e.g. Details canvas) passes nothing for
        # filters that don't affect it, the helper must not flag.
        assert is_filters_active() is False

    def test_node_type_active(self):
        assert is_filters_active(node_type=["Learn"]) is True

    def test_context_active(self):
        assert is_filters_active(context=["Mind"]) is True

    def test_subcontext_active(self):
        assert is_filters_active(subcontext=["Rational"]) is True

    def test_goal_active(self):
        assert is_filters_active(goal=["Read War and Peace"]) is True

    def test_community_all_inactive(self):
        assert is_filters_active(community="All") is False

    def test_community_specific_active(self):
        assert is_filters_active(community="3") is True

    def test_orphans_method_active(self):
        # "Orphans" mode narrows visible nodes even with community="All".
        assert is_filters_active(community="All",
                                 community_method="orphans") is True

    def test_default_method_inactive(self):
        assert is_filters_active(community_method="components") is False

    def test_min_value_active(self):
        assert is_filters_active(value=2) is True

    def test_min_value_at_floor_inactive(self):
        assert is_filters_active(value=1) is False

    def test_min_interest_active(self):
        assert is_filters_active(interest=5) is True

    def test_max_difficulty_active(self):
        assert is_filters_active(difficulty=7) is True

    def test_max_difficulty_at_ceiling_inactive(self):
        assert is_filters_active(difficulty=10) is False

    def test_max_time_active(self):
        assert is_filters_active(time=20) is True

    def test_max_time_zero_inactive(self):
        assert is_filters_active(time=0) is False

    def test_done_default_inactive(self):
        assert is_filters_active(done=["hide_done"]) is False

    def test_done_toggled_off_active(self):
        # Showing completed tasks is a deviation from the default.
        assert is_filters_active(done=[]) is True


# ============================================================================
# node_options
# ============================================================================

class TestNodeOptions:
    def test_basic_options(self):
        nodes = [_make_node("A"), _make_node("B")]
        result = node_options(nodes)
        assert result == [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]

    def test_exclude_node(self):
        nodes = [_make_node("A"), _make_node("B"), _make_node("C")]
        result = node_options(nodes, exclude="B")
        names = [r['value'] for r in result]
        assert "B" not in names
        assert len(result) == 2

    def test_empty_list(self):
        assert node_options([]) == []


# ============================================================================
# handle_save
# ============================================================================

class TestHandleSave:
    def test_creates_new_node(self):
        msg = handle_save(manager,
            "NewNode", "Learn", "desc", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
            [], [], [], [], []
        )
        assert "Added" in msg
        assert manager.get_node("NewNode") is not None

    def test_updates_existing_node(self):
        manager.add_node(_make_node("Existing", value=3))
        msg = handle_save(manager,
            "Existing", "Learn", "updated desc", 9, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
            [], [], [], [], []
        )
        assert "Updated" in msg
        assert manager.get_node("Existing").value == 9

    def test_syncs_edges(self):
        manager.add_node(_make_node("A"))
        manager.add_node(_make_node("B", status="Done"))
        handle_save(manager,
            "A", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
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
        manager.add_node(_make_node("ToDelete"))
        msg = handle_delete(manager,"ToDelete")
        assert "Deleted" in msg
        assert manager.get_node("ToDelete") is None

    def test_returns_message_with_name(self):
        manager.add_node(_make_node("MyNode"))
        msg = handle_delete(manager,"MyNode")
        assert "MyNode" in msg


# ============================================================================
# handle_toggle_done
# ============================================================================

class TestHandleToggleDone:
    def test_toggle_open_to_done(self):
        manager.add_node(_make_node("A", status="Open"))
        msg = handle_toggle_done(manager,{"id": "A"})
        assert manager.get_node("A").status == "Done"
        assert "Done" in msg

    def test_toggle_done_to_open(self):
        manager.add_node(_make_node("A", status="Done"))
        msg = handle_toggle_done(manager,{"id": "A"})
        assert manager.get_node("A").status == "Open"
        assert "Open" in msg


# ============================================================================
# handle_group_delete
# ============================================================================

class TestHandleGroupDelete:
    def test_deletes_multiple(self):
        manager.add_node(_make_node("A"))
        manager.add_node(_make_node("B"))
        manager.add_node(_make_node("C"))
        msg = handle_group_delete(manager,'["A","B"]')
        assert manager.get_node("A") is None
        assert manager.get_node("B") is None
        assert manager.get_node("C") is not None
        assert "2" in msg

    def test_empty_list_no_error(self):
        msg = handle_group_delete(manager,"[]")
        assert msg == ""

    def test_timestamp_suffix_stripped(self):
        manager.add_node(_make_node("X"))
        msg = handle_group_delete(manager,'["X"]|1234567890')
        assert manager.get_node("X") is None
        assert "1" in msg


# ============================================================================
# generate_elements — Resource node color logic
# ============================================================================

class TestResourceNodeColor:
    """Tests that nodes get the right color in generate_elements.

    Expected colors are resolved from DEFAULT_NODE_COLORS rather than
    hardcoded so a future palette tweak doesn't break these checks; the
    intent of each test is encoded in which key it pulls (Resource vs.
    Done vs. Blocked, etc.).
    """

    def test_resource_open_gets_resource_color(self):
        manager.add_node(_make_node("Res1", type="Resource", status="Open"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Res1')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Resource']

    def test_resource_done_gets_done_color(self):
        manager.add_node(_make_node("Res2", type="Resource", status="Done"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Res2')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Done']

    def test_resource_blocked_gets_blocked_color(self):
        """Blocked resource nodes should follow the Blocked color, like other blocked types."""
        manager.add_node(_make_node("Blocker", type="Learn", status="Open"))
        manager.add_node(_make_node("Res3", type="Resource", status="Open"))
        manager.add_edge("Blocker", "Res3", EDGE_NEEDS_HARD)
        # Res3 should now be Blocked
        assert manager.get_node("Res3").status == "Blocked"
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Res3')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Blocked']

    def test_goal_node_gets_goal_color(self):
        manager.add_node(_make_node("G1", type="Goal"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'G1')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Goal']

    def test_normal_node_gets_status_color(self):
        manager.add_node(_make_node("Learn1", type="Learn", status="Open"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Learn1')
        assert node_el['data']['color'] == DEFAULT_NODE_COLORS['Open']


# ============================================================================
# handle_save — no resources parameter
# ============================================================================

class TestHandleSaveNoResources:
    """Tests that handle_save works without a resources edge parameter."""

    def test_save_with_needs_edges_only(self):
        manager.add_node(_make_node("Prereq", status="Done"))
        msg = handle_save(manager,
            "NewRes", "Resource", "A resource", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
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
            [], "Mind", None, None, None, None,
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
            [], "Mind", None, None, None, None,
            [], [], [], [], []
        )
        assert manager.get_node("Node").time_p == 64.0

        # Simulate the user changing pessimistic from 64 to 80 and saving
        handle_save(manager,
            "Node", "Learn", "", 5, 16.0, 32.0, 80.0, 5, 5,
            [], "Mind", None, None, None, None,
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
            ["Done"], "Work", "Research", None, None, None,
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
        assert node.context == "Work"
        assert node.subcontext == "Research"

    def test_second_save_does_not_revert_to_first_save_values(self):
        """Two successive saves with different values — the second must win.
        Guards against any caching or no-op update path."""
        handle_save(manager,"N", "Learn", "v1", 3, 1.0, 2.0, 4.0, 3, 3,
                     [], "Mind", None, None, None, None, [], [], [], [], [])
        handle_save(manager,"N", "Learn", "v2", 8, 5.0, 10.0, 20.0, 8, 8,
                     [], "Mind", None, None, None, None, [], [], [], [], [])
        node = manager.get_node("N")
        assert node.description == "v2"
        assert node.value == 8
        assert node.time_o == 5.0
        assert node.time_m == 10.0
        assert node.time_p == 20.0

    def test_edge_list_update_replaces_previous_edges(self):
        """When edges change on save, the new edge list fully replaces the old one.
        Guards against edges accumulating instead of being replaced."""
        manager.add_node(_make_node("A", status="Done"))
        manager.add_node(_make_node("B", status="Done"))
        manager.add_node(_make_node("C", status="Done"))

        # First save: C is a hard prereq
        handle_save(manager,"Target", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None, None, None,
                     ["C"], [], [], [], [])
        edges = manager.get_edges()
        hard_prereqs = [e['source'] for e in edges
                        if e['target'] == "Target" and e['type'] == EDGE_NEEDS_HARD]
        assert hard_prereqs == ["C"]

        # Second save: user removes C and adds A, B
        handle_save(manager,"Target", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None, None, None,
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
                     [], "Mind", None, None, None, None,
                     [], [], [], [], [])
        node = manager.get_node("Node")
        assert node.time_mode == 'manual'

    def test_inherited_time_mode_persisted(self):
        """Saving with time_mode='inherited' stores it in the DB."""
        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None, None, None,
                     [], [], [], [], [], time_mode='inherited')
        node = manager.get_node("Node")
        assert node.time_mode == 'inherited'

    def test_time_mode_updated_on_save(self):
        """Changing time_mode from manual to inherited on update persists."""
        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None, None, None,
                     [], [], [], [], [], time_mode='manual')
        assert manager.get_node("Node").time_mode == 'manual'

        handle_save(manager,"Node", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], "Mind", None, None, None, None,
                     [], [], [], [], [], time_mode='inherited')
        assert manager.get_node("Node").time_mode == 'inherited'

    def test_goal_node_with_inherited_time(self):
        """Goal nodes can use inherited time mode."""
        handle_save(manager,"MyGoal", "Goal", "a goal", 5, 0, 0, 0, 5, 5,
                     [], "Mind", None, None, None, None,
                     [], [], [], [], [], time_mode='inherited')
        node = manager.get_node("MyGoal")
        assert node.type == "Goal"
        assert node.time_mode == 'inherited'

    def test_milestone_node_with_inherited_time(self):
        """Milestone nodes use inherited time mode (mirrors Goal)."""
        handle_save(manager, "MyMilestone", "Milestone", "a milestone",
                    8, 0, 0, 0, 7, 5,
                    [], "Body", None, None, None, None,
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
                    [], "Mind", None, None, None, None,
                    [], [], [], [], [], time_mode='manual')
        assert manager.get_node("Convertible").type == "Learn"

        # Convert-type: same name + new type, time_mode='inherited' as the
        # upstream resolver would supply for a Milestone.
        handle_save(manager, "Convertible", "Milestone", "now a milestone",
                    8, 0, 0, 0, 8, 7,
                    [], "Mind", None, None, None, None,
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
            [], "Mind", None, None, None, None,
            [], [], [], [], []
        )
        assert "Added" in msg
        node = manager.get_node("NewGoal")
        assert node is not None
        assert node.type == "Goal"

    def test_goal_node_with_dependencies(self):
        """Goal nodes can have prerequisites just like other types."""
        manager.add_node(_make_node("Task1", status="Done"))
        manager.add_node(_make_node("Task2"))
        handle_save(manager,
            "MyGoal", "Goal", "", 5, 0, 0, 0, 5, 5,
            [], "Mind", None, None, None, None,
            ["Task1", "Task2"], [], [], [], []
        )
        edges = manager.get_edges()
        hard = [e for e in edges if e['target'] == "MyGoal" and e['type'] == EDGE_NEEDS_HARD]
        assert len(hard) == 2

    def test_goal_node_in_generate_elements(self):
        """Goal nodes appear in the generated Cytoscape elements."""
        manager.add_node(_make_node("GoalNode", type="Goal"))
        elements = generate_elements()
        node_ids = [e['data']['id'] for e in elements if 'source' not in e['data']]
        assert "GoalNode" in node_ids
