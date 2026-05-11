"""
Tests for callback_helpers.py serialization functions and styles.py.

Tests pure functions that don't require a database.
"""

import json
from dash import html
import dash
from callback_helpers import (
    parse_links, serialize_links,
    get_all_triggered_ids, should_open_editor, resolve_active_node_id,
    _bool_icon,
    build_editor_snapshot, is_form_dirty_vs_snapshot, NEW_NODE_SNAPSHOT,
    snapshot_from_form_state, build_explain_summary,
    resolve_time_mode, resolve_locked_time_mode,
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
# resolve_locked_time_mode
# ============================================================================

class TestResolveLockedTimeMode:
    """Container Goal/Milestone types lock the Inherit toggle ON.

    The helper drives three outputs (time-mode value, warning style, warning
    text). The hot question is when the inline warning should appear vs hide;
    the regression we're protecting against is the warning appearing on form
    populate of an existing Milestone.
    """

    HIDDEN = {"display": "none"}
    VISIBLE = {"display": "block", "color": "#dc3545", "fontSize": "0.85rem"}
    MILESTONE_MSG = (
        "Inherit mode is required for Milestone nodes — "
        "their time is the sum of their children's."
    )
    GOAL_MSG = (
        "Inherit mode is required for Goal nodes — "
        "their time is the sum of their children's."
    )

    def test_non_container_clears_warning(self):
        # Learn/Action/Resource: pass through time_mode_val, hide warning.
        out = resolve_locked_time_mode([], 'Learn', only_time_mode_triggered=False)
        assert out == ([], self.HIDDEN, "")

    def test_non_container_inherited_value_unchanged(self):
        out = resolve_locked_time_mode(['inherited'], 'Resource',
                                       only_time_mode_triggered=True)
        assert out == (['inherited'], self.HIDDEN, "")

    def test_milestone_form_populate_clears_warning(self):
        # Regression: form populate fires BOTH node-type and node-time-mode in
        # the same dispatch (only_time_mode=False). The warning must hide even
        # if it was visible from a prior interaction.
        out = resolve_locked_time_mode(['inherited'], 'Milestone',
                                       only_time_mode_triggered=False)
        assert out == (dash.no_update, self.HIDDEN, "")

    def test_milestone_bounce_back_preserves_warning(self):
        # User toggled inherit off; the bounce-back cycle (only node-time-mode
        # triggered, time_mode now back to ['inherited']) must NOT clobber the
        # message we just made visible.
        out = resolve_locked_time_mode(['inherited'], 'Milestone',
                                       only_time_mode_triggered=True)
        assert out == (dash.no_update, dash.no_update, dash.no_update)

    def test_milestone_user_toggle_off_shows_warning(self):
        # User toggled inherit off on a milestone: only node-time-mode fires,
        # time_mode is now empty. Bounce back AND show warning.
        out = resolve_locked_time_mode([], 'Milestone',
                                       only_time_mode_triggered=True)
        assert out == (['inherited'], self.VISIBLE, self.MILESTONE_MSG)

    def test_goal_user_toggle_off_shows_goal_message(self):
        out = resolve_locked_time_mode([], 'Goal',
                                       only_time_mode_triggered=True)
        assert out == (['inherited'], self.VISIBLE, self.GOAL_MSG)

    def test_type_change_to_milestone_silently_forces_inherit(self):
        # User changes type dropdown Learn → Milestone with time_mode=[].
        # Only node-type triggered (so only_time_mode_triggered=False); force
        # inherit ON silently (no warning — they didn't toggle anything).
        out = resolve_locked_time_mode([], 'Milestone',
                                       only_time_mode_triggered=False)
        assert out == (['inherited'], self.HIDDEN, "")

    def test_type_change_into_goal_clears_stale_warning(self):
        # Inherited was already on (e.g. previous type was Goal too), trigger
        # is node-type (only_time_mode=False). Clear any stale warning.
        out = resolve_locked_time_mode(['inherited'], 'Goal',
                                       only_time_mode_triggered=False)
        assert out == (dash.no_update, self.HIDDEN, "")


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

    def test_competence_change_detected(self):
        from graph_manager import GraphManager
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, node.name)
        form = self._form_from_snapshot(snap)
        form['competence'] = 'Expert'
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

    def test_dormant_prereq_does_not_cause_false_positive(self):
        """Regression: edge dropdowns get options from non-dormant nodes only.
        dcc.Dropdown silently filters its value to entries in options, so a
        prereq edge to a dormant node is invisible to the form's State. The
        snapshot must apply the same filter, otherwise the dirty check fires
        on every X-close for any node that has a dormant prerequisite."""
        from graph_manager import GraphManager
        from models import EDGE_NEEDS_HARD
        mgr = GraphManager()
        target = self._seed(mgr, name='Target Goal', type='Goal')
        # Active prereq — visible in dropdown, will appear in form State.
        active = self._seed(mgr, name='Active Prereq', type='Learn')
        # Dormant prereq — excluded from dropdown options, dropped from form State.
        dormant = self._seed(mgr, name='Dormant Prereq', type='Action', dormant=1)
        mgr.add_edge(active.name, target.name, EDGE_NEEDS_HARD)
        mgr.add_edge(dormant.name, target.name, EDGE_NEEDS_HARD)
        snap = build_editor_snapshot(mgr, target.name)
        # Snapshot must include only the active prereq, mirroring the dropdown.
        assert snap['e_needs_h'] == ['Active Prereq']
        # Form State (also missing the dormant prereq) — not dirty.
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
            'priority_rank': 'none',
            'competence': '',
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
            desc=None, context=None, subctx=None, competence=None,
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
            'desc': '', 'context': '', 'subctx': '', 'competence': '',
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

    def test_dormant_prereq_filtering_inherited_from_form(self):
        """populate_editor filters dormant-endpoint edges out of the form's
        State values. Since snapshot_from_form_state copies form verbatim,
        it inherits the dormant-filter for free — no explicit filter needed."""
        form = self._form(e_needs_h=['Active Prereq'])
        snap = snapshot_from_form_state(form, form['name'], form['aliases'])
        assert snap['e_needs_h'] == ['Active Prereq']
        assert not is_form_dirty_vs_snapshot(snap, form)


