"""
Tests for callback helper functions extracted during refactoring.

Tests pure helpers (no DB) and action handlers (need temp DB via the callbacks module's
global `manager` instance).
"""

from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from callbacks import (
    _build_filters, _node_options, _handle_save, _handle_delete,
    _handle_toggle_done, _handle_group_delete, generate_elements, manager
)


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
# _build_filters
# ============================================================================

class TestBuildFilters:
    def test_all_defaults_empty_dict(self):
        result = _build_filters("All", "All", [])
        assert result == {}

    def test_empty_lists_empty_dict(self):
        result = _build_filters([], [], [])
        assert result == {}

    def test_context_filter(self):
        result = _build_filters("Mind", "All", [])
        assert result == {"context": ["Mind"]}

    def test_context_filter_multi(self):
        result = _build_filters(["Mind", "Body"], [], [])
        assert result == {"context": ["Mind", "Body"]}

    def test_none_context_maps_to_none(self):
        result = _build_filters("None", "All", [])
        assert result == {"context": [None]}

    def test_hide_done(self):
        result = _build_filters("All", "All", ["hide_done"])
        assert result == {"hide_done": True}

    def test_min_value(self):
        result = _build_filters("All", "All", [], f_value=5)
        assert result == {"min_value": 5}

    def test_min_interest(self):
        result = _build_filters("All", "All", [], f_interest=3)
        assert result == {"min_interest": 3}

    def test_max_time(self):
        result = _build_filters("All", "All", [], f_time=10)
        assert result == {"max_time": 10.0}

    def test_max_difficulty(self):
        result = _build_filters("All", "All", [], f_difficulty="7")
        assert result == {"max_difficulty": 7}

    def test_invalid_time_ignored(self):
        result = _build_filters("All", "All", [], f_time="abc")
        assert "max_time" not in result

    def test_subcontext_filter(self):
        result = _build_filters("All", "Rational", [])
        assert result == {"subcontext": ["Rational"]}

    def test_subcontext_filter_multi(self):
        result = _build_filters("All", ["Rational", "Creative"], [])
        assert result == {"subcontext": ["Rational", "Creative"]}

    def test_subcontext_all_ignored(self):
        result = _build_filters("All", "All", [])
        assert "subcontext" not in result


# ============================================================================
# _node_options
# ============================================================================

class TestNodeOptions:
    def test_basic_options(self):
        nodes = [_make_node("A"), _make_node("B")]
        result = _node_options(nodes)
        assert result == [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]

    def test_exclude_node(self):
        nodes = [_make_node("A"), _make_node("B"), _make_node("C")]
        result = _node_options(nodes, exclude="B")
        names = [r['value'] for r in result]
        assert "B" not in names
        assert len(result) == 2

    def test_empty_list(self):
        assert _node_options([]) == []


# ============================================================================
# _handle_save
# ============================================================================

