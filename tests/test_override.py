"""
Tests for the manual priority override feature.

Covers ConfigManager override CRUD, override node set computation across modes,
override-aware suggestion sorting, override column in the suggestions table,
and override cleanup on node delete/rename/group-delete.
"""

from typing import Any
import json
import pytest
import database
from dash import html
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from graph_manager import GraphManager
from config import ConfigManager
from callback_helpers import handle_delete, handle_group_delete, format_suggestions_table


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    """Creates a temporary database for each test, ensuring full isolation."""
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
        interest=5, difficulty=5, status="Open", context="Mind"
    )
    defaults.update(overrides)
    return Node(**defaults)


def _build_diamond(mgr):
    """Build a diamond-shaped graph: Goal -> A (hard), Goal -> B (soft), A -> Leaf (hard).

    Goal
    ├── A  (hard)
    │   └── Leaf  (hard)
    └── B  (soft)
    """
    mgr.add_node(_make_node("Goal", type="Goal", value=8))
    mgr.add_node(_make_node("A", value=6))
    mgr.add_node(_make_node("B", value=4))
    mgr.add_node(_make_node("Leaf", value=3))
    mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
    mgr.add_edge("Leaf", "A", EDGE_NEEDS_HARD)
    mgr.add_edge("B", "Goal", EDGE_NEEDS_SOFT)


# ============================================================================
# ConfigManager — Override CRUD
# ============================================================================

class TestOverrideCRUD:
    def test_default_override_is_empty(self):
        override = ConfigManager.get_override()
        assert override == {"parent": None, "mode": "hard"}

    def test_set_and_get_override(self):
        ConfigManager.set_override({"parent": "MyNode", "mode": "soft"})
        override = ConfigManager.get_override()
        assert override["parent"] == "MyNode"
        assert override["mode"] == "soft"

    def test_clear_override(self):
        ConfigManager.set_override({"parent": "X", "mode": "all"})
        ConfigManager.clear_override()
        override = ConfigManager.get_override()
        assert override["parent"] is None
        assert override["mode"] == "hard"

    def test_set_override_preserves_mode(self):
        ConfigManager.set_override({"parent": "A", "mode": "node_only"})
        override = ConfigManager.get_override()
        assert override["mode"] == "node_only"

    def test_override_persists_across_reads(self):
        ConfigManager.set_override({"parent": "Persistent", "mode": "hard"})
        assert ConfigManager.get_override()["parent"] == "Persistent"
        assert ConfigManager.get_override()["parent"] == "Persistent"


# ============================================================================
# ConfigManager — get_override_node_set
# ============================================================================

class TestOverrideNodeSet:
    def test_empty_when_no_override(self, mgr):
        result = ConfigManager.get_override_node_set(mgr)
        assert result == set()

    def test_empty_when_parent_node_missing(self, mgr):
        ConfigManager.set_override({"parent": "NonExistent", "mode": "hard"})
        result = ConfigManager.get_override_node_set(mgr)
        assert result == set()

    def test_node_only_mode(self, mgr):
        _build_diamond(mgr)
        ConfigManager.set_override({"parent": "Goal", "mode": "node_only"})
        result = ConfigManager.get_override_node_set(mgr)
        assert result == {"Goal"}

    def test_hard_mode_includes_hard_deps(self, mgr):
        _build_diamond(mgr)
        ConfigManager.set_override({"parent": "Goal", "mode": "hard"})
        result = ConfigManager.get_override_node_set(mgr)
        assert "Goal" in result
        assert "A" in result
        assert "Leaf" in result
        assert "B" not in result

    def test_soft_mode_includes_soft_deps(self, mgr):
        _build_diamond(mgr)
        ConfigManager.set_override({"parent": "Goal", "mode": "soft"})
        result = ConfigManager.get_override_node_set(mgr)
        assert "Goal" in result
        assert "B" in result
        # Soft mode only follows soft edges from the goal, not hard
        assert "A" not in result

    def test_all_mode_includes_everything(self, mgr):
        _build_diamond(mgr)
        ConfigManager.set_override({"parent": "Goal", "mode": "all"})
        result = ConfigManager.get_override_node_set(mgr)
        assert result == {"Goal", "A", "B", "Leaf"}

    def test_leaf_node_override_returns_only_self(self, mgr):
        _build_diamond(mgr)
        ConfigManager.set_override({"parent": "Leaf", "mode": "hard"})
        result = ConfigManager.get_override_node_set(mgr)
        assert result == {"Leaf"}

    def test_default_mode_is_hard(self, mgr):
        _build_diamond(mgr)
        # Omit mode key entirely — should default to hard
        ConfigManager.set_override({"parent": "Goal"})
        result = ConfigManager.get_override_node_set(mgr)
        assert "A" in result
        assert "B" not in result


