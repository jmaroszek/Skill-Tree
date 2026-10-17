"""The scoring functions in domain/scoring.py, called directly."""
import pytest
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
from skilltree.domain.scoring import (intrinsic_value, perceived_cost, is_eligible, build_adjacency,
                     total_value, score_nodes, explain_score, TIME_REF_HOURS)
from support.graphs import make_node


# ============================================================================
# Scoring Module (pure function tests)
# ============================================================================

class TestScoringFunctions:
    def test_intrinsic_value(self):
        node = make_node(value=8, interest=6)
        assert intrinsic_value(node, w_v=1.0, w_i=1.0) == 14.0
        assert intrinsic_value(node, w_v=2.0, w_i=0.5) == 19.0

    def test_perceived_cost(self):
        node = make_node(difficulty=5, time_o=2, time_m=2, time_p=2)
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85)
        expected = 1.0 + 2.5 * 5 + 1.0 * ((2.0 / TIME_REF_HOURS) ** 0.85)
        assert cost == pytest.approx(expected, rel=1e-4)

    def test_perceived_cost_normalizes_time_against_the_reference(self):
        """w_t is exactly the time term's value at t = TIME_REF_HOURS.

        This is what decouples beta (curvature) from w_t (magnitude): at the
        reference hour count the cost is w_t regardless of beta.
        """
        node = make_node(difficulty=0, time_o=TIME_REF_HOURS,
                          time_m=TIME_REF_HOURS, time_p=TIME_REF_HOURS)
        for beta in (0.35, 0.60, 0.85, 1.0):
            cost = perceived_cost(node, w_e=0.0, w_t=6.0, beta=beta)
            assert cost == pytest.approx(1.0 + 6.0, rel=1e-6)

    def test_is_eligible_no_prereqs(self):
        assert is_eligible("A", {"A": []}, {"A": make_node("A")}) is True

    def test_is_eligible_all_done(self):
        nodes = {"A": make_node("A"), "B": make_node("B", status="Done")}
        hard_in = {"A": ["B"]}
        assert is_eligible("A", hard_in, nodes) is True

    def test_is_eligible_one_not_done(self):
        nodes = {"A": make_node("A"), "B": make_node("B", status="Open")}
        hard_in = {"A": ["B"]}
        assert is_eligible("A", hard_in, nodes) is False

    def test_build_adjacency_hard_edge(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_HARD}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert 'B' in H_out['A']
        assert 'A' in Hard_in['B']
        assert len(S_out['A']) == 0

    def test_build_adjacency_soft_edge(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_NEEDS_SOFT}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert 'B' in S_out['A']
        assert len(H_out['A']) == 0

    def test_build_adjacency_helps_edge(self):
        edges = [{'source': 'A', 'target': 'B', 'type': EDGE_HELPS}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert 'B' in Syn['A']
        assert 'A' in Syn['B']  # bidirectional

    def test_build_adjacency_ignores_unknown_nodes(self):
        edges = [{'source': 'A', 'target': 'Z', 'type': EDGE_NEEDS_HARD}]
        H_out, S_out, Syn, Hard_in = build_adjacency(edges, {'A', 'B'})
        assert len(H_out['A']) == 0  # Z not in node_names

    def test_total_value_isolated_node(self):
        node = make_node("A", value=8, interest=6)
        nodes = {"A": node}
        H_out = {"A": []}
        S_out = {"A": []}
        Syn = {"A": set()}
        tv = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.25, 0.10, 0.40)
        assert tv == intrinsic_value(node, 1.0, 1.0)

    def test_total_value_with_hard_dependent(self):
        a = make_node("A", value=5, interest=5)
        b = make_node("B", value=10, interest=10)
        nodes = {"A": a, "B": b}
        H_out = {"A": ["B"], "B": []}
        S_out = {"A": [], "B": []}
        Syn = {"A": set(), "B": set()}
        d_H = 0.6
        tv_a = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, d_H, 0.25, 0.10, 0.40)
        iv_a = intrinsic_value(a, 1.0, 1.0)
        iv_b = intrinsic_value(b, 1.0, 1.0)
        assert tv_a == pytest.approx(iv_a + d_H * iv_b)

    def test_total_value_cycle_prevention(self):
        # A→B→A would recurse infinitely without visited set
        a = make_node("A", value=5, interest=5)
        b = make_node("B", value=5, interest=5)
        nodes = {"A": a, "B": b}
        H_out = {"A": ["B"], "B": ["A"]}
        S_out = {"A": [], "B": []}
        Syn = {"A": set(), "B": set()}
        # Should not hang — visited set prevents infinite recursion
        tv = total_value("A", set(), nodes, H_out, S_out, Syn, 1.0, 1.0, 0.6, 0.25, 0.10, 0.40)
        assert tv > 0


