"""
Tests for callback_helpers.py serialization functions and styles.py.

Tests pure functions that don't require a database.
"""

import json
from dash import html
import dash
from config import BADGE_PALETTE
from models import STATUS_DONE, STATUS_BLOCKED
from callback_helpers import (
    parse_links, serialize_links,
    get_all_triggered_ids, should_open_editor, resolve_active_node_id,
    _bool_icon,
    build_editor_snapshot, is_form_dirty_vs_snapshot, NEW_NODE_SNAPSHOT,
    snapshot_from_form_state, build_explain_summary,
    resolve_time_mode, resolve_value_mode,
    editor_form_values, ALL_WEEKDAYS,
    format_value_rank, _ordinal, _contributor_hover,
    alias_rows_label, update_alias_rows, sync_time_fields,
)
from styles import stylesheet, mini_stylesheet


# ============================================================================
# update_alias_rows
# ============================================================================

class TestUpdateAliasRows:
    def test_label_is_singular_for_zero_or_one_stored_row(self):
        assert alias_rows_label([]) == "Alias"
        assert alias_rows_label([""]) == "Alias"

    def test_label_is_plural_for_two_or_more_rows(self):
        assert alias_rows_label(["One", "Two"]) == "Aliases"
        assert alias_rows_label(["One", "Two", "Three"]) == "Aliases"

    def test_first_add_reveals_existing_row_without_adding_another(self):
        aliases, is_open = update_alias_rows(
            "add", ["Existing"], ["Stored"], False, "add", "remove",
        )
        assert aliases == ["Existing"]
        assert is_open is True

    def test_add_while_open_appends_a_row(self):
        aliases, is_open = update_alias_rows(
            "add", ["Existing"], ["Stored"], True, "add", "remove",
        )
        assert aliases == ["Existing", ""]
        assert is_open is True

    def test_add_after_all_rows_were_removed_restores_blank_row(self):
        aliases, is_open = update_alias_rows(
            "add", [], [], False, "add", "remove",
        )
        assert aliases == [""]
        assert is_open is True

    def test_removing_final_row_closes_aliases(self):
        aliases, is_open = update_alias_rows(
            {"type": "remove", "index": 0}, ["Only"], ["Only"], True,
            "add", "remove",
        )
        assert aliases == []
        assert is_open is False

    def test_removing_one_of_multiple_rows_keeps_collapse_unchanged(self):
        aliases, is_open = update_alias_rows(
            {"type": "remove", "index": 0}, ["First", "Second"],
            ["First", "Second"], True, "add", "remove",
        )
        assert aliases == ["Second"]
        assert is_open is dash.no_update


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
# resolve_time_mode
# ============================================================================

class TestResolveTimeMode:
    """Goal/Milestone container types must always inherit time from children;
    other types follow habit > inherited > manual based on form widget state.
    """

    def test_goal_forces_inherited_no_form_values(self):
        assert resolve_time_mode('Goal', [], []) == 'inherited'

    def test_goal_forces_inherited_even_when_habit_on(self):
        # Form lock makes this state unreachable in the UI, but the resolver
        # must enforce the invariant for any caller (convert-type, programmatic).
        assert resolve_time_mode('Goal', [], ['habit']) == 'inherited'

    def test_goal_forces_inherited_even_when_inherited_off(self):
        # User toggled off (somehow); resolver still enforces.
        assert resolve_time_mode('Goal', [], []) == 'inherited'

    def test_milestone_forces_inherited_no_form_values(self):
        assert resolve_time_mode('Milestone', [], []) == 'inherited'

    def test_milestone_forces_inherited_even_when_habit_on(self):
        assert resolve_time_mode('Milestone', [], ['habit']) == 'inherited'

    def test_milestone_forces_inherited_even_when_inherited_explicit(self):
        assert resolve_time_mode('Milestone', ['inherited'], []) == 'inherited'

    def test_learn_default_manual(self):
        assert resolve_time_mode('Learn', [], []) == 'manual'

    def test_learn_inherited_when_toggled(self):
        assert resolve_time_mode('Learn', ['inherited'], []) == 'inherited'

    def test_learn_habit_when_toggled(self):
        assert resolve_time_mode('Learn', [], ['habit']) == 'habit'

    def test_learn_habit_wins_over_inherited(self):
        # Mutual exclusivity is enforced upstream by enforce_time_mode_exclusivity,
        # but if both arrive here somehow, habit wins (matches existing precedent
        # in the original branched logic).
        assert resolve_time_mode('Learn', ['inherited'], ['habit']) == 'habit'

    def test_action_and_resource_follow_learn_rules(self):
        assert resolve_time_mode('Action', [], []) == 'manual'
        assert resolve_time_mode('Action', ['inherited'], []) == 'inherited'
        assert resolve_time_mode('Resource', [], ['habit']) == 'habit'

    def test_unknown_type_defaults_to_manual(self):
        # Unknown / None types are treated like Learn (no special-case force).
        assert resolve_time_mode(None, [], []) == 'manual'
        assert resolve_time_mode('Unknown', [], []) == 'manual'

    def test_none_form_values_safe(self):
        # Defensive: callers might pass None instead of empty lists.
        assert resolve_time_mode('Learn', None, None) == 'manual'
        assert resolve_time_mode('Goal', None, None) == 'inherited'


