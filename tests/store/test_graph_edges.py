"""Edges: adding and removing them, cycles, and the editor's sync."""
import pytest
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from support.graphs import make_node


# ============================================================================
# Edge Operations
# ============================================================================

class TestEdgeOperations:
    def test_add_and_get_edge(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_duplicate_edge_ignored(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        assert len(mgr.get_edges()) == 1

    def test_remove_edge(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.remove_edge("A", "B", EDGE_NEEDS_HARD)
        assert len(mgr.get_edges()) == 0

    def test_pair_conflict_rejected(self, mgr):
        """Directional edges (Hard/Soft) on a pair are mutually exclusive."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # Opposite direction Hard/Soft is rejected as a cycle, before
        # reaching the pair-conflict check; either way the new row is denied.
        with pytest.raises(ValueError, match="cycle|already exists"):
            mgr.add_edge("B", "A", EDGE_NEEDS_SOFT)
        assert len(mgr.get_edges()) == 1

    def test_helps_coexists_with_directional_edge(self, mgr):
        """Per design (composite PK on source/target/type), Helps may coexist
        with a Hard or Soft prereq on the same pair — a node that unlocks
        another can also synergize with it."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "B", EDGE_HELPS)  # should NOT raise
        edges = mgr.get_edges()
        assert len(edges) == 2
        types = {e['type'] for e in edges}
        assert types == {EDGE_NEEDS_HARD, EDGE_HELPS}

    def test_helps_canonicalization_collapses_reverse_insert(self, mgr):
        """Fix 6: (A,B,Helps) and (B,A,Helps) are the same fact — only one row."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("B", "A", EDGE_HELPS)
        mgr.add_edge("A", "B", EDGE_HELPS)
        edges = mgr.get_edges()
        assert len(edges) == 1
        # Canonical form: lexically-sorted endpoints
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_HELPS

    def test_remove_nonexistent_edge_no_error(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.remove_edge("A", "B", EDGE_NEEDS_HARD)  # should not raise


# ============================================================================
# Cycle Detection
# ============================================================================

class TestCycleDetection:
    def test_self_loop_rejected(self, mgr):
        mgr.add_node(make_node("A"))
        with pytest.raises(ValueError, match="[Ss]elf-loop"):
            mgr.add_edge("A", "A", EDGE_NEEDS_HARD)

    def test_self_loop_rejected_for_all_edge_types(self, mgr):
        """Fix 3: self-loops rejected on Hard, Soft, AND Helps."""
        mgr.add_node(make_node("A"))
        for etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS):
            with pytest.raises(ValueError, match="[Ss]elf-loop"):
                mgr.add_edge("A", "A", etype)

    def test_simple_cycle_rejected(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("B", "A", EDGE_NEEDS_HARD)

    def test_transitive_cycle_rejected(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("C", "A", EDGE_NEEDS_HARD)

    def test_soft_edge_cycle_also_rejected(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_SOFT)
        with pytest.raises(ValueError, match="cycle"):
            mgr.add_edge("B", "A", EDGE_NEEDS_SOFT)

    def test_helps_edge_allows_bidirectional(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        mgr.add_edge("B", "A", EDGE_HELPS)  # should not raise


# ============================================================================
# Sync Edges
# ============================================================================

class TestSyncEdges:
    def test_sync_replaces_needs_hard(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "C", EDGE_NEEDS_HARD)
        # Replace A with B as hard prereq
        mgr.sync_edges("C", needs_hard=["B"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        hard_edges = [e for e in edges if e['type'] == EDGE_NEEDS_HARD]
        assert len(hard_edges) == 1
        assert hard_edges[0]['source'] == "B"

    def test_sync_replaces_helps(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        # Sync A: replace helps from B to C
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=[], supports_soft=[], helps=["C"])
        edges = mgr.get_edges()
        helps_edges = [e for e in edges if e['type'] == EDGE_HELPS]
        assert len(helps_edges) == 1
        assert helps_edges[0]['target'] == "C"

    def test_sync_supports_creates_reverse_edges(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        # A supports_hard B means B Needs_Hard A → edge from A to B
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "A"
        assert edges[0]['target'] == "B"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_sync_rejects_pair_conflict_in_form(self, mgr):
        """Fix 6: declaring the same pair in two different edge buckets raises
        a clear error before any DB mutation. Replaces the old behavior where
        a (B needs A, B supports A) form would silently skip the cycle-creating
        edge — now caught earlier as a pair conflict at form-validation time."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        with pytest.raises(ValueError, match="[Oo]nly one edge type"):
            mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=["A"], supports_soft=[], helps=[])

    def test_sync_with_none_args(self, mgr):
        mgr.add_node(make_node("A"))
        # None args should be treated as empty lists
        mgr.sync_edges("A", None, None, None, None, None)
        assert len(mgr.get_edges()) == 0


# ============================================================================
# sync_edges without resources parameter
# ============================================================================

class TestSyncEdgesWithoutResources:
    """Tests that sync_edges works without the removed resources parameter."""

    def test_sync_hard_and_soft_needs(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("C"))
        mgr.sync_edges("C",
                        needs_hard=["A"], needs_soft=["B"],
                        supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        hard = [e for e in edges if e['type'] == EDGE_NEEDS_HARD]
        soft = [e for e in edges if e['type'] == EDGE_NEEDS_SOFT]
        assert len(hard) == 1 and hard[0]['source'] == "A"
        assert len(soft) == 1 and soft[0]['source'] == "B"

    def test_sync_supports_direction(self, mgr):
        mgr.add_node(make_node("Source", status="Done"))
        mgr.add_node(make_node("Target"))
        mgr.sync_edges("Source",
                        needs_hard=[], needs_soft=[],
                        supports_hard=["Target"], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['source'] == "Source"
        assert edges[0]['target'] == "Target"
        assert edges[0]['type'] == EDGE_NEEDS_HARD

    def test_sync_helps(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.sync_edges("A",
                        needs_hard=[], needs_soft=[],
                        supports_hard=[], supports_soft=[], helps=["B"])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['type'] == EDGE_HELPS

    def test_sync_clears_old_edges(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("C"))
        mgr.sync_edges("C",
                        needs_hard=["A"], needs_soft=[],
                        supports_hard=[], supports_soft=[], helps=[])
        assert len(mgr.get_edges()) == 1
        # Now sync again with different edges
        mgr.sync_edges("C",
                        needs_hard=[], needs_soft=["B"],
                        supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        assert len(edges) == 1
        assert edges[0]['type'] == EDGE_NEEDS_SOFT
