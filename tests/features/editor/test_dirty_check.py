"""The unsaved-changes check: the form against its pristine snapshot."""
from skilltree.features.editor.form import (
    build_editor_snapshot, is_form_dirty_vs_snapshot, NEW_NODE_SNAPSHOT,
    snapshot_from_form_state, editor_form_values,
)
from skilltree.domain.time import (
    ALL_WEEKDAYS,
)
import pytest
from skilltree.store.graph.manager import GraphManager


# ============================================================================
# is_form_dirty_vs_snapshot — X-button close-prompt regression tests
# ============================================================================

class TestIsFormDirtyVsSnapshot:
    """Pin the dirty-state detection behind the Node Editor's X-close prompt.

    Snapshot-based design: populate_editor stores a pristine snapshot of the
    form values it just wrote; the dirty check compares current form State to
    that snapshot. This eliminates false-positives from display transformations
    and from the title-case linter rewriting names/aliases on save.
    """

    @staticmethod
    def _seed(mgr, **overrides):
        from skilltree.domain.models import Node
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

    def test_pristine_form_is_not_dirty(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        assert not is_form_dirty_vs_snapshot(snap, self._form_from_snapshot(snap))

    def test_edge_change_detected(self, services):
        """Adding a prerequisite must count as dirty."""
        mgr = GraphManager()
        self._seed(mgr, name='Target')
        node = self._seed(mgr, name='Alpha')
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['e_needs_h'] = ['Target']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_link_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['resource_links'] = {'obsidian': ['notes/alpha.md']}
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_time_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['time_m'] = (form['time_m'] or 0) + 1
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_context_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['context'] = 'Body'
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_type_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['n_type'] = 'Action'
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_status_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['status_done'] = ['Done']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_alias_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['aliases'] = ['AlphaAlias']
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_description_change_detected(self, services):
        mgr = GraphManager()
        node = self._seed(mgr)
        snap = build_editor_snapshot(mgr, services.events, node.name)
        form = self._form_from_snapshot(snap)
        form['desc'] = 'updated description'
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_snapshot_none_returns_not_dirty(self):
        """No baseline snapshot — can't be dirty regardless of form values."""
        assert not is_form_dirty_vs_snapshot(None, {
            'name': 'Anything', 'desc': 'whatever',
            'resource_links': {'drive': ['a', 'b']}, 'aliases': ['X'],
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

    # Written around the Resource sections new databases used to start with.
    @pytest.mark.usefixtures("legacy_resource_sections")
    def test_resource_link_change_detected(self, services):
        """Adding a link in any section counts as dirty; an empty row does not."""
        mgr = GraphManager()
        node = self._seed(mgr, name='WithLinks', resource_links={'drive': ['a.pdf']})
        snap = build_editor_snapshot(mgr, services.events, node.name)
        assert snap['resource_links'] == {'drive': ['a.pdf']}
        form = self._form_from_snapshot(snap)
        form['resource_links'] = {'drive': ['a.pdf'], 'website': ['']}
        assert not is_form_dirty_vs_snapshot(snap, form)
        form['resource_links'] = {'drive': ['a.pdf', 'b.pdf']}
        assert is_form_dirty_vs_snapshot(snap, form)

    def test_post_save_alias_lint_does_not_cause_false_positive(self, services):
        """Regression: set_aliases title-case-lints aliases on save. After the
        post-save snapshot refresh, a form holding the linted alias must not
        flag as dirty."""
        from skilltree.store import settings
        from skilltree.domain.names import NAME_FORMAT_TITLE
        settings.NAME_FORMATTING.set({'mode': NAME_FORMAT_TITLE})
        mgr = GraphManager()
        node = self._seed(mgr)
        # Save aliases through the manager — which applies the linter.
        mgr.set_aliases(node.name, ['alpha alias'])
        # Snapshot refreshed from DB now holds the *linted* alias.
        snap = build_editor_snapshot(mgr, services.events, node.name)
        assert snap['aliases'] == ['Alpha Alias']
        # Form holds the linted alias too (input was re-rendered from the store).
        form = self._form_from_snapshot(snap)
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_dormant_prereq_is_included_in_editor_snapshot(self, services):
        """The pristine snapshot mirrors dormant relationships shown in the form."""
        from skilltree.domain.models import EDGE_NEEDS_HARD
        mgr = GraphManager()
        target = self._seed(mgr, name='Target Goal', type='Goal')
        # Active prereq — visible in dropdown, will appear in form State.
        active = self._seed(mgr, name='Active Prereq', type='Learn')
        # Dormant prereq — visible in the relationship dropdown alongside active nodes.
        dormant = self._seed(mgr, name='Dormant Prereq', type='Action', dormant=1)
        mgr.add_edge(active.name, target.name, EDGE_NEEDS_HARD)
        mgr.add_edge(dormant.name, target.name, EDGE_NEEDS_HARD)
        snap = build_editor_snapshot(mgr, services.events, target.name)
        assert snap['e_needs_h'] == ['Active Prereq', 'Dormant Prereq']
        # Form State includes the same dormant relationship, so it is still pristine.
        form = self._form_from_snapshot(snap)
        assert not is_form_dirty_vs_snapshot(snap, form)


# ============================================================================
# snapshot_from_form_state — post-save pristine snapshot built directly from
# form State rather than a DB round-trip. This is the bug-fix path for the
# persistent "unsaved changes" false-positive after save: the DB round-trip
# through build_editor_snapshot re-applied friendly_time_estimates, which
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
            'resource_links': {},
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
        friendly_time_estimates could pick 'weeks' from large hour values,
        diverging both time_unit and time_o/m/p. Snapshotting form State
        directly preserves the user's selected unit."""
        # 500/600/700 hours — friendly_time_estimates would pick 'weeks'.
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
            resource_links=None,
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
        assert snap['resource_links'] == {}
        assert snap['status_done'] == []
        assert snap['time_mode'] == []
        # Reconstitute the form the way Dash would (with the defaults the
        # input components emit) and confirm not dirty.
        form_for_check = dict(form)
        form_for_check.update({
            'desc': '', 'context': '', 'subctx': '',
            'resource_links': {},
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
            resource_links={},
            time_mode=[], value_mode=[], priority_rank='none', aliases=[''],
            time_habit_mode=[],
            habit_duration=0, habit_duration_unit='weeks',
            habit_intensity_o=0, habit_intensity_m=0, habit_intensity_p=0,
            habit_intensity_unit='min_per_session',
            habit_days=list(ALL_WEEKDAYS),
            dormancy=None,
        )
        base.update(overrides)
        return base

    def test_keys_match_new_node_snapshot_schema(self):
        """The form-values dict must carry exactly the snapshot's key set —
        no missing field (false positive) and no extra field (silent no-op)."""
        produced = editor_form_values(**self._full_kwargs())
        assert set(produced.keys()) == set(NEW_NODE_SNAPSHOT.keys())

    def test_keys_match_built_snapshot_schema(self, services):
        from skilltree.domain.models import Node
        mgr = GraphManager()
        mgr.add_node(Node(name='Alpha', type='Learn', description='x',
                          value=5, interest=5, difficulty=5, status='Open',
                          time_o=40, time_m=80, time_p=160, context='Mind'))
        snap = build_editor_snapshot(mgr, services.events, 'Alpha')
        produced = editor_form_values(**self._full_kwargs())
        assert set(produced.keys()) == set(snap.keys())

    def test_blank_form_not_dirty_vs_new_node_snapshot(self):
        """A blank new-node form (component defaults) built through the helper
        must not register dirty against NEW_NODE_SNAPSHOT."""
        blank = editor_form_values(**self._full_kwargs(
            name='', n_type='', desc='', context='', subctx='', time_o=None, time_m=None,
            time_p=None, time_unit='weeks',
        ))
        assert not is_form_dirty_vs_snapshot(NEW_NODE_SNAPSHOT, blank)

    def test_new_node_starts_without_an_estimate(self):
        """The estimate is the user's own call: nothing is pre-filled, and an
        empty bracket is refused on save."""
        from skilltree.domain.time import time_estimate_problem
        bracket = [NEW_NODE_SNAPSHOT[k] for k in ('time_o', 'time_m', 'time_p')]
        assert bracket == [None, None, None]
        assert time_estimate_problem(*bracket)

    def test_omitting_habit_args_uses_layout_defaults(self, services):
        """A caller with no habit state (the historical modal-gate case) gets
        the same habit defaults the editor components emit — so an unchanged
        non-habit node does not falsely register dirty."""
        from skilltree.domain.models import Node
        mgr = GraphManager()
        mgr.add_node(Node(name='Alpha', type='Learn', description='hello',
                          value=5, interest=5, difficulty=5, status='Open',
                          time_o=40, time_m=80, time_p=160, context='Mind'))
        snap = build_editor_snapshot(mgr, services.events, 'Alpha')
        # Mirror the snapshot's non-habit fields but pass NO habit_* kwargs.
        form = editor_form_values(
            name='Alpha', n_type='Learn', desc='hello',
            context='Mind', subctx='',
            status_done=[], val=5, interest=5, diff=5,
            time_o=snap['time_o'], time_m=snap['time_m'], time_p=snap['time_p'],
            time_unit=snap['time_unit'],
            e_needs_h=[], e_needs_s=[], e_supp_h=[], e_supp_s=[], e_helps=[],
            resource_links={},
            time_mode=[], value_mode=[], priority_rank='none', aliases=[''],
            dormancy=snap['dormancy'],
        )
        assert not is_form_dirty_vs_snapshot(snap, form)

    def test_unchanged_loaded_node_not_dirty(self, services):
        """End-to-end: a loaded node's form (mirroring its snapshot) routed
        through the helper is not dirty — the core false-positive case."""
        from skilltree.domain.models import Node
        mgr = GraphManager()
        mgr.add_node(Node(name='Habit Node', type='Action', description='d',
                          value=5, interest=5, difficulty=5, status='Open',
                          context='Mind',
                          time_o=40, time_m=80, time_p=160, time_mode='habit',
                          habit_duration=6, habit_duration_unit='weeks',
                          habit_intensity_o=20, habit_intensity_m=30,
                          habit_intensity_p=45,
                          habit_intensity_unit='min_per_session'))
        snap = build_editor_snapshot(mgr, services.events, 'Habit Node')
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
            resource_links=snap['resource_links'],
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
            dormancy=snap['dormancy'],
        )
        assert not is_form_dirty_vs_snapshot(snap, form)
