"""Status: the Blocked cascade, Goal completion and the auto-Done queue."""
import pytest
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_DONE, STATUS_OPEN, STATUS_BLOCKED
from support.graphs import make_node


# ============================================================================
# State Management
# ============================================================================

class TestStateManagement:
    def test_node_blocked_when_hard_prereq_not_done(self, mgr):
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        assert mgr.get_node("Target").status == "Blocked"

    def test_node_unblocked_when_hard_prereq_done(self, mgr):
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        mgr.update_node(make_node("Prereq", status="Done"))
        assert mgr.get_node("Target").status == "Open"

    def test_soft_prereq_does_not_block(self, mgr):
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("Target", status="Open"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_SOFT)
        assert mgr.get_node("Target").status == "Open"

    def test_done_node_reblocks_when_prereq_un_dones(self, mgr):
        """Un-Done-ing a prereq cascades downstream: a Done dependent flips
        to Blocked because its hard prereq is no longer satisfied. This is
        the post-Group-3 non-sticky-Done semantics — the UI guards this with
        a confirmation modal so the user is aware before triggering."""
        mgr.add_node(make_node("Prereq", status="Done"))
        mgr.add_node(make_node("Target", status="Done"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        # Change prereq back to Open — Target should re-Block
        mgr.update_node(make_node("Prereq", status="Open"))
        assert mgr.get_node("Target").status == "Blocked"

    def test_cascade_unblock(self, mgr):
        mgr.add_node(make_node("A", status="Open"))
        mgr.add_node(make_node("B", status="Open"))
        mgr.add_node(make_node("C", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"
        # Complete A — B should unblock, then C should unblock (B is now Open, not Done)
        mgr.update_node(make_node("A", status="Done"))
        assert mgr.get_node("B").status == "Open"
        # C still Blocked because B is Open, not Done
        assert mgr.get_node("C").status == "Blocked"
        # Complete B — C should unblock
        mgr.update_node(make_node("B", status="Done"))
        assert mgr.get_node("C").status == "Open"

    def test_multiple_hard_prereqs_all_must_be_done(self, mgr):
        mgr.add_node(make_node("P1", status="Open"))
        mgr.add_node(make_node("P2", status="Open"))
        mgr.add_node(make_node("Target", status="Open"))
        mgr.add_edge("P1", "Target", EDGE_NEEDS_HARD)
        mgr.add_edge("P2", "Target", EDGE_NEEDS_HARD)
        assert mgr.get_node("Target").status == "Blocked"
        mgr.update_node(make_node("P1", status="Done"))
        assert mgr.get_node("Target").status == "Blocked"  # P2 still Open
        mgr.update_node(make_node("P2", status="Done"))
        assert mgr.get_node("Target").status == "Open"

    def test_sync_edges_blocks_chain_via_needs(self, mgr):
        """Creating a chain A→B→C via sync_edges should block B and C immediately."""
        mgr.add_node(make_node("Chain1"))
        mgr.add_node(make_node("Chain2"))
        mgr.add_node(make_node("Chain3"))
        # Chain2 needs Chain1
        mgr.sync_edges("Chain2", needs_hard=["Chain1"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("Chain2").status == "Blocked"
        # Chain3 needs Chain2
        mgr.sync_edges("Chain3", needs_hard=["Chain2"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("Chain3").status == "Blocked"

    def test_sync_edges_blocks_via_supports(self, mgr):
        """When node A declares supports_hard=[B, C], B and C should become Blocked."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B", "C"], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"

    def test_sync_edges_supports_unblocks_when_done(self, mgr):
        """After A supports B and A is marked Done, B should become Open."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        mgr.update_node(make_node("A", status="Done"))
        assert mgr.get_node("B").status == "Open"

    def test_sync_edges_chain_via_supports_cascades(self, mgr):
        """Building a chain entirely through supports: A supports B, B supports C.
        When saving B, existing needs_hard from A must be preserved in the call."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.sync_edges("A", needs_hard=[], needs_soft=[], supports_hard=["B"], supports_soft=[], helps=[])
        # B also supports C; preserve the existing A→B prereq in needs_hard
        mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=["C"], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"
        # Complete A — B unblocks, C stays blocked
        mgr.update_node(make_node("A", status="Done"))
        assert mgr.get_node("B").status == "Open"
        assert mgr.get_node("C").status == "Blocked"

    def test_delete_node_unblocks_dependents(self, mgr):
        """Deleting a hard prereq should unblock its dependents."""
        mgr.add_node(make_node("Prereq"))
        mgr.add_node(make_node("Target"))
        mgr.add_edge("Prereq", "Target", EDGE_NEEDS_HARD)
        assert mgr.get_node("Target").status == "Blocked"
        mgr.delete_node("Prereq")
        assert mgr.get_node("Target").status == "Open"

    def test_sync_edges_can_remove_dormant_needs_edges(self, mgr):
        """Dormant relationships are visible, so sync is a complete replacement."""
        mgr.add_node(make_node("Target"))
        mgr.add_node(make_node("ActivePrereq"))
        mgr.add_node(make_node("DormantPrereq", dormant=1))
        mgr.add_edge("ActivePrereq", "Target", EDGE_NEEDS_HARD)
        mgr.add_edge("DormantPrereq", "Target", EDGE_NEEDS_HARD)
        mgr.sync_edges("Target", needs_hard=["ActivePrereq"], needs_soft=[],
                       supports_hard=[], supports_soft=[], helps=[])
        edges = mgr.get_edges()
        incoming = {e['source'] for e in edges
                    if e['target'] == 'Target' and e['type'] == EDGE_NEEDS_HARD}
        assert incoming == {"ActivePrereq"}

    def test_sync_edges_can_remove_dormant_helps_edges(self, mgr):
        """Omitting a visible dormant synergy removes it from either orientation."""
        mgr.add_node(make_node("Target"))
        mgr.add_node(make_node("ActiveHelper"))
        mgr.add_node(make_node("DormantHelper", dormant=1))
        mgr.add_edge("Target", "ActiveHelper", EDGE_HELPS)
        mgr.add_edge("Target", "DormantHelper", EDGE_HELPS)
        mgr.sync_edges("Target", needs_hard=[], needs_soft=[],
                       supports_hard=[], supports_soft=[], helps=["ActiveHelper"])
        edges = mgr.get_edges()
        helps_partners = {e['target'] for e in edges
                          if e['source'] == 'Target' and e['type'] == EDGE_HELPS}
        helps_partners |= {e['source'] for e in edges
                           if e['target'] == 'Target' and e['type'] == EDGE_HELPS}
        assert helps_partners == {"ActiveHelper"}

    def test_delete_node_cascades_unblock(self, mgr):
        """Deleting the root of a chain should cascade unblocking through dependents."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.get_node("C").status == "Blocked"
        # Delete A — B loses its only prereq → Open, C still blocked by B (not Done)
        mgr.delete_node("A")
        assert mgr.get_node("B").status == "Open"
        assert mgr.get_node("C").status == "Blocked"

    def test_removing_edge_via_sync_unblocks(self, mgr):
        """Removing a hard prereq via sync_edges should unblock the node."""
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.sync_edges("B", needs_hard=["A"], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Blocked"
        # Remove the prereq
        mgr.sync_edges("B", needs_hard=[], needs_soft=[], supports_hard=[], supports_soft=[], helps=[])
        assert mgr.get_node("B").status == "Open"

    def test_recompute_all_statuses_repairs_drift(self, mgr):
        """Raw-SQL edge insertion bypasses the cascade, leaving the target stuck
        at Open. recompute_all_statuses must repair it."""
        mgr.add_node(make_node("A", status="Open"))
        mgr.add_node(make_node("B", status="Open"))
        with mgr.get_connection() as conn:
            conn.execute(
                "INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                ("A", "B", EDGE_NEEDS_HARD),
            )
            conn.commit()
        assert mgr.get_node("B").status == "Open"
        changed = mgr.recompute_all_statuses()
        assert changed == 1
        assert mgr.get_node("B").status == "Blocked"

    def test_recompute_all_statuses_noop_when_consistent(self, mgr):
        """On a clean graph where statuses already match the cascade, recompute
        should report zero changes."""
        mgr.add_node(make_node("A", status="Open"))
        mgr.add_node(make_node("B", status="Open"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        assert mgr.get_node("B").status == "Blocked"
        assert mgr.recompute_all_statuses() == 0

    def test_recompute_all_statuses_skips_goals_and_repairs_done(self, mgr):
        """Goals keep their manual status. Done nodes whose prereqs are no
        longer satisfied are repaired to Blocked — recompute is the safety
        net that surfaces drift the cascade missed."""
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("GoalNode", type="Goal", status="Open"))
        mgr.add_node(make_node("DoneNode", status="Done"))
        with mgr.get_connection() as conn:
            conn.execute(
                "INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                ("Prereq", "GoalNode", EDGE_NEEDS_HARD),
            )
            conn.execute(
                "INSERT INTO Edges (source, target, type) VALUES (?, ?, ?)",
                ("Prereq", "DoneNode", EDGE_NEEDS_HARD),
            )
            conn.commit()
        mgr.recompute_all_statuses()
        # Goal status is user-controlled even when raw-SQL inserts created
        # an unsatisfied prereq.
        assert mgr.get_node("GoalNode").status == "Open"
        # Done with un-Done prereq is asymmetric drift; recompute repairs it.
        assert mgr.get_node("DoneNode").status == "Blocked"

    def test_recompute_all_statuses_normalizes_blocked_goal(self, mgr):
        """A Goal has no Blocked state. One stored as Blocked (e.g. stamped
        before Goals were exempted from the cascade) is drift the renderer
        paints red; recompute must normalize it back to Open."""
        mgr.add_node(make_node("GoalNode", type="Goal", status="Open"))
        with mgr.get_connection() as conn:
            conn.execute(
                "UPDATE Nodes SET status='Blocked' WHERE name='GoalNode'",
            )
            conn.commit()
        assert mgr.get_node("GoalNode").status == "Blocked"
        changed = mgr.recompute_all_statuses()
        assert changed == 1
        assert mgr.get_node("GoalNode").status == "Open"


# ============================================================================
# GraphManager — Goal Completion
# ============================================================================

class TestGoalCompletion:
    def test_no_subtree_returns_zeros(self, mgr):
        mgr.add_node(make_node("Goal", type="Goal"))
        result = mgr.get_goal_completion("Goal")
        assert result["total"] == 0
        assert result["done"] == 0
        assert result["pct"] == 0
        assert result["remaining_time"] == 0.0

    def test_all_done(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        result = mgr.get_goal_completion("Goal")
        assert result["total"] == 1
        assert result["done"] == 1
        assert result["pct"] == 100

    def test_partial_completion(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("C", status="Open"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "Goal", EDGE_NEEDS_HARD)
        result = mgr.get_goal_completion("Goal")
        assert result["total"] == 3
        assert result["done"] == 2
        assert result["pct"] == 67  # 2/3 rounded

    def test_remaining_time_excludes_done(self, mgr):
        mgr.add_node(make_node("A", status="Done", time_o=10, time_m=10, time_p=10))
        mgr.add_node(make_node("B", status="Open", time_o=5, time_m=5, time_p=5))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        result = mgr.get_goal_completion("Goal")
        assert result["remaining_time"] == 5.0  # Only B's time

    def test_is_blocked_all_subtasks_blocked(self, mgr):
        mgr.add_node(make_node("Prereq", status="Open"))
        mgr.add_node(make_node("A", status="Open"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Prereq", "A", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        # A is blocked because Prereq is Open
        mgr.get_goal_completion("Goal")
        # The subtree is [Prereq, A]. Prereq is Open, A is Blocked.
        # done + blocked = 0 + 1, total = 2 → not all blocked
        # Only "blocked" if ALL remaining are blocked
        # Prereq is Open (not blocked), so the goal is not fully blocked

    def test_is_blocked_flag(self, mgr):
        # Create a scenario where all subtask nodes are either done or blocked
        mgr.add_node(make_node("Blocker", status="Open"))
        mgr.add_node(make_node("A", status="Open"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Blocker", "A", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        # Subtree: {Blocker, A, B}. Blocker=Open, A=Blocked, B=Done
        # done + blocked = 1 + 1 = 2, total = 3, blocked > 0 → not all blocked
        result = mgr.get_goal_completion("Goal")
        assert result["is_blocked"] == False  # Blocker is still Open (workable)


# ============================================================================
# GraphManager — auto-Done candidate queue
# ============================================================================

class TestAutoDoneCandidates:
    """When the last hard prerequisite of a Goal or inherited-time container
    becomes Done, GraphManager should queue it as an auto-Done candidate.
    Milestones never queue. The UI
    drains this queue and surfaces a "Mark Done?" suggestion modal.
    """

    def test_pop_returns_and_clears(self, mgr):
        mgr._auto_done_candidates = ['A', 'B', 'C']
        popped = mgr.pop_auto_done_candidates()
        assert popped == ['A', 'B', 'C']
        assert mgr.pop_auto_done_candidates() == []

    def test_last_prereq_done_queues_goal(self, mgr):
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        # Flip P to Done — its only dependent G has all prereqs Done now.
        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == ["G"]

    def test_last_prereq_done_never_queues_milestone(self, mgr):
        # Finishing the work isn't evidence the target was hit, so a
        # Milestone is never suggested, though it inherits its time.
        mgr.add_node(make_node("M", type="Milestone", time_mode='inherited'))
        mgr.add_node(make_node("P", type="Learn"))
        mgr.add_edge("P", "M", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == []
        assert not mgr.is_auto_done_ready("M")

    def test_non_last_prereq_done_does_not_queue(self, mgr):
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("P1", type="Learn"))
        mgr.add_node(make_node("P2", type="Learn"))
        mgr.add_edge("P1", "G", EDGE_NEEDS_HARD)
        mgr.add_edge("P2", "G", EDGE_NEEDS_HARD)

        # P1 done, but P2 is still Open — Goal isn't ready.
        p1 = mgr.get_node("P1")
        p1.status = STATUS_DONE
        mgr.update_node(p1)

        assert mgr.pop_auto_done_candidates() == []

    def test_non_container_dependent_not_queued(self, mgr):
        # A Learn that depends on a Learn shouldn't be queued — only Goals
        # and Milestones get the auto-done suggestion.
        mgr.add_node(make_node("L1", type="Learn"))
        mgr.add_node(make_node("L2", type="Learn"))
        mgr.add_edge("L1", "L2", EDGE_NEEDS_HARD)

        l1 = mgr.get_node("L1")
        l1.status = STATUS_DONE
        mgr.update_node(l1)

        assert mgr.pop_auto_done_candidates() == []

    def test_already_done_container_not_queued(self, mgr):
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited',
                                status=STATUS_DONE))
        mgr.add_node(make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == []

    def test_resave_already_done_node_does_not_queue(self, mgr):
        # Re-saving an already-Done leaf shouldn't re-fire candidates.
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        # First save: P → Done. Queues G.
        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)
        mgr.pop_auto_done_candidates()  # Drain

        # Re-save P (still Done) — should NOT re-queue.
        p = mgr.get_node("P")
        mgr.update_node(p)
        assert mgr.pop_auto_done_candidates() == []

    def test_open_to_open_save_does_not_queue(self, mgr):
        # Saving a node without a Done transition shouldn't queue.
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.description = "edited"
        mgr.update_node(p)
        assert mgr.pop_auto_done_candidates() == []

    def test_multiple_containers_share_prereq(self, mgr):
        # One leaf shared between two Goals — when the leaf goes Done and
        # both Goals' other prereqs are also Done, both queue.
        mgr.add_node(make_node("G1", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("G2", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("Shared", type="Learn"))
        mgr.add_edge("Shared", "G1", EDGE_NEEDS_HARD)
        mgr.add_edge("Shared", "G2", EDGE_NEEDS_HARD)

        s = mgr.get_node("Shared")
        s.status = STATUS_DONE
        mgr.update_node(s)

        candidates = mgr.pop_auto_done_candidates()
        assert set(candidates) == {"G1", "G2"}

    def test_chained_containers_only_direct_queued(self, mgr):
        # Leaf → container → Goal. When leaf goes Done, only the container
        # is direct-eligible. The Goal still has the container as an Open
        # prereq, so it shouldn't queue yet.
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("C", type="Learn", time_mode='inherited'))
        mgr.add_node(make_node("L", type="Learn"))
        mgr.add_edge("L", "C", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "G", EDGE_NEEDS_HARD)

        l = mgr.get_node("L")
        l.status = STATUS_DONE
        mgr.update_node(l)
        assert mgr.pop_auto_done_candidates() == ["C"]

        # Mark the container Done — now Goal becomes a candidate.
        c = mgr.get_node("C")
        c.status = STATUS_DONE
        mgr.update_node(c)
        assert mgr.pop_auto_done_candidates() == ["G"]

    def test_milestone_marked_done_by_hand_queues_goal(self, mgr):
        # Leaf → Milestone → Goal. The Milestone waits for the user, and
        # marking it Done is what makes the Goal a candidate.
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("M", type="Milestone", time_mode='inherited'))
        mgr.add_node(make_node("L", type="Learn"))
        mgr.add_edge("L", "M", EDGE_NEEDS_HARD)
        mgr.add_edge("M", "G", EDGE_NEEDS_HARD)

        l = mgr.get_node("L")
        l.status = STATUS_DONE
        mgr.update_node(l)
        assert mgr.pop_auto_done_candidates() == []

        m = mgr.get_node("M")
        m.status = STATUS_DONE
        mgr.update_node(m)
        assert mgr.pop_auto_done_candidates() == ["G"]

    def test_milestone_with_no_prereqs_not_queued(self, mgr):
        # A Milestone with zero hard prereqs has "all prereqs done" vacuously.
        # We don't queue it — there's nothing concrete the user just achieved.
        mgr.add_node(make_node("M", type="Milestone", time_mode='inherited'))
        # Trigger collection by saving an unrelated Done node — but there's
        # no edge from it, so the dependent walk yields nothing.
        mgr.add_node(make_node("Other", type="Learn"))
        other = mgr.get_node("Other")
        other.status = STATUS_DONE
        mgr.update_node(other)
        assert mgr.pop_auto_done_candidates() == []

    def test_dedup_in_queue(self, mgr):
        # Multiple update_node calls that would each queue the same candidate
        # should only queue it once.
        mgr.add_node(make_node("G", type="Goal", time_mode='inherited'))
        mgr.add_node(make_node("P", type="Learn"))
        mgr.add_edge("P", "G", EDGE_NEEDS_HARD)

        p = mgr.get_node("P")
        p.status = STATUS_DONE
        mgr.update_node(p)
        # Re-save P (also as Done) to attempt double-queue
        p = mgr.get_node("P")
        mgr.update_node(p)

        assert mgr.pop_auto_done_candidates() == ["G"]


class TestMilestoneHitEarly:
    """A Milestone is a result. It can be hit before the work planned for it
    is finished, and reopening that work doesn't take the result back."""

    def _chain(self, mgr):
        # Program → Squat 1.5x BW → Heavier Program
        mgr.add_node(make_node("Program", type="Action"))
        mgr.add_node(make_node("Squat 1.5x BW", type="Milestone", time_mode='inherited'))
        mgr.add_node(make_node("Heavier Program", type="Action"))
        mgr.add_edge("Program", "Squat 1.5x BW", EDGE_NEEDS_HARD)
        mgr.add_edge("Squat 1.5x BW", "Heavier Program", EDGE_NEEDS_HARD)

    def _set_status(self, mgr, name, status):
        node = mgr.get_node(name)
        node.status = status
        mgr.update_node(node)

    def test_milestone_done_before_its_work(self, mgr):
        self._chain(mgr)
        assert mgr.get_node("Squat 1.5x BW").status == STATUS_BLOCKED

        self._set_status(mgr, "Squat 1.5x BW", STATUS_DONE)

        assert mgr.get_node("Squat 1.5x BW").status == STATUS_DONE
        assert mgr.get_node("Program").status == STATUS_OPEN
        assert mgr.get_node("Heavier Program").status == STATUS_OPEN
        assert mgr.recompute_all_statuses() == 0

    def test_reopening_the_work_keeps_the_milestone(self, mgr):
        self._chain(mgr)
        self._set_status(mgr, "Program", STATUS_DONE)
        self._set_status(mgr, "Squat 1.5x BW", STATUS_DONE)
        self._set_status(mgr, "Heavier Program", STATUS_DONE)

        assert mgr.get_downstream_done_dependents("Program") == []
        self._set_status(mgr, "Program", STATUS_OPEN)

        assert mgr.get_node("Squat 1.5x BW").status == STATUS_DONE
        assert mgr.get_node("Heavier Program").status == STATUS_DONE
        assert mgr.recompute_all_statuses() == 0

    def test_other_types_still_wait_for_their_work(self, mgr):
        self._chain(mgr)
        with pytest.raises(ValueError, match="can't be Done yet"):
            self._set_status(mgr, "Heavier Program", STATUS_DONE)

    def test_done_milestone_turned_action_must_meet_the_action_rule(self, mgr):
        self._chain(mgr)
        self._set_status(mgr, "Squat 1.5x BW", STATUS_DONE)
        node = mgr.get_node("Squat 1.5x BW")
        node.type = "Action"
        with pytest.raises(ValueError, match="can't be Done yet"):
            mgr.update_node(node)
