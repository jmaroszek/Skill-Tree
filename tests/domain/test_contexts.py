"""Which subcontext pairs a taxonomy edit leaves behind."""
from skilltree.domain.contexts import compute_orphaned_subcontext_pairs


# ============================================================================
# Subcontext-Pair Orphan Detection
# ============================================================================

class TestOrphanedSubcontextPairs:
    """Pure-helper tests — no DB. Identifies (ctx, sub) pairs that no longer exist."""

    def test_move_between_parents(self):
        old = {"STEM": ["Psychology"]}
        new = {"Social": ["Psychology"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM", "Social"])
        assert pairs == [("STEM", "Psychology")]

    def test_rename_in_place(self):
        old = {"STEM": ["Psychology"]}
        new = {"STEM": ["Cognitive"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert pairs == [("STEM", "Psychology")]

    def test_pure_delete(self):
        old = {"STEM": ["Psychology", "Math"]}
        new = {"STEM": ["Math"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert pairs == [("STEM", "Psychology")]

    def test_parent_context_removed_is_skipped(self):
        # Psychology "moves" but its old parent STEM no longer exists in new_contexts —
        # those nodes are handled by the context-orphan path, not this one.
        old = {"STEM": ["Psychology"]}
        new = {"Social": ["Psychology"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["Social"])
        assert pairs == []

    def test_same_name_added_under_new_parent_does_not_orphan(self):
        old = {"STEM": ["Psychology"]}
        new = {"STEM": ["Psychology"], "Arts": ["Psychology"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM", "Arts"])
        assert pairs == []

    def test_empty_old(self):
        pairs = compute_orphaned_subcontext_pairs({}, {"STEM": ["Math"]}, ["STEM"])
        assert pairs == []

    def test_unchanged_returns_empty(self):
        old = {"STEM": ["Math"]}
        new = {"STEM": ["Math"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM"])
        assert pairs == []

    def test_combined_move_and_rename(self):
        old = {"STEM": ["Psychology", "Bio"], "Mind": ["Sleep"]}
        new = {"STEM": ["Biology"], "Social": ["Psychology"], "Mind": ["Sleep"]}
        pairs = compute_orphaned_subcontext_pairs(old, new, ["STEM", "Social", "Mind"])
        assert sorted(pairs) == sorted([("STEM", "Psychology"), ("STEM", "Bio")])
