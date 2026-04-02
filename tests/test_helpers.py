"""
Tests for callback_helpers.py serialization functions and styles.py.

Tests pure functions that don't require a database.
"""

import json
import pytest
from callback_helpers import (
    parse_links, serialize_links,
    get_all_triggered_ids, should_open_editor, resolve_active_node_id,
)
from styles import stylesheet, mini_stylesheet


# ============================================================================
# parse_links
# ============================================================================

class TestParseLinks:
    def test_none_returns_single_empty(self):
        assert parse_links(None) == ['']

    def test_empty_string_returns_single_empty(self):
        assert parse_links('') == ['']

    def test_json_array(self):
        val = json.dumps(["path/a", "path/b"])
        assert parse_links(val) == ["path/a", "path/b"]

    def test_empty_json_array(self):
        assert parse_links('[]') == ['']

    def test_plain_string_fallback(self):
        assert parse_links("some/path.md") == ["some/path.md"]

    def test_invalid_json_falls_back(self):
        assert parse_links("{not valid}") == ["{not valid}"]

    def test_json_object_treated_as_plain(self):
        # A JSON object isn't a list → falls back to wrapping the string
        val = json.dumps({"key": "value"})
        result = parse_links(val)
        assert len(result) == 1

    def test_numeric_string(self):
        # "42" is valid JSON (a number) but not a list
        assert parse_links("42") == ["42"]


# ============================================================================
# serialize_links
# ============================================================================

class TestSerializeLinks:
    def test_none_returns_none(self):
        assert serialize_links(None) is None

    def test_empty_list_returns_none(self):
        assert serialize_links([]) is None

    def test_all_whitespace_returns_none(self):
        assert serialize_links(["  ", "", "   "]) is None

    def test_single_value(self):
        result = serialize_links(["path/a"])
        assert json.loads(result) == ["path/a"]

    def test_multiple_values(self):
        result = serialize_links(["path/a", "path/b"])
        assert json.loads(result) == ["path/a", "path/b"]

    def test_strips_whitespace(self):
        result = serialize_links(["  path/a  ", "path/b  "])
        parsed = json.loads(result)
        assert parsed == ["path/a", "path/b"]

    def test_filters_empty_strings(self):
        result = serialize_links(["path/a", "", "  ", "path/b"])
        parsed = json.loads(result)
        assert parsed == ["path/a", "path/b"]

    def test_roundtrip(self):
        original = ["notes/a.md", "notes/b.md", "http://example.com"]
        serialized = serialize_links(original)
        deserialized = parse_links(serialized)
        assert deserialized == original


# ============================================================================
# Stylesheet Derivation
# ============================================================================

class TestStylesheets:
    def test_stylesheet_has_node_rule(self):
        selectors = [r['selector'] for r in stylesheet]
        assert 'node' in selectors

    def test_stylesheet_has_edge_rule(self):
        selectors = [r['selector'] for r in stylesheet]
        assert 'edge' in selectors

    def test_mini_has_same_selectors_as_main(self):
        main_selectors = sorted(r['selector'] for r in stylesheet)
        mini_selectors = sorted(r['selector'] for r in mini_stylesheet)
        assert main_selectors == mini_selectors

    def test_mini_node_is_smaller(self):
        main_node = next(r for r in stylesheet if r['selector'] == 'node')
        mini_node = next(r for r in mini_stylesheet if r['selector'] == 'node')
        assert mini_node['style']['width'] < main_node['style']['width']
        assert mini_node['style']['height'] < main_node['style']['height']
        # Mini adds explicit font-size; main uses the browser default (no key)
        assert 'font-size' in mini_node['style']

    def test_mini_edge_is_thinner(self):
        main_edge = next(r for r in stylesheet if r['selector'] == 'edge')
        mini_edge = next(r for r in mini_stylesheet if r['selector'] == 'edge')
        assert mini_edge['style']['width'] < main_edge['style']['width']

    def test_mini_inherits_edge_colors(self):
        """Verify that edge type colors from the main stylesheet propagate to mini."""
        for selector in ['[type = "Needs_Hard"]', '[type = "Helps"]']:
            main_rule = next((r for r in stylesheet if r['selector'] == selector), None)
            mini_rule = next((r for r in mini_stylesheet if r['selector'] == selector), None)
            if main_rule and mini_rule:
                for key in main_rule['style']:
                    assert mini_rule['style'][key] == main_rule['style'][key], \
                        f"Mismatch in {selector} style key '{key}'"

    def test_mini_does_not_mutate_main(self):
        """Verify deepcopy — changing mini shouldn't affect main."""
        main_node = next(r for r in stylesheet if r['selector'] == 'node')
        mini_node = next(r for r in mini_stylesheet if r['selector'] == 'node')
        assert main_node['style']['width'] != mini_node['style']['width']


