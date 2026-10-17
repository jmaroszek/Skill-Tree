"""What the migration dialog lists for a taxonomy edit."""


class TestBuildMigrationContent:
    """Per-node UI generation, smart defaults, and mapping-store shape.

    Walks the rendered Dash component tree to verify each per-node dropdown's
    default value, since the smart-default logic is the headline feature of
    the flexible-migration redesign.
    """

    @staticmethod
    def _walk(children):
        """Return {(type, idx): {'value': v, 'options': [...]}} for every
        pattern-matched component in the rendered tree."""
        found = {}
        def visit(el):
            if el is None or isinstance(el, (str, int, float, bool)):
                return
            ch = getattr(el, 'children', None)
            if isinstance(ch, list):
                for x in ch: visit(x)
            elif ch is not None:
                visit(ch)
            eid = getattr(el, 'id', None)
            if isinstance(eid, dict):
                t, i = eid.get('type'), eid.get('index')
                found[(t, i)] = {
                    'value': getattr(el, 'value', None),
                    'options': getattr(el, 'options', None),
                }
        for c in (children if isinstance(children, list) else [children]):
            visit(c)
        return found

    @staticmethod
    def _ns(name, **attrs):
        from types import SimpleNamespace
        return SimpleNamespace(name=name, **attrs)

    def _build(self, **kwargs):
        from skilltree.features.settings.migration import build_migration_content
        return build_migration_content(**kwargs)

    # --- Pure-rename smart defaults -----------------------------------------

    def test_pure_rename_prefills_each_node_with_original_subcontext(self):
        """The headline scenario — Social → People preserving 5 subcontexts."""
        nodes = [
            self._ns('A', subcontext='Dating'),
            self._ns('B', subcontext='Morality'),
            self._ns('C', subcontext='Influence'),
            self._ns('D', subcontext='Relationships'),
            self._ns('E', subcontext='Psychology'),
        ]
        children, mapping = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating', 'Morality', 'Influence',
                                               'Relationships', 'Psychology']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        for i, n in enumerate(nodes):
            assert sels[('migration-cgc-node', i)]['value'] == 'People'
            assert sels[('migration-cgs-node', i)]['value'] == n.subcontext

    def test_rename_clears_subcontext_absent_from_new_context(self):
        """A node tagged with a subcontext the new context doesn't have
        should default to __clear__, not to a random first-of-list."""
        nodes = [
            self._ns('Keep', subcontext='Dating'),
            self._ns('Drop', subcontext='Vanished'),
        ]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-cgs-node', 0)]['value'] == 'Dating'
        assert sels[('migration-cgs-node', 1)]['value'] == '__clear__'

    def test_rename_with_node_having_no_subcontext_uses_fallback(self):
        nodes = [self._ns('NoSub', subcontext=None)]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating', 'Friends']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-cgc-node', 0)]['value'] == 'People'
        # Fallback should be the first available sub for the new context
        assert sels[('migration-cgs-node', 0)]['value'] == 'Dating'

    def test_rename_with_no_subcontexts_under_new_context(self):
        """Renamed-to has no subs at all → fallback is __keep__."""
        nodes = [self._ns('NoSub', subcontext=None)]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': []},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-cgs-node', 0)]['value'] == '__keep__'

    # --- No-rename fallback --------------------------------------------------

    def test_no_rename_falls_back_to_first_new_ctx_uniformly(self):
        """With no rename map, every per-node row
        should default to (first_new_ctx, first_sub) — the user can adjust."""
        nodes = [self._ns('A', subcontext='Dating'),
                 self._ns('B', subcontext='Morality')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['Mind', 'Body'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Mind': ['Sleep'], 'Body': ['Strength']},
            rename_map={},
        )
        sels = self._walk(children)
        for i in range(2):
            assert sels[('migration-cgc-node', i)]['value'] == 'Mind'
            assert sels[('migration-cgs-node', i)]['value'] == 'Sleep'

    def test_no_rename_with_empty_new_contexts(self):
        nodes = [self._ns('A', subcontext='Dating')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': [], 'subcontext': [], 'type': []},
            subcontexts_by_context={},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-cgc-node', 0)]['value'] == '__keep__'

    # --- Subcontext-orphan smart default ------------------------------------

    def test_subcontext_orphan_smart_default_when_unique_new_parent(self):
        """`Old > Sub` label and `Sub` lives under exactly one new ctx →
        pre-pick that (parent, sub) pair on every node row."""
        nodes = [self._ns('A', context='STEM'),
                 self._ns('B', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM > Psychology': nodes}},
            new_values_by_field={'context': ['STEM', 'Social'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'STEM': ['Math'], 'Social': ['Psychology']},
            rename_map={},
        )
        sels = self._walk(children)
        for i in range(2):
            assert sels[('migration-sgc-node', i)]['value'] == 'Social'
            assert sels[('migration-sgs-node', i)]['value'] == 'Psychology'

    def test_subcontext_orphan_falls_back_when_sub_under_multiple_parents(self):
        """`Sub` under multiple new parents → can't auto-pick → __keep__."""
        nodes = [self._ns('A', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM > Psychology': nodes}},
            new_values_by_field={'context': ['Social', 'Mind'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Social': ['Psychology'], 'Mind': ['Psychology']},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-sgc-node', 0)]['value'] == '__keep__'
        assert sels[('migration-sgs-node', 0)]['value'] == '__keep__'

    def test_subcontext_orphan_falls_back_when_sub_under_no_new_parent(self):
        nodes = [self._ns('A', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM > Vanished': nodes}},
            new_values_by_field={'context': ['STEM'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'STEM': ['Math']},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-sgc-node', 0)]['value'] == '__keep__'

    # --- Mapping store shape -------------------------------------------------

    def test_mapping_ctx_nodes_indexed_to_match_dropdown_indices(self):
        nodes = [self._ns('A', subcontext='Dating'),
                 self._ns('B', subcontext='Morality'),
                 self._ns('C', subcontext='Influence')]
        _, mapping = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating', 'Morality', 'Influence']},
            rename_map={'Social': 'People'},
        )
        assert len(mapping['ctx_nodes']) == 3
        for i, n in enumerate(nodes):
            assert mapping['ctx_nodes'][i]['node_name'] == n.name
            assert mapping['ctx_nodes'][i]['old_value'] == 'Social'
            assert mapping['ctx_nodes'][i]['group_idx'] == 0
            assert mapping['ctx_nodes'][i]['field'] == 'context'

    def test_multiple_ctx_orphan_groups_get_distinct_group_idx(self):
        """Two old contexts removed → two cards, each entry tagged with its group_idx."""
        social = [self._ns('A', subcontext='Dating')]
        hobbies = [self._ns('X', subcontext='Reading'),
                   self._ns('Y', subcontext='Reading')]
        _, mapping = self._build(
            orphans_by_field={'context': {'Social': social, 'Hobbies': hobbies}},
            new_values_by_field={'context': ['Mind'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Mind': ['Sleep']},
            rename_map={},
        )
        assert len(mapping['ctx_nodes']) == 3
        groups = {e['old_value']: e['group_idx'] for e in mapping['ctx_nodes']}
        assert groups['Social'] != groups['Hobbies']

    def test_no_orphans_returns_empty_lists(self):
        children, mapping = self._build(
            orphans_by_field={},
            new_values_by_field={'context': [], 'subcontext': [], 'type': []},
            subcontexts_by_context={},
            rename_map={},
        )
        assert children == []
        assert mapping == {'type': [], 'ctx_nodes': [], 'sub_nodes': []}

    def test_type_orphans_use_per_node_dropdowns_unchanged(self):
        """Type path is untouched — each node still gets a migration-dropdown."""
        nodes = [self._ns('A'), self._ns('B')]
        children, mapping = self._build(
            orphans_by_field={'type': {'OldType': nodes}},
            new_values_by_field={'context': [], 'subcontext': [], 'type': ['NewType']},
            subcontexts_by_context={},
            rename_map={},
        )
        sels = self._walk(children)
        assert ('migration-dropdown', 0) in sels
        assert ('migration-dropdown', 1) in sels
        assert all(s['value'] == 'NewType' for s in sels.values()
                   if s['value'] not in ('__keep__', '__clear__', None))
        assert len(mapping['type']) == 2
        assert mapping['type'][0]['node_name'] == 'A'

    def test_default_rename_map_arg_is_treated_as_empty(self):
        """rename_map=None should behave the same as rename_map={}."""
        nodes = [self._ns('A', subcontext='Dating')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating']},
            rename_map=None,
        )
        sels = self._walk(children)
        # No rename → fallback default ctx (first new), not preserve original sub
        assert sels[('migration-cgc-node', 0)]['value'] == 'People'

    # --- Bulk row presence and defaults -------------------------------------

    def test_bulk_row_renders_per_group_with_renamed_default(self):
        nodes = [self._ns('A', subcontext='Dating')]
        children, _ = self._build(
            orphans_by_field={'context': {'Social': nodes}},
            new_values_by_field={'context': ['People'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'People': ['Dating']},
            rename_map={'Social': 'People'},
        )
        sels = self._walk(children)
        assert sels[('migration-bulk-cgc', 0)]['value'] == 'People'
        # Bulk apply button is also rendered
        assert ('migration-bulk-cg-apply', 0) in sels

    def test_bulk_row_renders_for_subcontext_orphan_groups(self):
        nodes = [self._ns('A', context='STEM')]
        children, _ = self._build(
            orphans_by_field={'subcontext': {'STEM > Psychology': nodes}},
            new_values_by_field={'context': ['Social'], 'subcontext': [], 'type': []},
            subcontexts_by_context={'Social': ['Psychology']},
            rename_map={},
        )
        sels = self._walk(children)
        assert sels[('migration-bulk-sgc', 0)]['value'] == 'Social'
        assert ('migration-bulk-sg-apply', 0) in sels
