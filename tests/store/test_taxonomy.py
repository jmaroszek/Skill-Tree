"""Carrying context and subcontext edits onto nodes."""
from support.graphs import make_node


# ============================================================================
# Node Migration
# ============================================================================

class TestNodeMigration:
    def test_find_orphaned_nodes_no_removals(self, mgr):
        mgr.add_node(make_node("A", context="Mind"))
        result = mgr.find_orphaned_nodes('context', ["Mind", "Body"], ["Mind", "Body"])
        assert result == {}

    def test_find_orphaned_nodes_with_removal(self, mgr):
        mgr.add_node(make_node("A", context="Mind"))
        mgr.add_node(make_node("B", context="Body"))
        result = mgr.find_orphaned_nodes('context', ["Mind", "Body"], ["Body"])
        assert "Mind" in result
        assert len(result["Mind"]) == 1
        assert result["Mind"][0].name == "A"
        assert "Body" not in result

    def test_find_orphaned_nodes_no_affected(self, mgr):
        mgr.add_node(make_node("A", context="Body"))
        result = mgr.find_orphaned_nodes('context', ["Mind", "Body"], ["Body"])
        assert result == {}

    def test_find_orphaned_nodes_type(self, mgr):
        mgr.add_node(make_node("A", type="Learn"))
        mgr.add_node(make_node("B", type="Goal"))
        result = mgr.find_orphaned_nodes('type', ["Learn", "Goal"], ["Goal"])
        assert "Learn" in result
        assert result["Learn"][0].name == "A"

    def test_apply_migration_context(self, mgr):
        mgr.add_node(make_node("A", context="OldCtx"))
        mgr.add_node(make_node("B", context="OldCtx"))
        mgr.apply_migration('context', {"OldCtx": "NewCtx"})
        assert mgr.get_node("A").context == "NewCtx"
        assert mgr.get_node("B").context == "NewCtx"

    def test_apply_migration_clear(self, mgr):
        mgr.add_node(make_node("A", context="OldCtx"))
        mgr.apply_migration('context', {"OldCtx": "__clear__"})
        assert mgr.get_node("A").context is None

    def test_apply_migration_context_clears_invalid_subcontexts(self, mgr):
        mgr.add_node(make_node("A", context="Mind", subcontext="Rational"))
        new_subs = {"Body": ["Stress", "Sleep"]}
        mgr.apply_migration('context', {"Mind": "Body"}, new_subcontexts=new_subs)
        node = mgr.get_node("A")
        assert node.context == "Body"
        assert node.subcontext is None  # "Rational" not valid under "Body"

    def test_apply_migration_subcontext(self, mgr):
        mgr.add_node(make_node("A", context="Mind", subcontext="OldSub"))
        mgr.apply_migration('subcontext', {"OldSub": "NewSub"})
        assert mgr.get_node("A").subcontext == "NewSub"

    def test_apply_migration_empty_remap(self, mgr):
        mgr.add_node(make_node("A", context="Mind"))
        mgr.apply_migration('context', {})
        assert mgr.get_node("A").context == "Mind"  # unchanged


