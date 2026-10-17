"""Ranking through the GraphManager: goal boosts, Milestones, inherited modes."""
import pytest
from skilltree.store import database
from skilltree.domain.models import EDGE_NEEDS_HARD
from skilltree.domain.profiles import DEFAULT_HYPERPARAMS
from skilltree.domain.scoring import (intrinsic_value, perceived_cost, score_nodes)
from support.graphs import make_node


# ============================================================================
# Priority Scoring (integration via GraphManager)
# ============================================================================

class TestPriorityScoring:
    def test_done_nodes_get_negative_score(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        assert scored[0].priority_score == -1.0

    def test_blocked_nodes_get_negative_score(self, mgr):
        mgr.add_node(make_node("A", status="Blocked"))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        assert scored[0].priority_score == -1.0

    def test_open_node_gets_positive_score(self, mgr):
        mgr.add_node(make_node("A", status="Open", value=8, interest=7))
        scored = mgr.calculate_priority_scores([mgr.get_node("A")])
        assert scored[0].priority_score > 0

    def test_higher_value_scores_higher(self, mgr):
        mgr.add_node(make_node("Low", value=1, interest=1, difficulty=5))
        mgr.add_node(make_node("High", value=10, interest=10, difficulty=5))
        scored = mgr.calculate_priority_scores([mgr.get_node("Low"), mgr.get_node("High")])
        high_score = next(n for n in scored if n.name == "High").priority_score
        low_score = next(n for n in scored if n.name == "Low").priority_score
        assert high_score > low_score

    def test_higher_difficulty_scores_lower(self, mgr):
        mgr.add_node(make_node("Easy", value=5, interest=5, difficulty=1))
        mgr.add_node(make_node("Hard", value=5, interest=5, difficulty=10))
        scored = mgr.calculate_priority_scores([mgr.get_node("Easy"), mgr.get_node("Hard")])
        easy_score = next(n for n in scored if n.name == "Easy").priority_score
        hard_score = next(n for n in scored if n.name == "Hard").priority_score
        assert easy_score > hard_score

    def test_ineligible_hard_prereq_scores_negative(self, mgr):
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        # Target is now Blocked by state management, but even if we force-pass it,
        # it would be ineligible
        scored = mgr.calculate_priority_scores([mgr.get_node("Target")])
        assert scored[0].priority_score == -1.0

    def test_network_value_propagation(self, mgr):
        # Node that unlocks a high-value downstream should score higher
        mgr.add_node(make_node("Gateway", status="Open", value=1, interest=1))
        mgr.add_node(make_node("Treasure", status="Open", value=10, interest=10))
        mgr.add_node(make_node("Isolated", status="Open", value=1, interest=1))
        mgr.add_edge("Gateway", "Treasure", EDGE_NEEDS_HARD)
        scored = mgr.calculate_priority_scores([mgr.get_node("Gateway"), mgr.get_node("Isolated")])
        gateway_score = next(n for n in scored if n.name == "Gateway").priority_score
        isolated_score = next(n for n in scored if n.name == "Isolated").priority_score
        assert gateway_score > isolated_score

    def test_scores_sorted_descending(self, mgr):
        for i, name in enumerate(["A", "B", "C"]):
            mgr.add_node(make_node(name, value=i + 1, interest=i + 1))
        all_nodes = mgr.get_all_nodes()
        scored = mgr.calculate_priority_scores(all_nodes)
        scores = [n.priority_score for n in scored]
        assert scores == sorted(scores, reverse=True)


# ============================================================================
# Scoring — Goal Boost & Type Exclusions
# ============================================================================

class TestScoringGoalBoost:

    def test_goal_nodes_get_negative_score(self, mgr):
        mgr.add_node(make_node("G", type="Goal"))
        scored = mgr.calculate_priority_scores([mgr.get_node("G")])
        assert scored[0].priority_score == -1.0

    def test_goal_boost_applied(self, mgr):
        # Gateway is a hard prereq of GoalNode → Gateway should be boosted
        mgr.add_node(make_node("Gateway", value=5, interest=5))
        mgr.add_node(make_node("Unrelated", value=5, interest=5))
        mgr.add_node(make_node("GoalNode", type="Goal"))
        mgr.add_edge("Gateway", "GoalNode", EDGE_NEEDS_HARD)

        scored_without = mgr.calculate_priority_scores(
            [mgr.get_node("Gateway"), mgr.get_node("Unrelated")]
        )
        gw_base = next(n for n in scored_without if n.name == "Gateway").priority_score
        un_base = next(n for n in scored_without if n.name == "Unrelated").priority_score
        # Without goals, Gateway and Unrelated should score similarly
        # (Gateway has a slight edge due to network value from GoalNode)

        scored_with = mgr.calculate_priority_scores(
            [mgr.get_node("Gateway"), mgr.get_node("Unrelated")],
            priority_goals=["GoalNode"]
        )
        gw_boosted = next(n for n in scored_with if n.name == "Gateway").priority_score
        un_boosted = next(n for n in scored_with if n.name == "Unrelated").priority_score

        assert gw_boosted > gw_base  # Gateway got boosted
        assert un_boosted == un_base  # Unrelated unchanged

    def test_ranked_goals_decreasing_boost(self, mgr):
        # Three goals, each with one prereq
        for i, name in enumerate(["P1", "P2", "P3"]):
            mgr.add_node(make_node(name, value=5, interest=5))
        for i, name in enumerate(["G1", "G2", "G3"]):
            mgr.add_node(make_node(name, type="Goal"))
            mgr.add_edge(f"P{i+1}", name, EDGE_NEEDS_HARD)

        scored = mgr.calculate_priority_scores(
            [mgr.get_node("P1"), mgr.get_node("P2"), mgr.get_node("P3")],
            priority_goals=["G1", "G2", "G3"]
        )
        p1 = next(n for n in scored if n.name == "P1").priority_score
        p2 = next(n for n in scored if n.name == "P2").priority_score
        p3 = next(n for n in scored if n.name == "P3").priority_score

        # Rank 1 gets full boost, rank 2 gets 66%, rank 3 gets 33%
        assert p1 >= p2 >= p3


# ============================================================================
# Scoring — Milestone exclusion
# ============================================================================

class TestScoringMilestoneSkip:
    """Milestone nodes are non-competing containers (like Goals): they should
    receive priority_score=-1.0 and be excluded from per-bucket density counts.
    """

    def test_milestone_nodes_get_negative_score(self, mgr):
        mgr.add_node(make_node("M", type="Milestone", value=10, interest=10))
        scored = mgr.calculate_priority_scores([mgr.get_node("M")])
        assert scored[0].priority_score == -1.0

    def test_unrelated_inventory_does_not_change_merit(self, mgr):
        # Neither unrelated milestones nor learn nodes dilute task merit.
        hypers = {**DEFAULT_HYPERPARAMS, 'alpha': 1.0}
        mgr.add_node(make_node("L1", type="Learn", context="Mind", subcontext="Rational"))
        mgr.add_node(make_node("L2", type="Learn", context="Mind", subcontext="Rational"))
        mgr.add_node(make_node("MS", type="Milestone", context="Mind", subcontext="Rational"))
        active = [mgr.get_node("L1"), mgr.get_node("L2"), mgr.get_node("MS")]
        scored_with_ms = score_nodes(active, active, mgr.get_edges(), hypers)

        mgr.add_node(make_node("L3", type="Learn", context="Mind", subcontext="Rational"))
        active2 = [mgr.get_node(n) for n in ("L1", "L2", "L3", "MS")]
        scored_with_l3 = score_nodes(active2, active2, mgr.get_edges(), hypers)

        l1_with_ms = next(n for n in scored_with_ms if n.name == "L1").priority_score
        l1_with_l3 = next(n for n in scored_with_l3 if n.name == "L1").priority_score
        assert l1_with_l3 == l1_with_ms


# ============================================================================
# Milestone value-transparency invariant
# ============================================================================

class TestMilestoneValueTransparency:
    """Milestones are transparent checkpoints: their own value/interest/effort
    must never enter scoring. The invariant is enforced at the model layer
    (Node.__post_init__ forces value_mode='inherited' for Milestones) so it
    holds on every read path — primary Next-tab ranking included, not just
    Goal ranking. Goals are exempt: they legitimately carry their own value.
    """

    def test_milestone_forced_to_inherited_on_construction(self):
        """A Milestone constructed with value_mode='manual' is corrected."""
        n = make_node("MS", type="Milestone", value_mode='manual',
                       value=10, interest=10)
        assert n.value_mode == 'inherited'

    def test_milestone_inherited_even_with_default_value_mode(self):
        n = make_node("MS", type="Milestone")  # no value_mode passed
        assert n.value_mode == 'inherited'

    def test_milestone_intrinsic_value_is_zero(self):
        """High ratings on a Milestone contribute 0 IV — the leak this fixes."""
        n = make_node("MS", type="Milestone", value=10, interest=10)
        assert intrinsic_value(n, w_v=1.0, w_i=1.0) == 0.0

    def test_milestone_ratings_preserved_for_roundtrip(self):
        """v/i/d are preserved (not destroyed) even though value_mode is forced,
        mirroring the time_mode precedent — a type change restores them."""
        n = make_node("MS", type="Milestone", value=9, interest=7, difficulty=4)
        assert n.value == 9 and n.interest == 7 and n.difficulty == 4

    def test_goal_not_forced_to_inherited(self):
        """Goals carry their own value (docs/modeling.md) — NOT forced."""
        g = make_node("G", type="Goal", value_mode='manual', value=8, interest=6)
        assert g.value_mode == 'manual'
        assert intrinsic_value(g, w_v=1.0, w_i=1.0) == 14.0

    def test_milestone_db_roundtrip_is_inherited(self, mgr):
        mgr.add_node(make_node("MS", type="Milestone", value=10, interest=10))
        fetched = mgr.get_node("MS")
        assert fetched.value_mode == 'inherited'
        assert intrinsic_value(fetched, 1.0, 1.0) == 0.0

    def test_milestone_does_not_leak_value_into_unlocking_node(self):
        """The core bug: a Learn that hard-unlocks a high-rated Milestone must
        score the SAME as if the Milestone carried no ratings — the Milestone's
        own value must not cascade back into the work that leads to it.

        Compare the unlocking Learn's score against a baseline where the
        downstream node is an explicit zero-IV container. They must match.
        """
        # Graph A: Learn → Milestone (Milestone has high placeholder ratings).
        learn_a = make_node("LearnA", type="Learn", value=5, interest=5,
                             difficulty=3, context="Body", subcontext="Exercise")
        ms = make_node("MS", type="Milestone", value=10, interest=10,
                        context="Body", subcontext="Exercise")
        edges_a = [{'source': 'LearnA', 'target': 'MS', 'type': EDGE_NEEDS_HARD}]
        scored_a = score_nodes([learn_a], [learn_a, ms], edges_a, DEFAULT_HYPERPARAMS)
        learn_a_score = scored_a[0].priority_score

        # Graph B: Learn → explicit pure container (IV genuinely 0).
        learn_b = make_node("LearnB", type="Learn", value=5, interest=5,
                             difficulty=3, context="Body", subcontext="Exercise")
        cont = make_node("Cont", type="Learn", value=10, interest=10,
                          value_mode='inherited', time_mode='inherited',
                          context="Body", subcontext="Exercise")
        edges_b = [{'source': 'LearnB', 'target': 'Cont', 'type': EDGE_NEEDS_HARD}]
        scored_b = score_nodes([learn_b], [learn_b, cont], edges_b, DEFAULT_HYPERPARAMS)
        learn_b_score = scored_b[0].priority_score

        assert learn_a_score == pytest.approx(learn_b_score)

    def test_legacy_milestone_row_corrected_on_read(self, mgr):
        """A legacy Milestone row stored with value_mode='manual' and a real
        time estimate (written via raw SQL to bypass the model guard, simulating
        a row that predates this rule) reads back as a pure container: both
        modes inherited, zero IV, zero time. There is no DB migration —
        Node.__post_init__ enforces the invariant on every construction, so the
        correction happens transparently when GraphManager loads the row."""
        import sqlite3
        conn = sqlite3.connect(database.get_db_path())
        conn.execute(
            "INSERT INTO Nodes (name, type, description, value, time_o, time_m, "
            "time_p, interest, difficulty, status, context, value_mode, time_mode) "
            "VALUES (?, 'Milestone', '', 10, 5, 10, 20, 10, 5, 'Open', 'Body', "
            "'manual', 'manual')",
            ("LegacyMS",),
        )
        conn.commit()
        conn.close()

        node = mgr.get_node("LegacyMS")
        assert node.value_mode == 'inherited'
        assert node.time_mode == 'inherited'
        assert intrinsic_value(node, 1.0, 1.0) == 0.0
        assert node.time == 0.0

    def test_milestone_value_leak_would_inflate_without_fix(self):
        """Guard test: confirm the scenario is non-trivial — if the Milestone
        DID carry its ratings (the old bug), the unlocking Learn would score
        strictly higher. We simulate the buggy case with a manual-value Learn
        as the downstream node and confirm it scores higher than our Milestone
        case, proving the transparency is actually doing work."""
        learn = make_node("Learn", type="Learn", value=5, interest=5,
                           difficulty=3, context="Body", subcontext="Exercise")
        ms = make_node("MS", type="Milestone", value=10, interest=10,
                        context="Body", subcontext="Exercise")
        edges = [{'source': 'Learn', 'target': 'MS', 'type': EDGE_NEEDS_HARD}]
        ms_case = score_nodes([learn], [learn, ms], edges, DEFAULT_HYPERPARAMS)[0].priority_score

        learn2 = make_node("Learn2", type="Learn", value=5, interest=5,
                            difficulty=3, context="Body", subcontext="Exercise")
        downstream = make_node("Down", type="Learn", value=10, interest=10,
                                context="Body", subcontext="Exercise")
        edges2 = [{'source': 'Learn2', 'target': 'Down', 'type': EDGE_NEEDS_HARD}]
        learn_case = score_nodes([learn2], [learn2, downstream], edges2,
                                 DEFAULT_HYPERPARAMS)[0].priority_score

        assert learn_case > ms_case


# ============================================================================
# Scoring — inherited time_mode prevents double-counting
# ============================================================================

class TestScoringInheritedTimeMode:
    def test_inherited_node_uses_zero_time_in_cost(self):
        """time=0 substitution avoids double-counting a container's children.

        The substitution itself is still the contract — only whether such a
        node gets *recommended* changed (see TestNoOwnWorkIsNotRecommended).
        """
        manual = make_node("Manual", value=5, interest=5, difficulty=5,
                            time_o=10, time_m=10, time_p=10, time_mode='manual')
        inherited = make_node("Inherited", value=5, interest=5, difficulty=5,
                               time_o=10, time_m=10, time_p=10, time_mode='inherited')
        c_manual = perceived_cost(manual, w_e=2.5, w_t=1.0, beta=0.85)
        c_inherited = perceived_cost(inherited, w_e=2.5, w_t=1.0, beta=0.85,
                                     time_override=0.0)
        assert c_inherited < c_manual
        assert c_inherited == pytest.approx(1.0 + 2.5 * 5)

    def test_manual_node_still_uses_full_time(self, mgr):
        """A manual-mode node should use its full expected time in cost calculation."""
        node = make_node("Full", value=5, interest=5, time_o=10, time_m=10, time_p=10,
                          time_mode='manual')
        scored = score_nodes([node], [node], [], {})
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85)
        iv = intrinsic_value(node, 1.0, 1.0)
        expected_score = round(iv / cost, 2)
        assert scored[0].priority_score == expected_score

    def test_inherited_cost_arithmetic(self):
        """Pin the exact cost formula for inherited nodes: 1 + w_e*difficulty + 0.

        Locks in the contract that the time term contributes nothing for
        containers — protects against an accidental revert to a non-zero override.
        """
        node = make_node("C", value=5, interest=5, difficulty=4,
                          time_o=10, time_m=10, time_p=10, time_mode='inherited')
        cost = perceived_cost(node, w_e=2.5, w_t=1.0, beta=0.85, time_override=0.0)
        assert cost == pytest.approx(1.0 + 2.5 * 4)

    def test_chained_inherited_nodes_no_phantom_cost(self, mgr):
        """A chain of inherited nodes shouldn't accumulate phantom 1.0 costs.

        With the old t_override=1.0, each inherited node added a phantom unit
        to its denominator. With t_override=0.0, the cost is purely from the
        base + difficulty contribution, so identical-difficulty chains have
        identical per-node costs.
        """
        a = make_node("A", value=5, interest=5, difficulty=3, time_mode='inherited')
        b = make_node("B", value=5, interest=5, difficulty=3, time_mode='inherited')
        c = make_node("C", value=5, interest=5, difficulty=3, time_mode='inherited')
        # Compare costs directly: these nodes are no longer ranked, so equal
        # priority_scores would only prove they share the same -1.0 sentinel.
        costs = [perceived_cost(n, w_e=2.5, w_t=1.0, beta=0.85, time_override=0.0)
                 for n in (a, b, c)]
        assert costs[0] == costs[1] == costs[2] == pytest.approx(1.0 + 2.5 * 3)