class TestResolveValueMode:
    """Milestones always inherit value (transparent checkpoints). Goals do
    NOT — they carry their own value. Otherwise the toggle decides.
    """

    def test_milestone_forces_inherited_no_toggle(self):
        assert resolve_value_mode('Milestone', []) == 'inherited'

    def test_milestone_forces_inherited_even_when_toggle_off(self):
        # User somehow cleared the (locked) toggle; resolver still enforces.
        assert resolve_value_mode('Milestone', []) == 'inherited'

    def test_milestone_inherited_when_toggle_on(self):
        assert resolve_value_mode('Milestone', ['inherited']) == 'inherited'

    def test_goal_not_forced(self):
        # Unlike time_mode, Goals are NOT forced to inherit value.
        assert resolve_value_mode('Goal', []) == 'manual'

    def test_goal_inherited_when_toggled(self):
        assert resolve_value_mode('Goal', ['inherited']) == 'inherited'

    def test_learn_default_manual(self):
        assert resolve_value_mode('Learn', []) == 'manual'

    def test_learn_inherited_when_toggled(self):
        assert resolve_value_mode('Learn', ['inherited']) == 'inherited'

    def test_action_and_resource_follow_learn_rules(self):
        assert resolve_value_mode('Action', []) == 'manual'
        assert resolve_value_mode('Resource', ['inherited']) == 'inherited'

    def test_unknown_type_defaults_to_toggle(self):
        assert resolve_value_mode(None, []) == 'manual'
        assert resolve_value_mode('Unknown', ['inherited']) == 'inherited'

    def test_none_toggle_value_safe(self):
        assert resolve_value_mode('Learn', None) == 'manual'
        assert resolve_value_mode('Milestone', None) == 'inherited'


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

    def test_selection_border_wins_over_dormant_border(self):
        """Cytoscape resolves overlapping style rules in list order."""
        for rules in (stylesheet, mini_stylesheet):
            selectors = [rule['selector'] for rule in rules]
            assert selectors.index('.dormant') < selectors.index('node:selected')
            selected_rule = next(
                rule for rule in rules if rule['selector'] == 'node:selected')
            assert selected_rule['style']['border-color'] == '#ffffff'
            assert selected_rule['style']['border-style'] == 'solid'


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
    """Tests for the boolean check/cross icon helper.

    These used to assert the Unicode glyphs U+2713 and U+2717 in stock
    Bootstrap green and red. The app is on one icon family (Bootstrap Icons)
    and one status palette, so the assertions name those instead.
    """

    def test_truthy_returns_check(self):
        result = _bool_icon(True)
        assert isinstance(result, html.I)
        assert result.className == "bi bi-check-lg"
        assert result.style["color"] == BADGE_PALETTE[STATUS_DONE][0]
        assert result.title == "Yes"

    def test_falsy_returns_cross(self):
        result = _bool_icon(False)
        assert isinstance(result, html.I)
        assert result.className == "bi bi-x-lg"
        assert result.style["color"] == BADGE_PALETTE[STATUS_BLOCKED][0]
        assert result.title == "No"

    def test_none_returns_cross(self):
        assert _bool_icon(None).className == "bi bi-x-lg"

    def test_nonempty_string_returns_check(self):
        assert _bool_icon("some/path.md").className == "bi bi-check-lg"

    def test_empty_string_returns_cross(self):
        assert _bool_icon("").className == "bi bi-x-lg"

    def test_uses_the_shared_palette_not_bootstrap_defaults(self):
        """Regression: stock #198754 / #dc3545 made a "yes" here a different
        green from a Done node one panel over."""
        assert _bool_icon(True).style["color"] != "#198754"
        assert _bool_icon(False).style["color"] != "#dc3545"


# ============================================================================
# is_form_dirty_vs_snapshot — X-button close-prompt regression tests
# ============================================================================