# ============================================================================
# build_explain_summary — Adjustments section rendering
# ============================================================================

def _minimal_breakdown(**overrides):
    """Build the minimal dict shape that _explain_summary_table consumes."""
    bd = {
        'node': 'X',
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


class TestExplainSummaryAdjustments:
    def test_no_adjustments_section_when_all_trivial(self):
        """With weight=1, density=1, no goal boost: no Adjustments header."""
        table = build_explain_summary(_minimal_breakdown(), normalized=80)
        text = _render_text(table)
        assert "Adjustments" not in text
        assert "Density" not in text
        assert "Context Weight" not in text

    def test_density_only_renders_row(self):
        bd = _minimal_breakdown(context_adjustment={
            'weight': 1.0, 'n_bucket': 17, 'alpha': 0.3,
            'density_mult': 0.432, 'combined_multiplier': 0.432,
        })
        table = build_explain_summary(bd, normalized=50)
        text = _render_text(table)
        assert "Adjustments" in text
        assert "Density" in text
        assert "n=17" in text
        assert "\u03b1=0.30" in text
        assert "Context Weight" not in text
        assert "Goal Boost" not in text

    def test_weight_only_renders_row(self):
        bd = _minimal_breakdown(context_adjustment={
            'weight': 2.0, 'n_bucket': 5, 'alpha': 0.0,
            'density_mult': 1.0, 'combined_multiplier': 2.0,
        })
        table = build_explain_summary(bd, normalized=50)
        text = _render_text(table)
        assert "Context Weight" in text
        assert "\u00d72.000" in text
        assert "Density" not in text

    def test_goal_boost_and_context_both_render(self):
        bd = _minimal_breakdown(
            goal_boost={'multiplier': 1.5, 'goal': 'Health', 'rank': 1},
            context_adjustment={
                'weight': 2.0, 'n_bucket': 17, 'alpha': 0.3,
                'density_mult': 0.432, 'combined_multiplier': 1.296,
            },
        )
        table = build_explain_summary(bd, normalized=50)
        text = _render_text(table)
        assert "Goal Boost" in text
        assert "rank #1" in text
        assert "Health" in text
        assert "Context Weight" in text
        assert "Density" in text
        assert "Combined" in text

    def test_raw_annotation_updated_when_adjustments_present(self):
        """When Adjustments section shows, Raw row gets the short summary."""
        bd = _minimal_breakdown(context_adjustment={
            'weight': 2.0, 'n_bucket': 1, 'alpha': 0.0,
            'density_mult': 1.0, 'combined_multiplier': 2.0,
        })
        table = build_explain_summary(bd, normalized=50)
        text = _render_text(table)
        # Old inline annotation should not appear any more
        assert "includes goal boost" not in text
        assert "all adjustments applied" in text

    def test_ineligible_still_shows_block_reason(self):
        bd = _minimal_breakdown(eligible=False, block_reason="Blocked")
        table = build_explain_summary(bd, normalized=None)
        text = _render_text(table)
        assert "Blocked" in text