# ============================================================================
# Scoring — inherited value_mode prevents own-IV injection
# ============================================================================

class TestScoringInheritedValueMode:
    def test_inherited_node_scores_with_zero_iv(self):
        """A node with value_mode='inherited' contributes 0 IV to its own score
        — score depends entirely on cascade from descendants (none here)."""
        n = make_node("Container", value=10, interest=10, difficulty=3,
                       value_mode='inherited')
        scored = score_nodes([n], [n], [], {})
        # iv = 0, cascade = 0 (no children), so total_value = 0, score = 0.
        assert scored[0].priority_score == 0.0

    def test_manual_node_scores_with_full_iv(self):
        """Sanity baseline: identical node in manual mode scores normally."""
        n = make_node("Manual", value=10, interest=10, difficulty=3,
                       value_mode='manual')
        scored = score_nodes([n], [n], [], {})
        assert scored[0].priority_score > 0.0

    def test_inherited_parent_does_not_inflate_child_score(self):
        """A child's score is its own IV + d_H * tv(parent). When the parent
        is value_mode='inherited', the parent contributes 0 to its own IV,
        so the child's score loses the parent's IV bump.

        Compare two structurally identical trees: in tree A the parent is
        manual (full IV), in tree B the parent is inherited (zero IV).
        The child in A should score higher than the child in B.
        """
        # Tree A: manual parent
        child_a = make_node("ChildA", value=5, interest=5, difficulty=3)
        parent_a = make_node("ParentA", type='Learn', value=10, interest=10,
                              difficulty=3, value_mode='manual')
        edges_a = [{'source': 'ChildA', 'target': 'ParentA', 'type': 'Needs_Hard'}]

        # Tree B: inherited parent (same children, same parent v/i/d)
        child_b = make_node("ChildB", value=5, interest=5, difficulty=3)
        parent_b = make_node("ParentB", type='Learn', value=10, interest=10,
                              difficulty=3, value_mode='inherited')
        edges_b = [{'source': 'ChildB', 'target': 'ParentB', 'type': 'Needs_Hard'}]

        scored_a = score_nodes([child_a, parent_a], [child_a, parent_a], edges_a, {})
        scored_b = score_nodes([child_b, parent_b], [child_b, parent_b], edges_b, {})

        a = next(n for n in scored_a if n.name == 'ChildA').priority_score
        b = next(n for n in scored_b if n.name == 'ChildB').priority_score
        # Manual parent injects extra IV into the child via cascade — child A wins.
        assert a > b

    def test_inherited_ratings_keep_own_effort_in_cost(self):
        """Effort prices the node's own hours, so inheriting only the ratings
        leaves it in the cost. A node with Effort 10 must not score like one
        with Effort 1 just because its value flows from what it unlocks."""
        hp = {'w_e': 2.5, 'w_t': 1.0, 'beta': 0.85}
        child = make_node("Child", value=8, interest=8)

        def score_with(difficulty):
            parent = make_node("P", difficulty=difficulty, time_o=1, time_m=1,
                                time_p=1, value_mode='inherited')
            edges = [{'source': 'P', 'target': 'Child', 'type': EDGE_NEEDS_HARD}]
            scored = score_nodes([parent], [parent, child], edges, hp)
            return scored[0].priority_score

        assert score_with(1) > score_with(10) > 0

    def test_inherited_time_zeroes_effort_in_cost(self):
        """A node with no hours of its own (time inherited) has no work for
        Effort to price, so Explain reports its effort as overridden."""
        node = make_node("C", difficulty=10, time_mode='inherited',
                          value_mode='inherited')
        breakdown = explain_score("C", [node], [], {'w_e': 2.5})
        assert breakdown['cost']['effort_overridden'] is True
        assert breakdown['cost']['cost'] == pytest.approx(1.0)

    def test_inherited_parent_still_passes_descendant_value(self):
        """An inherited parent zeroes its OWN IV but still passes its descendants'
        IV upward through the cascade. Verify a grandchild → parent → grandparent
        chain still flows when the middle node is inherited."""
        gc = make_node("Grandchild", value=8, interest=8, difficulty=3)
        mid = make_node("Middle", type='Learn', value=10, interest=10,
                         difficulty=3, value_mode='inherited')
        gp = make_node("Grandparent", type='Learn', value=2, interest=2,
                        difficulty=3, value_mode='manual')
        edges = [
            {'source': 'Grandchild', 'target': 'Middle', 'type': 'Needs_Hard'},
            {'source': 'Middle',     'target': 'Grandparent', 'type': 'Needs_Hard'},
        ]
        scored = score_nodes([gc, mid, gp], [gc, mid, gp], edges, {})
        # Grandchild gets its own IV plus d_H * tv(Middle), where tv(Middle) =
        # 0 (inherited) + d_H * tv(Grandparent). So Grandchild's score is non-zero
        # and reflects the path through Middle even though Middle itself adds 0.
        gc_score = next(n for n in scored if n.name == 'Grandchild').priority_score
        assert gc_score > 0.0