class TestIsFormDirtyVsSnapshot:
    """Pin the dirty-state detection behind the Node Editor's X-close prompt.

    Snapshot-based design: populate_editor stores a pristine snapshot of the
    form values it just wrote; the dirty check compares current form State to
    that snapshot. This eliminates false-positives from display transformations
    (e.g. strip_gdrive_prefix on Drive paths) and from the title-case linter
    rewriting names/aliases on save.
    """

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

    @staticmethod
    def _form_from_snapshot(snapshot):
        """The form values that exactly mirror a freshly-populated snapshot."""
        return dict(snapshot)

    def test_pristine_form_is_not_dirty(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        assert not is_form_dirty_vs_snapshot(snap, self._form_from_snapshot(snap))

    def test_edge_change_detected(self):
        """Adding a prerequisite must count as dirty."""
        from graph_manager import GraphManager
        mgr = GraphManager()
        self._seed(mgr, name='Target')
        node = self._seed(mgr, name='Alpha')
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['e_needs_h'] = ['Target']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_link_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['obs_links'] = ['notes/alpha.md']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_time_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['time_m'] = (form['time_m'] or 0) + 1
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_context_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['context'] = 'Body'
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_type_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['n_type'] = 'Action'
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_status_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['status_done'] = ['Done']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_alias_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['aliases'] = ['AlphaAlias']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_description_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['desc'] = 'updated description'
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_snapshot_none_returns_not_dirty(self):
        """No baseline snapshot — can't be dirty regardless of form values."""
        assert not is_form_dirty_vs_snapshot(None, {
            'name': 'Anything', 'desc': 'whatever',
            'obs_links': ['a', 'b'], 'aliases': ['X'],
        })

    def test_blank_new_node_form_is_not_dirty(self):
        """Empty new-node form against NEW_NODE_SNAPSHOT should not prompt."""
        assert not is_form_dirty_vs_snapshot(
            NEW_NODE_SNAPSHOT, dict(NEW_NODE_SNAPSHOT)
        )

    def test_new_node_with_name_typed_is_dirty(self):
        form = dict(NEW_NODE_SNAPSHOT)
        form['name'] = 'Unsaved'
        assert is_form_dirty_vs_snapshot(NEW_NODE_SNAPSHOT, form)

    def test_gdrive_prefix_does_not_cause_false_positive(self):
        """Regression: render_drive_links strips the GDrive prefix for display,
        so the form's State value is the stripped path. The snapshot must store
        the stripped form too — otherwise every node with a Drive path under
        the configured root would falsely flag as dirty."""
        from graph_manager import GraphManager
        from config import ConfigManager
        mgr = GraphManager()
        # Configure a Drive root and seed a node whose path lives under it.
        prefix = 'C:/GDrive/SkillTree/'
        ConfigManager.set_gdrive_path(prefix)
        try:
            full_path = prefix + 'foo.pdf'
            node = self._seed(
                mgr, name='WithDrive',
                google_drive_path=json.dumps([full_path]),
            )
            snap = build_editor_snapshot(mgr, node.name)
            # The snapshot must hold the *stripped* path — what the input shows.
            assert snap['drive_links'] == ['foo.pdf']
            # Form State (post-render) also holds the stripped path. Not dirty.
            form = self._form_from_snapshot(snap)
            assert not is_form_dirty_vs_snapshot(snap, form)
        finally:
            ConfigManager.set_gdrive_path('')

    def test_post_save_alias_lint_does_not_cause_false_positive(self):
        """Regression: set_aliases title-case-lints aliases on save. After the
        post-save snapshot refresh, a form holding the linted alias must not
        flag as dirty."""
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        # Save aliases through the manager — which applies the linter.
        mgr.set_aliases(node.name, ['alpha alias'])
        # Snapshot refreshed from DB now holds the *linted* alias.
        snap = build_editor_snapshot(mgr, node.name)
        assert snap['aliases'] == ['Alpha Alias']
        # Form holds the linted alias too (input was re-rendered from the store).
        form = self._form_from_snapshot(snap)
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_dormant_prereq_is_included_in_editor_snapshot(self):
        """The pristine snapshot mirrors dormant relationships shown in the form."""
        from graph_manager import GraphManager
        from models import EDGE_NEEDS_HARD
        mgr = GraphManager()
        target = self._seed(mgr, name='Target Goal', type='Goal')
        # Active prereq — visible in dropdown, will appear in form State.
        active = self._seed(mgr, name='Active Prereq', type='Learn')
        # Dormant prereq — visible in the relationship dropdown alongside active nodes.
        dormant = self._seed(mgr, name='Dormant Prereq', type='Action', dormant=1)
        mgr.add_edge(active.name, target.name, EDGE_NEEDS_HARD)
        mgr.add_edge(dormant.name, target.name, EDGE_NEEDS_HARD)
        snap = build_editor_snapshot(mgr, target.name)
        assert snap['e_needs_h'] == ['Active Prereq', 'Dormant Prereq']
        # Form State includes the same dormant relationship, so it is still pristine.
        form = self._form_from_snapshot(snap)
        assert not is_form_dirty_vs_snapshot(snap, form)


# ============================================================================
# snapshot_from_form_state — post-save pristine snapshot built directly from
# form State rather than a DB round-trip. This is the bug-fix path for the
# persistent "unsaved changes" false-positive after save: the DB round-trip
# through build_editor_snapshot re-applied _friendly_time_estimates, which
# could pick a different time_unit than the user had selected, causing the
# next dirty check to fire.
# ============================================================================

class TestSnapshotFromFormState:
    """Post-save snapshot must equal the form that was just saved, so the
    immediate post-save dirty check returns False regardless of any DB-side
    display transforms that would diverge on a round-trip."""

    @staticmethod
    def _form(**overrides):
        """A fully-populated form dict matching the snapshot schema."""
        base = {
            'name': 'Alpha',
            'n_type': 'Learn',
            'desc': 'hello',
            'context': 'Mind', 'subctx': '',
            'status_done': [],
            'val': 5, 'interest': 5, 'diff': 5,
            'time_o': 40, 'time_m': 80, 'time_p': 160,
            'time_unit': 'hours',
            'e_needs_h': [], 'e_needs_s': [],
            'e_supp_h': [], 'e_supp_s': [], 'e_helps': [],
            'obs_links': [''], 'drive_links': [''], 'website_links': [''],
            'time_mode': [],
            'habit_intensity_unit': 'min_per_session',
            'habit_days': [0, 1, 2, 3, 4, 5, 6],
            'priority_rank': 'none',
            'aliases': [''],
        }
        base.update(overrides)
        return base

    def test_snapshot_matches_form_not_dirty(self):
        """Core invariant: a snapshot built from form values, with the same
        name/aliases, yields a dirty-check of False against that form."""
        form = self._form()
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_time_unit_drift_does_not_trip_dirty_check(self):
        """Regression: the primary observed false-positive. User types time
        values in 'hours'; on save, a DB round-trip through
        _friendly_time_estimates could pick 'weeks' from large hour values,
        diverging both time_unit and time_o/m/p. Snapshotting form State
        directly preserves the user's selected unit."""
        # 500/600/700 hours — _friendly_time_estimates would pick 'weeks'.
        form = self._form(time_o=500, time_m=600, time_p=700, time_unit='hours')
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        # Snapshot must preserve the form's 'hours' unit and raw hour values.
        assert snap['time_unit'] == 'hours'
        assert snap['time_o'] == 500
        assert snap['time_m'] == 600
        assert snap['time_p'] == 700
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_linted_name_in_snapshot_not_dirty_vs_linted_form(self):
        """The title-case linter rewrites 'lowercase node' -> 'Lowercase Node'
        on save, and sync_original_name_after_save pushes the linted name
        back into the form. The snapshot must hold the linted name too —
        otherwise form-post-lint vs snapshot-pre-lint would fire dirty."""
        pre_lint_form = self._form(name='lowercase node')
        snap = snapshot_from_form_state(
            pre_lint_form, 'Lowercase Node', pre_lint_form['aliases']
        )
        # After Dash applies the callback's output, the form's node-name value
        # is 'Lowercase Node' — matching the snapshot.
        post_lint_form = dict(pre_lint_form)
        post_lint_form['name'] = 'Lowercase Node'
        assert not is_form_dirty_vs_snapshot(snap, post_lint_form)

    def test_linted_aliases_in_snapshot_not_dirty_vs_linted_form(self):
        """Aliases get title-case-linted by manager.set_aliases on save, and
        the aliases-store output rewrites the form's alias inputs. Snapshot
        must match the post-lint form."""
        pre_lint_form = self._form(aliases=['alpha alias'])
        snap = snapshot_from_form_state(
            pre_lint_form, pre_lint_form['name'], ['Alpha Alias']
        )
        post_lint_form = dict(pre_lint_form)
        post_lint_form['aliases'] = ['Alpha Alias']
        assert not is_form_dirty_vs_snapshot(snap, post_lint_form)

    def test_gdrive_full_path_in_form_not_dirty(self):
        """Regression: the user may have typed a full GDrive-prefixed path,
        which handle_save strips before writing to DB. build_editor_snapshot
        read back as stripped; form still held full path -> dirty.
        snapshot_from_form_state stores what the form holds, so no drift."""
        form = self._form(drive_links=['C:/GDrive/SkillTree/foo.pdf'])
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        assert snap['drive_links'] == ['C:/GDrive/SkillTree/foo.pdf']
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_new_node_after_save_has_real_snapshot(self):
        """Brand-new node save: form holds the typed values; snapshot must
        carry those values (not fall back to NEW_NODE_SNAPSHOT)."""
        form = self._form(
            name='Fresh Node', desc='just typed',
            val=7, interest=8, diff=3,
            time_o=1, time_m=2, time_p=3, time_unit='days',
            aliases=['Fresh'],
        )
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        assert snap['name'] == 'Fresh Node'
        assert snap['desc'] == 'just typed'
        assert snap['val'] == 7
        assert snap['time_unit'] == 'days'
        assert snap['aliases'] == ['Fresh']
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_empty_optional_fields_default_sensibly(self):
        """A form with None in optional fields should produce a snapshot
        with the same sensible defaults the dirty check uses."""
        form = self._form(
            desc=None, context=None, subctx=None,
            obs_links=None, drive_links=None, website_links=None,
            aliases=None, status_done=None, time_mode=None,
        )
        snap = snapshot_from_form_state(
            form,
            form['name'],
            None,  # mirrors manager.get_aliases returning empty -> [''] fallback
        )
        # Defaults match the expectations of is_form_dirty_vs_snapshot.
        assert snap['desc'] == ''
        assert snap['aliases'] == ['']
        assert snap['obs_links'] == ['']
        assert snap['status_done'] == []
        assert snap['time_mode'] == []
        # Reconstitute the form the way Dash would (with the defaults the
        # input components emit) and confirm not dirty.
        form_for_check = dict(form)
        form_for_check.update({
            'desc': '', 'context': '', 'subctx': '',
            'obs_links': [''], 'drive_links': [''], 'website_links': [''],
            'aliases': [''], 'status_done': [], 'time_mode': [],
        })
        assert not is_form_dirty_vs_snapshot(snap, form_for_check)

    def test_user_edit_after_save_is_dirty(self):
        """Sanity: if the user edits anything after save, the dirty check must
        still fire. The fix must not make 'always clean'."""
        form = self._form()
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        edited = dict(form)
        edited['desc'] = 'now edited'
        assert is_form_dirty_vs_snapshot(snap, edited)

    def test_dormant_prereq_inherited_from_form(self):
        """Post-save snapshots retain dormant relationships from form State."""
        form = self._form(e_needs_h=['Active Prereq', 'Dormant Prereq'])
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        assert snap['e_needs_h'] == ['Active Prereq', 'Dormant Prereq']
        assert not is_form_dirty_vs_snapshot(snap, form)


# ============================================================================
# editor_form_values — single source of truth for the dirty-check form dict.
#
# Regression guard for the spurious "unsaved changes" prompt: the form-values
# dict used to be hand-built at three separate call sites (the X-close gate,
# the close-prompt modal, and the navigation interceptor). They drifted — the
# modal gate omitted every habit_* field, the close gate omitted habit_days —
# so an omitted field read back as a coercion default that disagreed with the
# snapshot, flagging an unchanged form as dirty on every close. Routing all
# call sites through editor_form_values fixes that; these tests pin the schema
# so a future field addition can't silently reopen the drift.
# ============================================================================

class TestEditorFormValues:
    @staticmethod
    def _full_kwargs(**overrides):
        base = dict(
            name='Alpha', n_type='Learn', desc='hello',
            context='Mind', subctx='',
            status_done=[],
            val=5, interest=5, diff=5,
            time_o=40, time_m=80, time_p=160, time_unit='hours',
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            obs_links=[''], drive_links=[''], website_links=[''],
            time_mode=[], value_mode=[], priority_rank='none', aliases=[''],
            time_habit_mode=[],
            habit_duration=0, habit_duration_unit='weeks',
            habit_intensity_o=0, habit_intensity_m=0, habit_intensity_p=0,
            habit_intensity_unit='min_per_session',
            habit_days=list(ALL_WEEKDAYS),
        )
        base.update(overrides)
        return base

    def test_keys_match_new_node_snapshot_schema(self):
        """The form-values dict must carry exactly the snapshot's key set —
        no missing field (false positive) and no extra field (silent no-op)."""
        produced = editor_form_values(**self._full_kwargs())
        assert set(produced.keys()) == set(NEW_NODE_SNAPSHOT.keys())

    def test_keys_match_built_snapshot_schema(self):
        from graph_manager import GraphManager
        from models import Node
        mgr = GraphManager()
        mgr.add_node(Node(name='Alpha', type='Learn', description='x',
                          value=5, interest=5, difficulty=5, status='Open',
                          time_o=40, time_m=80, time_p=160, context='Mind'))
        snap = build_editor_snapshot(mgr, 'Alpha')
        produced = editor_form_values(**self._full_kwargs())
        assert set(produced.keys()) == set(snap.keys())

    def test_blank_form_not_dirty_vs_new_node_snapshot(self):
        """A blank new-node form (component defaults) built through the helper
        must not register dirty against NEW_NODE_SNAPSHOT."""
        blank = editor_form_values(**self._full_kwargs(
            name='', desc='', context='', subctx='', time_o=2, time_m=4,
            time_p=6, time_unit='weeks',
        ))
        assert not is_form_dirty_vs_snapshot(NEW_NODE_SNAPSHOT, blank)

    def test_omitting_habit_args_uses_layout_defaults(self):
        """A caller with no habit state (the historical modal-gate case) gets
        the same habit defaults the editor components emit — so an unchanged
        non-habit node does not falsely register dirty."""
        from graph_manager import GraphManager
        from models import Node
        mgr = GraphManager()
        mgr.add_node(Node(name='Alpha', type='Learn', description='hello',
                          value=5, interest=5, difficulty=5, status='Open',
                          time_o=40, time_m=80, time_p=160, context='Mind'))
        snap = build_editor_snapshot(mgr, 'Alpha')
        # Mirror the snapshot's non-habit fields but pass NO habit_* kwargs.
        form = editor_form_values(
            name='Alpha', n_type='Learn', desc='hello',
            context='Mind', subctx='',
            status_done=[], val=5, interest=5, diff=5,
            time_o=snap['time_o'], time_m=snap['time_m'], time_p=snap['time_p'],
            time_unit=snap['time_unit'],
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            obs_links=[''], drive_links=[''], website_links=[''],
            time_mode=[], value_mode=[], priority_rank='none', aliases=[''],
        )
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_unchanged_loaded_node_not_dirty(self):
        """End-to-end: a loaded node's form (mirroring its snapshot) routed
        through the helper is not dirty — the core false-positive case."""
        from graph_manager import GraphManager
        from models import Node
        mgr = GraphManager()
        mgr.add_node(Node(name='Habit Node', type='Action', description='d',
                          value=5, interest=5, difficulty=5, status='Open',
                          context='Mind',
                          time_o=40, time_m=80, time_p=160, time_mode='habit',
                          habit_duration=6, habit_duration_unit='weeks',
                          habit_intensity_o=20, habit_intensity_m=30,
                          habit_intensity_p=45,
                          habit_intensity_unit='min_per_session'))
        snap = build_editor_snapshot(mgr, 'Habit Node')
        form = editor_form_values(
            name=snap['name'], n_type=snap['n_type'], desc=snap['desc'],
            context=snap['context'], subctx=snap['subctx'],
            status_done=snap['status_done'],
            val=snap['val'], interest=snap['interest'], diff=snap['diff'],
            time_o=snap['time_o'], time_m=snap['time_m'], time_p=snap['time_p'],
            time_unit=snap['time_unit'],
            e_needs_h=snap['e_needs_h'], e_needs_s=snap['e_needs_s'],
            e_supp_h=snap['e_supp_h'], e_supp_s=snap['e_supp_s'],
            e_helps=snap['e_helps'],
            obs_links=snap['obs_links'], drive_links=snap['drive_links'],
            website_links=snap['website_links'],
            time_mode=snap['time_mode'], time_habit_mode=snap['time_habit_mode'],
            habit_duration=snap['habit_duration'],
            habit_duration_unit=snap['habit_duration_unit'],
            habit_intensity_o=snap['habit_intensity_o'],
            habit_intensity_m=snap['habit_intensity_m'],
            habit_intensity_p=snap['habit_intensity_p'],
            habit_intensity_unit=snap['habit_intensity_unit'],
            habit_days=snap['habit_days'],
            value_mode=snap['value_mode'], priority_rank=snap['priority_rank'],
            aliases=snap['aliases'],
        )
        assert not is_form_dirty_vs_snapshot(snap, form)


# ============================================================================
# build_explain_summary — plain-language calculation details
# ============================================================================

def _minimal_breakdown(**overrides):
    """Build the minimal dict shape that _explain_summary_table consumes."""
    bd = {
        'node': 'X',
        'context': 'Mind',
        'subcontext': None,
        'score': 1.23,
        'raw_score': 1.23,
        'eligible': True,
        'block_reason': None,
        'intrinsic': {'value': 5, 'interest': 5, 'iv': 10.0},
        'cost': {'difficulty': 5, 'time': 2.0, 'time_overridden': False, 'cost': 15.5},
        'composition': {
            'iv': 10.0,
            'hard_cascade': 2.0,
            'soft_cascade': 0.5,
            'synergy': 0.0,
            'total_value': 12.5,
        },
        'goal_boost': None,
        'variety': None,
        'context_adjustment': {
            'weight': 1.0, 'n_bucket': 1, 'alpha': 0.0,
            'density_mult': 1.0, 'combined_multiplier': 1.0,
        },
        'contributors': [],
    }
    bd.update(overrides)
    return bd


def _render_text(component):
    """Flatten a Dash component tree into a string for substring assertions."""
    if component is None:
        return ""
    if isinstance(component, str):
        return component
    if isinstance(component, list):
        return " ".join(_render_text(c) for c in component)
    children = getattr(component, 'children', None)
    return _render_text(children) if children is not None else ""


class TestContributorHover:
    def test_downstream_contributor_is_name_route_and_ratings(self):
        row = {'name': 'Health', 'via': 'Hard', 'depth': 2, 'iv': 181.0,
               'value': 9, 'interest': 10, 'pct_of_tv': 14.5, 'contribution': 40.0,
               'remaining_hours': 400.0, 'future_discount': 0.67}
        assert _contributor_hover(row) == (
            "<b>Health</b><br>Value 9 · Interest 10<br>2 steps away via hard prerequisite"
            "<br>Passes on 22% of its value")

    def test_self_bar_shows_only_name_and_ratings(self):
        row = {'name': 'X', 'via': 'Self', 'depth': 0, 'iv': 10.0,
               'value': 5, 'interest': 5}
        assert _contributor_hover(row) == "<b>X</b><br>Value 5 · Interest 5"

    def test_names_are_escaped(self):
        row = {'name': 'A <b> B', 'via': 'Synergy', 'depth': 1, 'iv': 0.0}
        assert _contributor_hover(row) == (
            "<b>A &lt;b&gt; B</b><br>1 step away via synergy partner")


class TestExplainSummary:
    def test_value_is_shown_as_shares_not_internal_quantities(self):
        """10 + 2 + 0.5 of 12.5 → 80% / 16% / 4.0%; no raw value or cost."""
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "Own ratings Value 5 · Interest 5 80%" in text
        assert "Unlocks 16%" in text
        assert "Prepares you for 4.0%" in text
        for internal in ("10.00", "12.50", "15.50", "1.23", "Raw", "Intrinsic"):
            assert internal not in text

    def test_synergy_rows_sit_together_at_the_end_of_value(self):
        bd = _minimal_breakdown(composition={
            'iv': 10.0, 'hard_cascade': 2.0, 'soft_cascade': 0.5, 'synergy': 1.0,
            'iv_multiplier': 1.4, 'iv_multiplier_contribution': 4.0,
            'done_synergy_count': 1, 'total_value': 17.5,
        })
        text = _render_text(build_explain_summary(bd, normalized=80))
        assert ("Prepares you for 2.9% Synergy partners 5.7% "
                "Finished synergy partners 1 finished 23% Cost") in text

    def test_value_sources_with_no_share_are_left_out(self):
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "ynergy partners" not in text

    def test_cost_is_shown_as_time_and_effort(self):
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "Time 2h" in text
        assert "Effort 5 of 10" in text

    def test_inherited_value_and_time_read_as_none_of_its_own(self):
        bd = _minimal_breakdown(
            intrinsic={'value': 7, 'interest': 6, 'iv': 0.0, 'value_overridden': True},
            cost={'difficulty': 4, 'time': 0.0, 'time_overridden': True,
                  'effort_overridden': True, 'cost': 1.0},
        )
        text = _render_text(build_explain_summary(bd, normalized=None))
        assert "Value 7" not in text
        assert "Own ratings none of its own" in text
        assert "Time None of its own" in text
        assert "Effort None of its own" in text

    def test_no_adjustments_section_when_all_trivial(self):
        """With weight=1, density=1, no goal boost or variety: no Adjustments header."""
        text = _render_text(build_explain_summary(_minimal_breakdown(), normalized=80))
        assert "Adjustments" not in text
        assert "Priority 80 of 100" in text

    def test_density_reads_as_crowding_without_parameters(self):
        bd = _minimal_breakdown(subcontext='Focus', context_adjustment={
            'weight': 1.0, 'n_bucket': 17, 'alpha': 0.3,
            'density_mult': 0.432, 'combined_multiplier': 0.432,
        })
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Crowding 17 goals in Mind · Focus −57%" in text
        assert "α" not in text and "n=17" not in text
        assert "Together" not in text

    def test_context_weight_reads_as_a_percent_change(self):
        bd = _minimal_breakdown(context_adjustment={
            'weight': 2.0, 'n_bucket': 5, 'alpha': 0.0,
            'density_mult': 1.0, 'combined_multiplier': 2.0,
        })
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Context weight Mind +100%" in text
        assert "×" not in text

    def test_variety_names_its_place_in_context_and_subcontext(self):
        bd = _minimal_breakdown(variety={
            'divisor': 1.25, 'context': 'Mind', 'subcontext': 'Focus',
            'context_rank': 3, 'subcontext_rank': 2,
        })
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Variety 3rd from Mind, 2nd from Focus −20%" in text

    def test_several_adjustments_add_a_together_row(self):
        bd = _minimal_breakdown(
            goal_boost={'multiplier': 1.5, 'goal': 'Health', 'rank': 1},
            context_adjustment={
                'weight': 2.0, 'n_bucket': 1, 'alpha': 0.0,
                'density_mult': 1.0, 'combined_multiplier': 2.0,
            },
        )
        text = _render_text(build_explain_summary(bd, normalized=50))
        assert "Priority goal Health (#1) +50%" in text
        assert "Context weight Mind +100%" in text
        assert "Together +200%" in text

    def test_goal_breakdown_shows_prerequisites_and_work_left(self):
        bd = _minimal_breakdown(
            is_goal=True,
            cost={'goal': True, 'remaining_time': 6.0, 'cost': 2.0,
                  'time_overridden': False},
            goal_boost={'multiplier': 1.5, 'goal': 'X', 'rank': 2},
        )
        text = _render_text(build_explain_summary(bd, normalized=40))
        assert "Prerequisites 16%" in text
        assert "Hard prerequisite work left 2.1d" in text
        assert "Effort" not in text
        assert "Priority goal X (#2) +50%" in text

    def test_ineligible_shows_reason_instead_of_priority(self):
        bd = _minimal_breakdown(eligible=False, block_reason="Blocked")
        text = _render_text(build_explain_summary(bd, normalized=None))
        assert "Not ranked Blocked" in text
        assert "of 100" not in text


# ============================================================================
# format_value_rank — the Explain modal's header stat
# ============================================================================

class TestFormatValueRank:
    """Total value is an internal quantity, so only the rank is shown."""

    POOL = [900.0, 800.0, 700.0, 600.0, 500.0, 400.0, 300.0, 200.0, 100.0, 50.0]

    def test_best_node(self):
        assert format_value_rank(900.0, self.POOL, "projects") == \
            "Ranks 1st of 10 projects"

    def test_worst_node(self):
        assert format_value_rank(50.0, self.POOL, "projects") == \
            "Ranks 10th of 10 projects"

    def test_middle_node(self):
        assert format_value_rank(600.0, self.POOL) == "Ranks 4th of 10 projects"

    def test_ties_share_the_better_rank(self):
        assert format_value_rank(5.0, [10.0, 5.0, 5.0, 1.0]) == "Ranks 2nd of 4 projects"

    def test_noun_is_used_verbatim(self):
        assert format_value_rank(900.0, self.POOL, "goals").endswith("goals")

    def test_the_raw_value_is_never_shown(self):
        """The number has no units and shifts with the profile; it stays out."""
        out = format_value_rank(12345.6, [99999.0, 12345.6, 1.0])
        assert "12345" not in out and "12,345" not in out

    def test_no_percentile_is_shown(self):
        assert "%" not in format_value_rank(900.0, self.POOL)

    def test_returns_empty_when_there_is_nothing_to_compare(self):
        assert format_value_rank(5.0, [5.0]) == ""
        assert format_value_rank(5.0, []) == ""
        assert format_value_rank(5.0, None) == ""

    def test_returns_empty_without_a_value(self):
        assert format_value_rank(None, self.POOL) == ""

    def test_ignores_missing_peer_values(self):
        """A peer with no computed total value must not skew the count."""
        assert format_value_rank(10.0, [10.0, 5.0, None, None]) == "Ranks 1st of 2 projects"


class TestOrdinal:
    def test_common_suffixes(self):
        assert [_ordinal(n) for n in (1, 2, 3, 4)] == ["1st", "2nd", "3rd", "4th"]

    def test_teens_are_all_th(self):
        assert [_ordinal(n) for n in (11, 12, 13)] == ["11th", "12th", "13th"]

    def test_suffix_repeats_past_twenty(self):
        assert [_ordinal(n) for n in (21, 22, 23, 111, 112)] == \
            ["21st", "22nd", "23rd", "111th", "112th"]


# ============================================================================
# sync_time_fields
# ============================================================================

class TestSyncTimeFields:
    def test_week_edit_fills_the_rest_and_leaves_the_week_alone(self):
        assert sync_time_fields('setting-hpw', 2.86, 20, 80, 1040) == (2.86, None, 80.0, 1040.0)

    def test_rounded_day_echo_does_not_overwrite_the_week(self):
        # 20h/week displays as 2.86 h/day; that echo must not turn 20 into 20.02.
        assert sync_time_fields('setting-hpd', 2.86, 20, 80, 1040) == (None, None, None, None)

    def test_a_real_day_edit_still_updates_the_week(self):
        assert sync_time_fields('setting-hpd', 3, 20, 80, 1040) == (None, 21.0, 84.0, 1092.0)

    def test_month_and_year_edits_fill_the_rest(self):
        assert sync_time_fields('setting-hpm', 2.86, 20, 80, 1040) == (2.86, 20.0, None, 1040.0)
        assert sync_time_fields('setting-hpy', 2.86, 20, 80, 1040) == (2.86, 20.0, 80.0, None)

    def test_blank_or_junk_input_changes_nothing(self):
        assert sync_time_fields('setting-hpw', None, None, None, None) == (None,) * 4
        assert sync_time_fields('setting-hpw', None, 'abc', None, None) == (None,) * 4
        assert sync_time_fields(None, 1, 2, 3, 4) == (None,) * 4

    def test_typing_20_reaches_a_fixed_point(self):
        """Feed each output back in as the trigger until nothing changes."""
        vals = {'setting-hpd': None, 'setting-hpw': 20, 'setting-hpm': None, 'setting-hpy': None}
        order = ['setting-hpd', 'setting-hpw', 'setting-hpm', 'setting-hpy']
        pending = ['setting-hpw']
        for _ in range(10):
            if not pending:
                break
            trig = pending.pop(0)
            out = sync_time_fields(trig, *(vals[k] for k in order))
            for k, v in zip(order, out):
                if v is not None and vals[k] != v:
                    vals[k] = v
                    pending.append(k)
        assert not pending
        assert (vals['setting-hpw'], vals['setting-hpm'], vals['setting-hpy']) == (20, 80.0, 1040.0)
