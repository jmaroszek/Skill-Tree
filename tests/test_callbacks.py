"""
Tests for callback helper functions extracted during refactoring.

Tests pure helpers (no DB) and action handlers (need temp DB via the callbacks module's
global `manager` instance).
"""

from typing import Any
import pytest
import database
from models import Node, EDGE_NEEDS_HARD, EDGE_HELPS
from callbacks import (
    _build_filters, _node_options, _handle_save, _handle_delete,
    _handle_toggle_done, _handle_group_delete, manager
)


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    """Creates a temporary database for each test, ensuring full isolation."""
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
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

    def test_context_filter(self):
        result = _build_filters("Mind", "All", [])
        assert result == {"context": "Mind"}

    def test_none_context_maps_to_none(self):
        result = _build_filters("None", "All", [])
        assert result == {"context": None}

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
        assert result == {"subcontext": "Rational"}

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
            [], [], [], [], [], []
        )
        assert "Added" in msg
        assert manager.get_node("NewNode") is not None

    def test_updates_existing_node(self):
        manager.add_node(_make_node("Existing", value=3))
        msg = _handle_save(
            "Existing", "Learn", "updated desc", 9, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
            [], [], [], [], [], []
        )
        assert "Updated" in msg
        assert manager.get_node("Existing").value == 9

    def test_syncs_edges(self):
        manager.add_node(_make_node("A"))
        manager.add_node(_make_node("B", status="Done"))
        msg = _handle_save(
            "A", "Learn", "", 5, 1.0, 2.0, 4.0, 5, 5,
            [], "Mind", None, None, None, None,
            ["B"], [], [], [], [], []  # B is a hard prereq of A
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