# ============================================================================
# get_all_triggered_ids
# ============================================================================

class TestGetAllTriggeredIds:
    def test_single_trigger(self):
        props = [{'prop_id': 'btn-edit-node.n_clicks', 'value': 1}]
        assert get_all_triggered_ids(props) == {'btn-edit-node'}

    def test_multiple_triggers(self):
        props = [
            {'prop_id': 'cytoscape-graph.tapNodeData', 'value': {'id': 'A'}},
            {'prop_id': 'edit-trigger-input.value', 'value': 'A|123'},
        ]
        assert get_all_triggered_ids(props) == {'cytoscape-graph', 'edit-trigger-input'}

    def test_empty_list(self):
        assert get_all_triggered_ids([]) == set()


# ============================================================================
# should_open_editor — double-click race condition regression tests
# ============================================================================

class TestShouldOpenEditor:
    """Verify that the editor opens for all edit-intent triggers, including
    when they are batched with tapNodeData in the same Dash callback cycle
    (the double-click race condition).
    """

    def test_edit_trigger_alone(self):
        assert should_open_editor({'edit-trigger-input'}, 'edit-trigger-input', None)

    def test_btn_edit_node_alone(self):
        assert should_open_editor({'btn-edit-node'}, 'btn-edit-node', None)

    def test_btn_add_alone(self):
        assert should_open_editor({'btn-add'}, 'btn-add', None)

    def test_search_node_with_value(self):
        assert should_open_editor({'search-node'}, 'search-node', 'MyNode')

    def test_search_node_without_value(self):
        assert not should_open_editor({'search-node'}, 'search-node', None)

    def test_tap_node_does_not_open(self):
        assert not should_open_editor({'cytoscape-graph'}, 'cytoscape-graph', None)

    def test_unrelated_trigger_does_not_open(self):
        assert not should_open_editor({'filter-context'}, 'filter-context', None)

    # --- The critical double-click race condition scenario ---
    def test_edit_trigger_batched_with_tap_node_data(self):
        """When a double-click causes both tapNodeData and edit-trigger-input
        to fire in the same Dash callback cycle, the editor must still open
        even though tapNodeData appears first in the Input list."""
        all_ids = {'cytoscape-graph', 'edit-trigger-input'}
        assert should_open_editor(all_ids, 'cytoscape-graph', None)

    def test_btn_edit_batched_with_tap_node_data(self):
        all_ids = {'cytoscape-graph', 'btn-edit-node'}
        assert should_open_editor(all_ids, 'cytoscape-graph', None)


# ============================================================================
# resolve_active_node_id — double-click race condition regression tests
# ============================================================================

class TestResolveActiveNodeId:
    """Verify correct node selection, especially when triggers are batched."""

    def test_edit_trigger_alone(self):
        result = resolve_active_node_id(
            {'edit-trigger-input'}, 'edit-trigger-input',
            'NodeA|12345', None, None, 'stale')
        assert result == 'NodeA'

    def test_search_node(self):
        result = resolve_active_node_id(
            {'search-node'}, 'search-node',
            None, 'SearchedNode', None, 'stale')
        assert result == 'SearchedNode'

    def test_tap_node(self):
        result = resolve_active_node_id(
            {'cytoscape-graph'}, 'cytoscape-graph',
            None, None, {'id': 'TappedNode'}, 'stale')
        assert result == 'TappedNode'

    def test_fallback_to_current_name(self):
        result = resolve_active_node_id(
            {'filter-context'}, 'filter-context',
            None, None, None, 'CurrentNode')
        assert result == 'CurrentNode'

    # --- The critical double-click race condition scenario ---
    def test_edit_trigger_batched_with_tap_prefers_edit_trigger(self):
        """When edit-trigger-input and tapNodeData fire together, the node ID
        from edit-trigger-input is used (it carries the ID explicitly)."""
        result = resolve_active_node_id(
            {'cytoscape-graph', 'edit-trigger-input'}, 'cytoscape-graph',
            'NodeA|12345', None, {'id': 'NodeA'}, 'stale')
        assert result == 'NodeA'

    def test_edit_trigger_batched_with_stale_tap(self):
        """Even if tapNodeData points to a different (stale) node, the
        edit-trigger-input value wins."""
        result = resolve_active_node_id(
            {'cytoscape-graph', 'edit-trigger-input'}, 'cytoscape-graph',
            'CorrectNode|999', None, {'id': 'StaleNode'}, 'OldName')
        assert result == 'CorrectNode'

    def test_edit_trigger_without_data_falls_through(self):
        """If edit-trigger-input fired but has no data, fall through."""
        result = resolve_active_node_id(
            {'cytoscape-graph', 'edit-trigger-input'}, 'cytoscape-graph',
            None, None, {'id': 'TappedNode'}, 'stale')
        assert result == 'TappedNode'