class TestApplyPerNodeMigrations:
    """Per-node ctx/sub remap iteration. Uses the temp_database fixture so
    actual DB writes can be observed."""

    def _apply(self, manager, entries, ctx_vals, sub_vals, new_subcontexts=None):
        from skilltree.features.settings.migration import _apply_per_node_migrations
        _apply_per_node_migrations(manager, entries, ctx_vals, sub_vals,
                                    new_subcontexts or {})

    @staticmethod
    def _entry(name, old='Social'):
        return {'field': 'context', 'old_value': old, 'node_name': name,
                'group_idx': 0}

    def test_per_node_ctx_change_writes_each_node_independently(self, mgr):
        """The whole point of the redesign — different nodes go to different ctx."""
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        mgr.add_node(make_node('B', context='Social', subcontext='Morality'))
        mgr.add_node(make_node('C', context='Social', subcontext='Influence'))
        entries = [self._entry('A'), self._entry('B'), self._entry('C')]
        new_subs = {'Mind': ['Focus'], 'Body': ['Strength']}
        self._apply(mgr, entries, ['Mind', 'Body', 'Mind'],
                    ['Focus', 'Strength', 'Focus'], new_subs)
        nodes = {n.name: n for n in mgr.get_all_nodes()}
        assert nodes['A'].context == 'Mind' and nodes['A'].subcontext == 'Focus'
        assert nodes['B'].context == 'Body' and nodes['B'].subcontext == 'Strength'
        assert nodes['C'].context == 'Mind' and nodes['C'].subcontext == 'Focus'

    def test_keep_sentinel_skips_dimension(self, mgr):
        """`__keep__` must not call apply_node_migration for that field."""
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        # Change ctx but keep sub
        self._apply(mgr, entries, ['Mind'], ['__keep__'],
                    {'Mind': ['Dating', 'Other']})
        n = mgr.get_node('A')
        assert n.context == 'Mind'
        assert n.subcontext == 'Dating'  # preserved

    def test_keep_for_ctx_only_changes_sub(self, mgr):
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, ['__keep__'], ['Morality'],
                    {'Social': ['Morality']})
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Morality'

    def test_clear_sentinel_nullifies_field(self, mgr):
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, ['__keep__'], ['__clear__'])
        n = mgr.get_node('A')
        assert n.subcontext is None

    def test_both_keep_is_no_op(self, mgr):
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, ['__keep__'], ['__keep__'])
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Dating'

    def test_ctx_change_clears_sub_when_invalid_under_new_ctx(self, mgr):
        """`apply_node_migration` already clears sub when it's invalid under
        the new ctx — verify the per-node loop preserves that contract."""
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        # Mind has its own subs; Dating isn't one of them
        new_subs = {'Mind': ['Focus', 'Sleep']}
        self._apply(mgr, entries, ['Mind'], ['__keep__'], new_subs)
        n = mgr.get_node('A')
        assert n.context == 'Mind'
        assert n.subcontext is None

    def test_empty_entries_is_no_op(self, mgr):
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        self._apply(mgr, [], [], [])
        n = mgr.get_node('A')
        assert n.context == 'Social'

    def test_mismatched_value_lengths_handled_gracefully(self, mgr):
        """If Dash delivers a shorter values list than entries, extra entries
        are skipped (defensive — shouldn't normally happen)."""
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        mgr.add_node(make_node('B', context='Social', subcontext='Morality'))
        entries = [self._entry('A'), self._entry('B')]
        # Only A has a value; B should be untouched
        self._apply(mgr, entries, ['Mind'], ['Focus'], {'Mind': ['Focus']})
        nodes = {n.name: n for n in mgr.get_all_nodes()}
        assert nodes['A'].context == 'Mind'
        assert nodes['B'].context == 'Social'  # untouched

    def test_none_values_treated_as_no_change(self, mgr):
        mgr.add_node(make_node('A', context='Social', subcontext='Dating'))
        entries = [self._entry('A')]
        self._apply(mgr, entries, [None], [None])
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Dating'

    def test_subcontext_only_remap_via_sub_nodes_entries(self, mgr):
        """sub_nodes entries are also dicts with 'node_name' — same helper handles them."""
        mgr.add_node(make_node('A', context='STEM', subcontext='Psychology'))
        # field is 'subcontext' for sub_nodes entries, but the helper only
        # uses node_name regardless of field
        entries = [{'field': 'subcontext', 'old_value': 'STEM > Psychology',
                    'node_name': 'A', 'group_idx': 0}]
        self._apply(mgr, entries, ['Social'], ['Psychology'],
                    {'STEM': [], 'Social': ['Psychology']})
        n = mgr.get_node('A')
        assert n.context == 'Social'
        assert n.subcontext == 'Psychology'


class TestFindOrphanedSubcontextPairs:
    """DB wrapper — confirms pair detection plus node lookup, keyed by display label."""

    def test_move_flags_only_pair_matched_nodes(self, mgr):
        mgr.add_node(make_node("A", context="STEM", subcontext="Psychology"))
        mgr.add_node(make_node("B", context="STEM", subcontext="Math"))
        old = {"STEM": ["Psychology", "Math"]}
        new = {"STEM": ["Math"], "Social": ["Psychology"]}
        result = mgr.find_orphaned_subcontext_pairs(old, new, ["STEM", "Social"])
        assert "STEM > Psychology" in result
        assert [n.name for n in result["STEM > Psychology"]] == ["A"]
        assert "STEM > Math" not in result

    def test_pair_removed_but_no_nodes_returns_empty(self, mgr):
        mgr.add_node(make_node("A", context="STEM", subcontext="Math"))
        old = {"STEM": ["Psychology", "Math"]}
        new = {"STEM": ["Math"]}
        result = mgr.find_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert result == {}

    def test_no_orphans_when_unchanged(self, mgr):
        mgr.add_node(make_node("A", context="STEM", subcontext="Math"))
        old = {"STEM": ["Math"]}
        new = {"STEM": ["Math"]}
        result = mgr.find_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert result == {}