class TestHandleSave:
    def test_creates_new_node(self):
        msg = _handle_save(
            "NewNode", "Learn", "desc", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
            [], [], [], [], []
        )
        assert "Added" in msg
        assert manager.get_node("NewNode") is not None

    def test_updates_existing_node(self):
        manager.add_node(_make_node("Existing", value=3))
        msg = _handle_save(
            "Existing", "Learn", "updated desc", 9, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
            [], [], [], [], []
        )
        assert "Updated" in msg
        assert manager.get_node("Existing").value == 9

    def test_syncs_edges(self):
        manager.add_node(_make_node("A"))
        manager.add_node(_make_node("B", status="Done"))
        msg = _handle_save(
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
# _handle_delete
# ============================================================================

class TestHandleDelete:
    def test_deletes_node(self):
        manager.add_node(_make_node("ToDelete"))
        msg = _handle_delete("ToDelete")
        assert "Deleted" in msg
        assert manager.get_node("ToDelete") is None

    def test_returns_message_with_name(self):
        manager.add_node(_make_node("MyNode"))
        msg = _handle_delete("MyNode")
        assert "MyNode" in msg


# ============================================================================
# _handle_toggle_done
# ============================================================================

class TestHandleToggleDone:
    def test_toggle_open_to_done(self):
        manager.add_node(_make_node("A", status="Open"))
        msg = _handle_toggle_done({"id": "A"})
        assert manager.get_node("A").status == "Done"
        assert "Done" in msg

    def test_toggle_done_to_open(self):
        manager.add_node(_make_node("A", status="Done"))
        msg = _handle_toggle_done({"id": "A"})
        assert manager.get_node("A").status == "Open"
        assert "Open" in msg


# ============================================================================
# _handle_group_delete
# ============================================================================

class TestHandleGroupDelete:
    def test_deletes_multiple(self):
        manager.add_node(_make_node("A"))
        manager.add_node(_make_node("B"))
        manager.add_node(_make_node("C"))
        msg = _handle_group_delete('["A","B"]')
        assert manager.get_node("A") is None
        assert manager.get_node("B") is None
        assert manager.get_node("C") is not None
        assert "2" in msg

    def test_empty_list_no_error(self):
        msg = _handle_group_delete("[]")
        assert msg == ""

    def test_timestamp_suffix_stripped(self):
        manager.add_node(_make_node("X"))
        msg = _handle_group_delete('["X"]|1234567890')
        assert manager.get_node("X") is None
        assert "1" in msg


# ============================================================================
# generate_elements — Resource node color logic
# ============================================================================

class TestResourceNodeColor:
    """Tests that Resource nodes get the correct color in generate_elements."""

    def test_resource_open_gets_purple(self):
        manager.add_node(_make_node("Res1", type="Resource", status="Open"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Res1')
        assert node_el['data']['color'] == '#9b59b6'

    def test_resource_done_gets_green(self):
        manager.add_node(_make_node("Res2", type="Resource", status="Done"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Res2')
        # Done color
        assert node_el['data']['color'] == '#198754'

    def test_resource_blocked_gets_purple(self):
        """Blocked resource nodes should still be purple, not the Blocked red."""
        manager.add_node(_make_node("Blocker", type="Learn", status="Open"))
        manager.add_node(_make_node("Res3", type="Resource", status="Open"))
        manager.add_edge("Blocker", "Res3", EDGE_NEEDS_HARD)
        # Res3 should now be Blocked
        assert manager.get_node("Res3").status == "Blocked"
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Res3')
        assert node_el['data']['color'] == '#9b59b6'

    def test_goal_node_gets_yellow(self):
        manager.add_node(_make_node("G1", type="Goal"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'G1')
        assert node_el['data']['color'] == '#ffc107'

    def test_normal_node_gets_status_color(self):
        manager.add_node(_make_node("Learn1", type="Learn", status="Open"))
        elements = generate_elements()
        node_el = next(e for e in elements if e['data'].get('id') == 'Learn1')
        # Open color
        assert node_el['data']['color'] == '#0d6efd'


# ============================================================================
# _handle_save — no resources parameter
# ============================================================================

class TestHandleSaveNoResources:
    """Tests that _handle_save works without a resources edge parameter."""

    def test_save_with_needs_edges_only(self):
        manager.add_node(_make_node("Prereq", status="Done"))
        msg = _handle_save(
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
# contract is: _handle_save must always write the exact values it receives,
# and get_node must return those exact values on the next read.
# ============================================================================

class TestSaveRoundTrip:
    """Regression tests verifying that saved values are faithfully stored and returned."""

    def test_time_estimates_stored_and_retrieved_accurately(self):
        """Exact time_o/m/p values round-trip through add → get_node."""
        _handle_save(
            "TimedNode", "Learn", "", 5, 40.0, 80.0, 160.0, 5, 5,
            [], None, None, None, None, None,
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
        _handle_save(
            "Node", "Learn", "", 5, 16.0, 32.0, 64.0, 5, 5,
            [], None, None, None, None, None,
            [], [], [], [], []
        )
        assert manager.get_node("Node").time_p == 64.0

        # Simulate the user changing pessimistic from 64 to 80 and saving
        _handle_save(
            "Node", "Learn", "", 5, 16.0, 32.0, 80.0, 5, 5,
            [], None, None, None, None, None,
            [], [], [], [], []
        )
        node = manager.get_node("Node")
        assert node.time_p == 80.0, (
            "Pessimistic estimate should be 80.0 after update, not the old value 64.0"
        )

    def test_all_scalar_fields_persisted_accurately(self):
        """Every user-editable field is faithfully stored and retrieved."""
        _handle_save(
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
        _handle_save("N", "Learn", "v1", 3, 1.0, 2.0, 4.0, 3, 3,
                     [], None, None, None, None, None, [], [], [], [], [])
        _handle_save("N", "Learn", "v2", 8, 5.0, 10.0, 20.0, 8, 8,
                     [], None, None, None, None, None, [], [], [], [], [])
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
        _handle_save("Target", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], None, None, None, None, None,
                     ["C"], [], [], [], [])
        edges = manager.get_edges()
        hard_prereqs = [e['source'] for e in edges
                        if e['target'] == "Target" and e['type'] == EDGE_NEEDS_HARD]
        assert hard_prereqs == ["C"]

        # Second save: user removes C and adds A, B
        _handle_save("Target", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
                     [], None, None, None, None, None,
                     ["A", "B"], [], [], [], [])
        edges = manager.get_edges()
        hard_prereqs = sorted(e['source'] for e in edges
                              if e['target'] == "Target" and e['type'] == EDGE_NEEDS_HARD)
        assert hard_prereqs == ["A", "B"], (
            "Edge list after second save must be exactly [A, B], not include stale C"
        )