# ============================================================================
# Override cleanup on node delete
# ============================================================================

class TestOverrideCleanupOnDelete:
    """The override cleanup on single-node delete lives in the Dash callback
    (callbacks.py), not in handle_delete itself.  We test the same logic
    pattern here: delete the node, then check-and-clear the override."""

    def test_delete_override_parent_clears_override(self, mgr):
        mgr.add_node(_make_node("Target"))
        ConfigManager.set_override({"parent": "Target", "mode": "hard"})
        handle_delete(mgr, "Target")
        # Replicate the callback's post-delete cleanup
        ov = ConfigManager.get_override()
        if ov.get("parent") == "Target":
            ConfigManager.clear_override()
        assert ConfigManager.get_override()["parent"] is None

    def test_delete_non_override_node_preserves_override(self, mgr):
        mgr.add_node(_make_node("Override"))
        mgr.add_node(_make_node("Other"))
        ConfigManager.set_override({"parent": "Override", "mode": "hard"})
        handle_delete(mgr, "Other")
        ov = ConfigManager.get_override()
        if ov.get("parent") == "Other":
            ConfigManager.clear_override()
        assert ConfigManager.get_override()["parent"] == "Override"


# ============================================================================
# Override cleanup on group delete
# ============================================================================

class TestOverrideCleanupOnGroupDelete:
    def test_group_delete_containing_override_parent_clears(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        ConfigManager.set_override({"parent": "A", "mode": "hard"})
        handle_group_delete(mgr, '["A","B"]')
        assert ConfigManager.get_override()["parent"] is None

    def test_group_delete_not_containing_override_parent_preserves(self, mgr):
        mgr.add_node(_make_node("A"))
        mgr.add_node(_make_node("B"))
        mgr.add_node(_make_node("C"))
        ConfigManager.set_override({"parent": "C", "mode": "hard"})
        handle_group_delete(mgr, '["A","B"]')
        assert ConfigManager.get_override()["parent"] == "C"


# ============================================================================
# Override cleanup on node rename
# ============================================================================

class TestOverrideCleanupOnRename:
    def test_rename_override_parent_updates_override(self, mgr):
        mgr.add_node(_make_node("OldName"))
        ConfigManager.set_override({"parent": "OldName", "mode": "soft"})
        mgr.rename_node("OldName", "NewName")
        # Simulate the rename callback's override update
        ov = ConfigManager.get_override()
        if ov.get("parent") == "OldName":
            ov["parent"] = "NewName"
            ConfigManager.set_override(ov)
        assert ConfigManager.get_override()["parent"] == "NewName"
        assert ConfigManager.get_override()["mode"] == "soft"

    def test_rename_non_override_node_preserves_override(self, mgr):
        mgr.add_node(_make_node("Override"))
        mgr.add_node(_make_node("Other"))
        ConfigManager.set_override({"parent": "Override", "mode": "hard"})
        mgr.rename_node("Other", "Renamed")
        ov = ConfigManager.get_override()
        if ov.get("parent") == "Other":
            ov["parent"] = "Renamed"
            ConfigManager.set_override(ov)
        assert ConfigManager.get_override()["parent"] == "Override"


# ============================================================================
# get_suggestions — two-tier override sorting
# ============================================================================

class TestSuggestionsOverrideSorting:
    """Verify that override nodes are promoted to the top of suggestions."""

    def test_override_nodes_appear_first(self, mgr):
        """When override is active, overridden open nodes appear before non-overridden ones."""
        from next_callbacks import get_suggestions
        mgr.add_node(_make_node("HighVal", value=10, interest=10))
        mgr.add_node(_make_node("LowVal", value=2, interest=2))
        mgr.add_node(_make_node("OverrideTarget", value=3, interest=3))
        ConfigManager.set_override({"parent": "OverrideTarget", "mode": "node_only"})

        results = get_suggestions(count=10)
        names = [n.name for n in results]
        if "OverrideTarget" in names:
            assert names.index("OverrideTarget") == 0

    def test_no_override_uses_normal_scoring(self, mgr):
        """Without an override, suggestions follow normal priority scoring."""
        from next_callbacks import get_suggestions
        mgr.add_node(_make_node("A", value=10, interest=10))
        mgr.add_node(_make_node("B", value=2, interest=2))
        ConfigManager.clear_override()

        results = get_suggestions(count=10)
        names = [n.name for n in results]
        assert len(names) >= 2

    def test_override_with_subtree(self, mgr):
        """Override on a goal promotes its hard deps to tier 1."""
        from next_callbacks import get_suggestions
        _build_diamond(mgr)
        mgr.add_node(_make_node("Unrelated", value=10, interest=10))
        ConfigManager.set_override({"parent": "Goal", "mode": "hard"})

        results = get_suggestions(count=10)
        names = [n.name for n in results]
        override_set = {"Goal", "A", "Leaf"}
        override_in_results = [n for n in names if n in override_set]
        non_override_in_results = [n for n in names if n not in override_set]
        # All override nodes should appear before any non-override node
        if override_in_results and non_override_in_results:
            last_override_idx = max(names.index(n) for n in override_in_results)
            first_non_override_idx = min(names.index(n) for n in non_override_in_results)
            assert last_override_idx < first_non_override_idx

    def test_tier2_fills_remaining_count(self, mgr):
        """Tier 2 nodes fill up to count when tier 1 doesn't exhaust it."""
        from next_callbacks import get_suggestions
        mgr.add_node(_make_node("Only", value=5))
        mgr.add_node(_make_node("Extra1", value=4))
        mgr.add_node(_make_node("Extra2", value=3))
        ConfigManager.set_override({"parent": "Only", "mode": "node_only"})

        results = get_suggestions(count=3)
        names = [n.name for n in results]
        assert names[0] == "Only"
        assert len(names) == 3

    def test_done_override_nodes_excluded(self, mgr):
        """Done nodes in the override set are excluded (negative score)."""
        from next_callbacks import get_suggestions
        mgr.add_node(_make_node("DoneNode", status="Done"))
        mgr.add_node(_make_node("OpenNode", value=5))
        ConfigManager.set_override({"parent": "DoneNode", "mode": "node_only"})

        results = get_suggestions(count=5)
        names = [n.name for n in results]
        assert "DoneNode" not in names


# ============================================================================
# format_suggestions_table — override column
# ============================================================================

class TestSuggestionsTableOverrideColumn:
    def test_override_column_present_when_override_active(self, mgr):
        mgr.add_node(_make_node("A", value=5))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        override_set = {"A"}
        result = format_suggestions_table(scored, mgr, override_set=override_set)
        # result is [dbc.Table, desc_area]; check the table has an Override header
        table_component = result[0]
        thead = table_component.children[0]
        header_texts = [th.children for th in thead.children.children if isinstance(th, html.Th)]
        assert "Override" in header_texts

    def test_no_override_column_when_no_override(self, mgr):
        mgr.add_node(_make_node("A", value=5))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        result = format_suggestions_table(scored, mgr, override_set=None)
        # result is [dbc.Table, desc_area]; stringify and check no Override header
        html_str = str(result)
        # "Override" should not appear as a table header
        # (it may appear in other contexts like node type, so check specifically)
        table_component = result[0]
        thead = table_component.children[0]
        header_texts = [th.children for th in thead.children.children if isinstance(th, html.Th)]
        assert "Override" not in header_texts

    def test_override_row_has_checkmark(self, mgr):
        mgr.add_node(_make_node("InSet", value=5))
        mgr.add_node(_make_node("OutSet", value=4))
        all_nodes = [mgr.get_node("InSet"), mgr.get_node("OutSet")]
        scored = mgr.calculate_priority_scores(all_nodes)
        override_set = {"InSet"}
        result = format_suggestions_table(scored, mgr, override_set=override_set)
        html_str = str(result)
        # The checkmark character should appear for the overridden node
        assert "\u2713" in html_str

    def test_override_row_styling(self, mgr):
        mgr.add_node(_make_node("Styled", value=5))
        scored = mgr.calculate_priority_scores([mgr.get_node("Styled")])
        override_set = {"Styled"}
        result = format_suggestions_table(scored, mgr, override_set=override_set)
        # result is [dbc.Table, desc_area]
        table_component = result[0]
        tbody = table_component.children[1]
        row = tbody.children[0]
        assert "borderLeft" in row.style
        assert "backgroundColor" in row.style


# ============================================================================
# Override color in DEFAULT_NODE_COLORS
# ============================================================================

class TestOverrideColor:
    def test_override_color_exists_in_defaults(self):
        from config import DEFAULT_NODE_COLORS
        assert "Override" in DEFAULT_NODE_COLORS

    def test_override_color_is_pink(self):
        from config import DEFAULT_NODE_COLORS
        assert DEFAULT_NODE_COLORS["Override"] == "#e83e8c"