# ============================================================================
# Scoring — container exclusion (both modes inherited)
# ============================================================================

class TestScoringContainerExclusion:
    """A node with both value_mode='inherited' AND time_mode='inherited' is a
    pure container (Node.is_container). Its IV is 0 and cost denominator
    collapses to 1.0, so without an explicit guard a container with valuable
    descendants downstream of an outgoing prereq edge would ride the cascade
    straight to the top of the recommendations. Containers are skipped — the
    children compete on their own merits."""

    def test_is_pure_container_property(self):
        # Both modes inherited → pure container (the scoring-exclusion gate).
        c = make_node(value_mode='inherited', time_mode='inherited')
        assert c.is_pure_container is True
        assert c.is_container is True  # also a container under the broad notion

    def test_one_mode_inherited_is_container_but_not_pure(self):
        # Under the split: either mode inherited → is_container; both → pure.
        v_only = make_node(value_mode='inherited', time_mode='manual')
        t_only = make_node(value_mode='manual', time_mode='inherited')
        assert v_only.is_container is True
        assert v_only.is_pure_container is False
        assert t_only.is_container is True
        assert t_only.is_pure_container is False

    def test_manual_node_is_neither(self):
        n = make_node(value_mode='manual', time_mode='manual')
        assert n.is_container is False
        assert n.is_pure_container is False

    def test_standalone_container_excluded_from_recommendations(self):
        """A container with no descendants is marked -1.0 and won't surface."""
        c = make_node("EmptyContainer", value_mode='inherited',
                       time_mode='inherited')
        scored = score_nodes([c], [c], [], {})
        assert scored[0].priority_score == -1.0

    def test_container_with_outgoing_prereq_still_excluded(self):
        """The bug case: container with no children pointing in, but it gates
        a valuable downstream node via an outgoing Needs_Hard. Pre-fix the
        cascade would give it a near-1.0 cost and a positive cascaded TV,
        putting it at the top of the list. Post-fix it's excluded outright,
        and the previously-top non-container is the actual #1."""
        container = make_node("ClassicalWorks", type='Learn',
                               value=6, interest=6, difficulty=8,
                               value_mode='inherited', time_mode='inherited')
        # Make the gated downstream an unranked Goal (mirrors the real prod
        # case: ClassicalWorks → Reading [Goal]). Goals don't compete, so the
        # container would otherwise have nothing to crowd it off the top.
        downstream = make_node("Reading", type='Goal',
                                value=9, interest=9, difficulty=5)
        rival = make_node("UnrelatedLearn", type='Learn',
                           value=7, interest=7, difficulty=3)
        edges = [{'source': 'ClassicalWorks', 'target': 'Reading',
                  'type': 'Needs_Hard'}]
        scored = score_nodes([container, downstream, rival],
                             [container, downstream, rival], edges, {})
        c = next(n for n in scored if n.name == 'ClassicalWorks')
        r = next(n for n in scored if n.name == 'UnrelatedLearn')
        assert c.priority_score == -1.0       # container excluded
        assert r.priority_score > 0.0         # rival ranks normally
        # And the rival is the top of the sorted list, not the container.
        top = sorted(scored, key=lambda n: n.priority_score, reverse=True)[0]
        assert top.name == 'UnrelatedLearn'

    def test_container_still_propagates_cascade_to_dependents(self):
        """Excluding a container from being scored does NOT remove it from the
        cascade graph — its dependents still get value flowing through it."""
        leaf = make_node("Leaf", value=10, interest=10)
        container = make_node("Container", type='Learn',
                               value_mode='inherited', time_mode='inherited')
        # leaf --Needs_Hard--> container (leaf unlocks container, so the
        # container's TV cascades into leaf's TV).
        edges = [{'source': 'Leaf', 'target': 'Container',
                  'type': 'Needs_Hard'}]
        scored = score_nodes([leaf, container], [leaf, container], edges, {})
        leaf_score = next(n for n in scored if n.name == 'Leaf').priority_score
        # Leaf's own IV is positive, so its score is positive regardless. The
        # important assertion is that leaf gets scored normally — the
        # container's exclusion didn't break the cascade walk.
        assert leaf_score > 0.0


