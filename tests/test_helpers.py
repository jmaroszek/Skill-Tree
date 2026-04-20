"""
Tests for callback_helpers.py serialization functions and styles.py.

Tests pure functions that don't require a database.
"""

import json
from dash import html
from callback_helpers import (
    parse_links, serialize_links,
    get_all_triggered_ids, should_open_editor, resolve_active_node_id,
    _bool_icon, has_editor_unsaved_changes,
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
        # btn-add is now handled as a toggle in core_engine, not via should_open_editor
        assert not should_open_editor({'btn-add'}, 'btn-add', None)

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


# ============================================================================
# _bool_icon
# ============================================================================

class TestBoolIcon:
    """Tests for the boolean checkmark/cross icon helper."""

    def test_truthy_returns_checkmark(self):
        result = _bool_icon(True)
        assert isinstance(result, html.Span)
        assert result.children == "\u2713"
        assert result.style["color"] == "#198754"

    def test_falsy_returns_cross(self):
        result = _bool_icon(False)
        assert isinstance(result, html.Span)
        assert result.children == "\u2717"
        assert result.style["color"] == "#dc3545"

    def test_none_returns_cross(self):
        result = _bool_icon(None)
        assert result.children == "\u2717"

    def test_nonempty_string_returns_checkmark(self):
        result = _bool_icon("some/path.md")
        assert result.children == "\u2713"

    def test_empty_string_returns_cross(self):
        result = _bool_icon("")
        assert result.children == "\u2717"


# ============================================================================
# has_editor_unsaved_changes — X-button close-prompt regression tests
# ============================================================================

class TestHasEditorUnsavedChanges:
    """Pin the dirty-state detection behind the Node Editor's X-close prompt.

    Regression: only 5 of the ~25 editable fields were being compared, so
    changes to edges/links/time/type/context/etc. caused the editor to
    silently close without prompting to save.
    """

    @staticmethod
    def _pristine_form(node):
        """Build the form-state kwargs that populate_editor would set for ``node``."""
        from callbacks import _friendly_time_estimates
        friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
            node.time_o, node.time_m, node.time_p
        )
        return dict(
            name=node.name, n_type=node.type, desc=node.description,
            context=node.context or '', subctx=node.subcontext or '',
            status_done=(['Done'] if node.status == 'Done' else []),
            val=node.value, interest=node.interest, diff=node.difficulty,
            time_o=friendly_o, time_m=friendly_m, time_p=friendly_p,
            time_unit=friendly_unit,
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            obs_link_values=[''], drive_link_values=[''], website_link_values=[''],
            progress_val=node.progress or 0,
            time_mode_val=(['inherited'] if node.time_mode == 'inherited' else []),
            priority_rank_val='none', competence_val=node.competence or '',
            alias_values=[''],
        )

    @staticmethod
    def _seed(mgr, **overrides):
        from models import Node
        defaults = dict(
            name='Alpha', type='Learn', description='hello', value=5,
            time_o=40.0, time_m=80.0, time_p=160.0, interest=5, difficulty=5,
            status='Open', context='Mind',
        )
        defaults.update(overrides)
        node = Node(**defaults)
        mgr.add_node(node)
        return node

    def test_pristine_form_is_not_dirty(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        assert not has_editor_unsaved_changes(
            mgr, node.name, **self._pristine_form(node)
        )

    def test_edge_change_detected(self):
        """Adding a prerequisite must count as dirty."""
        from graph_manager import GraphManager
        mgr = GraphManager()
        self._seed(mgr, name='Target')
        node = self._seed(mgr, name='Alpha')
        form = self._pristine_form(node)
        form['e_needs_h'] = ['Target']
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_link_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['obs_link_values'] = ['notes/alpha.md']
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_time_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['time_m'] = (form['time_m'] or 0) + 1
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_context_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['context'] = 'Body'
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_type_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['n_type'] = 'Action'
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_status_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['status_done'] = ['Done']
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_alias_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['alias_values'] = ['AlphaAlias']
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_competence_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['competence_val'] = 'Expert'
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_description_change_detected(self):
        """Sanity check: the original 5-field check still works."""
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        form = self._pristine_form(node)
        form['desc'] = 'updated description'
        assert has_editor_unsaved_changes(mgr, node.name, **form)

    def test_blank_new_node_form_is_not_dirty(self):
        """Empty new-node form (no original_name) should not prompt."""
        from graph_manager import GraphManager
        mgr = GraphManager()
        assert not has_editor_unsaved_changes(
            mgr, None,
            name='', n_type='Learn', desc='',
            context='', subctx='', status_done=[],
            val=5, interest=5, diff=5,
            time_o=2, time_m=4, time_p=6, time_unit='weeks',
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            obs_link_values=[''], drive_link_values=[''], website_link_values=[''],
            progress_val=0, time_mode_val=[], priority_rank_val='none',
            competence_val='', alias_values=[''],
        )

    def test_new_node_with_name_typed_is_dirty(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        assert has_editor_unsaved_changes(
            mgr, None,
            name='Unsaved', n_type='Learn', desc='',
            context='', subctx='', status_done=[],
            val=5, interest=5, diff=5,
            time_o=2, time_m=4, time_p=6, time_unit='weeks',
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            obs_link_values=[''], drive_link_values=[''], website_link_values=[''],
            progress_val=0, time_mode_val=[], priority_rank_val='none',
            competence_val='', alias_values=[''],
        )