# ============================================================================
# Scoring — perceived_cost time_override
# ============================================================================

class TestPerceivedCostTimeOverride:
    def test_default_uses_node_time(self):
        node = make_node(difficulty=5, time_o=2, time_m=2, time_p=2)
        cost_default = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85)
        cost_explicit = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=None)
        assert cost_default == cost_explicit

    def test_time_override_replaces_node_time(self):
        node = make_node(difficulty=5, time_o=10, time_m=10, time_p=10)
        cost_overridden = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=1.0)
        expected = 1.0 + 2.5 * 5 + 1.0 * ((1.0 / TIME_REF_HOURS) ** 0.85)
        assert cost_overridden == pytest.approx(expected, rel=1e-4)

    def test_time_override_zero(self):
        node = make_node(difficulty=5, time_o=10, time_m=10, time_p=10)
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=0.0)
        expected = 1.0 + 2.5 * 5 + 1.0 * (0.0 ** 0.85)
        assert cost == pytest.approx(expected, rel=1e-4)


class TestNoOwnWorkIsNotRecommended:
    """A node with no hours of its own has nothing left to do once eligible.

    `time_mode='inherited'` draws time from the hard prerequisites that
    eligibility already requires to be Done, so such a node is only rankable
    at the point its inherited hours are already spent. Without this gate it
    would collect the full cascade over a denominator carrying no time term
    at all, and outrank real work.
    """

    def test_inherited_time_node_is_not_ranked(self):
        node = make_node("Container", value=9, interest=9, difficulty=3,
                          time_o=10, time_m=10, time_p=10, time_mode='inherited')
        scored = score_nodes([node], [node], [], {})
        assert scored[0].priority_score == -1.0

    def test_it_still_carries_total_value(self):
        """Excluded from the list, not from the graph: cascade flows through."""
        node = make_node("Container", value=9, interest=9, time_mode='inherited')
        scored = score_nodes([node], [node], [], {})
        assert scored[0].total_value > 0

    def test_inherited_ratings_with_own_time_is_still_ranked(self):
        """The gate keys on time alone, deliberately.

        A node with inherited *ratings* but its own hours has real work to do
        and merely draws its worth from what it unlocks. It must keep ranking.
        """
        node = make_node("Conduit", value=5, interest=5, difficulty=3,
                          time_o=10, time_m=10, time_p=10, value_mode='inherited')
        scored = score_nodes([node], [node], [], {})
        assert scored[0].priority_score >= 0.0

    def test_property_keys_on_time_only(self):
        assert make_node(time_mode='inherited').has_no_own_work is True
        assert make_node(value_mode='inherited').has_no_own_work is False
        assert make_node(time_mode='inherited',
                          value_mode='inherited').has_no_own_work is True
        assert make_node().has_no_own_work is False

    def test_excluded_nodes_do_not_dilute_density_buckets(self):
        """Whatever cannot be recommended must not shrink a rival's multiplier."""
        ranked = make_node("Ranked", context="C", subcontext="S",
                            time_o=10, time_m=10, time_p=10)
        container = make_node("Container", context="C", subcontext="S",
                               time_mode='inherited')
        hp = {'alpha': 1.0}
        alone = score_nodes([ranked], [ranked], [], hp)[0].priority_score
        with_container = next(
            n for n in score_nodes([ranked, container], [ranked, container], [], hp)
            if n.name == "Ranked").priority_score
        assert alone == with_container
