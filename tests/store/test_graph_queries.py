"""Reading the graph: filters, Goal subtrees, effective time, communities."""
import pytest
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_DONE
from skilltree.store.graph import queries as graph_queries
from support.graphs import make_node


# ============================================================================
# Filtering
# ============================================================================

class TestFiltering:
    def test_filter_by_context(self, mgr):
        nodes = [make_node("A", context="Mind"), make_node("B", context="Body")]
        result = mgr.filter_nodes(nodes, {"context": "Mind"})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_by_subcontext(self, mgr):
        nodes = [make_node("A", subcontext="Rational"), make_node("B", subcontext="Sensory")]
        result = mgr.filter_nodes(nodes, {"subcontext": "Rational"})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_hide_done(self, mgr):
        nodes = [make_node("A", status="Done"), make_node("B", status="Open")]
        result = mgr.filter_nodes(nodes, {"hide_done": True})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_filter_by_min_value(self, mgr):
        nodes = [make_node("A", value=3), make_node("B", value=8)]
        result = mgr.filter_nodes(nodes, {"min_value": 5})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_filter_by_min_interest(self, mgr):
        nodes = [make_node("A", interest=2), make_node("B", interest=7)]
        result = mgr.filter_nodes(nodes, {"min_interest": 5})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_a_rating_filter_lets_through_a_node_without_its_own_ratings(self, mgr):
        """Its stored ratings only wait for a switch back to manual, and every
        screen shows it as Inherited, so a filter doesn't judge it on them."""
        header = make_node("Header", value=2, interest=2, difficulty=9)
        header.value_mode = "inherited"
        nodes = [header, make_node("Low", value=2)]
        assert [n.name for n in mgr.filter_nodes(nodes, {"min_value": 5})] == ["Header"]
        assert [n.name for n in mgr.filter_nodes(nodes, {"max_difficulty": 3})] == ["Header"]

    def test_filter_by_max_value(self, mgr):
        nodes = [make_node("A", value=3), make_node("B", value=8)]
        result = mgr.filter_nodes(nodes, {"max_value": 3})
        assert [n.name for n in result] == ["A"]

    def test_filter_by_value_band(self, mgr):
        nodes = [make_node("A", value=2), make_node("B", value=5), make_node("C", value=9)]
        result = mgr.filter_nodes(nodes, {"min_value": 4, "max_value": 6})
        assert [n.name for n in result] == ["B"]

    def test_filter_by_max_interest_and_min_difficulty(self, mgr):
        nodes = [make_node("A", interest=2, difficulty=8), make_node("B", interest=9, difficulty=8),
                 make_node("C", interest=2, difficulty=3)]
        result = mgr.filter_nodes(nodes, {"max_interest": 4, "min_difficulty": 5})
        assert [n.name for n in result] == ["A"]

    def test_filter_by_min_time(self, mgr):
        nodes = [make_node("A", time_o=1, time_m=1, time_p=1), make_node("B", time_o=100, time_m=100, time_p=100)]
        result = mgr.filter_nodes(nodes, {"min_time": 10})
        assert [n.name for n in result] == ["B"]

    def test_filter_by_time_band(self, mgr):
        nodes = [make_node("A", time_o=1, time_m=1, time_p=1),
                 make_node("B", time_o=20, time_m=20, time_p=20),
                 make_node("C", time_o=100, time_m=100, time_p=100)]
        result = mgr.filter_nodes(nodes, {"min_time": 10, "max_time": 50})
        assert [n.name for n in result] == ["B"]

    def test_filter_by_max_time(self, mgr):
        nodes = [make_node("A", time_o=1, time_m=1, time_p=1), make_node("B", time_o=100, time_m=100, time_p=100)]
        result = mgr.filter_nodes(nodes, {"max_time": 10})
        assert len(result) == 1
        assert result[0].name == "A"

    @staticmethod
    def _goal_over(mgr, *hours):
        """A Goal inheriting the given hours from its Hard prerequisites."""
        mgr.add_node(make_node("Goal", type="Goal", time_mode="inherited"))
        for i, h in enumerate(hours):
            mgr.add_node(make_node(f"T{i}", time_o=h, time_m=h, time_p=h))
            mgr.add_edge(f"T{i}", "Goal", EDGE_NEEDS_HARD)
        return mgr.get_all_nodes()

    def test_a_goal_is_as_long_as_the_work_it_inherits(self, mgr):
        """Its own time is 0, which made every Goal a quick win and none big."""
        nodes = self._goal_over(mgr, 60, 50)
        assert "Goal" in [n.name for n in mgr.filter_nodes(nodes, {"min_time": 100})]
        assert "Goal" not in [n.name for n in mgr.filter_nodes(nodes, {"max_time": 2})]

    def test_a_goal_with_little_left_is_a_quick_win(self, mgr):
        nodes = self._goal_over(mgr, 1)
        assert sorted(n.name for n in mgr.filter_nodes(nodes, {"max_time": 2})) == ["Goal", "T0"]

    def test_filter_by_max_difficulty(self, mgr):
        nodes = [make_node("A", difficulty=3), make_node("B", difficulty=8)]
        result = mgr.filter_nodes(nodes, {"max_difficulty": 5})
        assert len(result) == 1
        assert result[0].name == "A"

    def test_filter_by_search(self, mgr):
        nodes = [make_node("Python Basics"), make_node("Rust Advanced")]
        result = mgr.filter_nodes(nodes, {"search": "python"})
        assert len(result) == 1
        assert result[0].name == "Python Basics"

    def test_search_needs_every_term_in_any_order(self, mgr):
        nodes = [make_node("Skill Tree UI"), make_node("Skill Basics"),
                 make_node("Tree Surgery")]
        result = mgr.filter_nodes(nodes, {"search": "TREE skill"})
        assert [n.name for n in result] == ["Skill Tree UI"]

    def test_search_blank_filters_nothing(self, mgr):
        nodes = [make_node("A"), make_node("B")]
        assert mgr.filter_nodes(nodes, {"search": "   "}) == nodes

    def test_search_skips_descriptions_unless_asked(self, mgr):
        nodes = [make_node("A", description="Part of the Skill Tree app"),
                 make_node("Skill Tree UI", description="")]
        by_name = mgr.filter_nodes(nodes, {"search": "skill tree"})
        assert [n.name for n in by_name] == ["Skill Tree UI"]
        by_text = mgr.filter_nodes(
            nodes, {"search": "skill tree", "search_descriptions": True})
        assert [n.name for n in by_text] == ["A", "Skill Tree UI"]

    def test_search_matches_aliases(self, mgr):
        mgr.add_node(make_node("Cardio"))
        mgr.add_node(make_node("Strength"))
        mgr.set_aliases("Cardio", ["Aerobic Base"])
        result = mgr.filter_nodes(mgr.get_all_nodes(), {"search": "aerobic"})
        assert [n.name for n in result] == ["Cardio"]

    def test_hidden_by_status_counts_what_done_and_dormant_hide(self, mgr):
        nodes = [
            make_node("Open Skill"),
            make_node("Done Skill", status="Done"),
            make_node("Dormant Skill", dormant=1),
            make_node("Both Skill", status="Done", dormant=1),
            make_node("Other", status="Done"),
        ]
        filters = {"search": "skill", "hide_done": True}
        hidden = mgr.hidden_by_status(nodes, filters)
        assert hidden == {"hidden": 3, "done": 2, "dormant": 2}

    def test_hidden_by_status_ignores_a_switch_that_is_already_on(self, mgr):
        nodes = [make_node("A", status="Done"), make_node("B", dormant=1)]
        hidden = mgr.hidden_by_status(
            nodes, {"hide_done": True, "show_dormant": True})
        assert hidden == {"hidden": 1, "done": 1, "dormant": 0}

    def test_hidden_by_status_is_empty_when_the_other_filters_exclude_everything(self, mgr):
        nodes = [make_node("A", status="Done", context="Mind")]
        hidden = mgr.hidden_by_status(
            nodes, {"hide_done": True, "context": ["Body"]})
        assert hidden == {"hidden": 0, "done": 0, "dormant": 0}

    def test_combined_filters(self, mgr):
        nodes = [
            make_node("A", context="Mind", status="Done", value=8),
            make_node("B", context="Mind", status="Open", value=8),
            make_node("C", context="Body", status="Open", value=8),
            make_node("D", context="Mind", status="Open", value=2),
        ]
        result = mgr.filter_nodes(nodes, {"context": "Mind", "hide_done": True, "min_value": 5})
        assert len(result) == 1
        assert result[0].name == "B"

    def test_empty_filters_returns_all(self, mgr):
        nodes = [make_node("A"), make_node("B"), make_node("C")]
        result = mgr.filter_nodes(nodes, {})
        assert len(result) == 3


# ============================================================================
# Community Detection
# ============================================================================

class TestCommunityDetection:
    def test_disconnected_components(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        # C is disconnected
        communities = mgr.detect_communities(method="components")
        assert len(communities) == 2

    def test_single_connected_component(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("C"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        communities = mgr.detect_communities(method="components")
        assert len(communities) == 1

    def test_empty_graph(self, mgr):
        communities = mgr.detect_communities()
        assert len(communities) == 0

    def test_louvain_method(self, mgr):
        # Create a graph with enough structure for Louvain
        for name in ["A", "B", "C", "D", "E"]:
            mgr.add_node(make_node(name))
        mgr.add_edge("A", "B", EDGE_HELPS)
        mgr.add_edge("B", "C", EDGE_HELPS)
        mgr.add_edge("C", "A", EDGE_HELPS)
        mgr.add_edge("D", "E", EDGE_HELPS)
        communities = mgr.detect_communities(method="louvain")
        assert len(communities) >= 1
        # All nodes accounted for
        all_names = set()
        for c in communities:
            all_names.update(c)
        assert all_names == {"A", "B", "C", "D", "E"}

    def test_communities_with_filters(self, mgr):
        mgr.add_node(make_node("A", context="Mind"))
        mgr.add_node(make_node("B", context="Mind"))
        mgr.add_node(make_node("C", context="Body"))
        mgr.add_edge("A", "B", EDGE_HELPS)
        communities = mgr.detect_communities(method="components", filters={"context": "Mind"})
        all_names = set()
        for c in communities:
            all_names.update(c)
        assert "C" not in all_names


# ============================================================================
# Community Naming
# ============================================================================

class TestCommunityNaming:
    def test_empty_community(self, mgr):
        assert mgr.name_community(set()) == "Empty"

    def test_nonexistent_nodes(self, mgr):
        assert mgr.name_community({"DoesNotExist"}) == "Unknown"

    def test_names_a_cluster_after_its_goal(self, mgr):
        mgr.add_node(make_node("Sleep", type="Goal", context="Body"))
        for name in ("A", "B", "C"):
            mgr.add_node(make_node(name, context="Body"))
            mgr.add_edge(name, "Sleep", EDGE_NEEDS_HARD)
        assert mgr.name_community({"Sleep", "A", "B", "C"}) == "Body: Sleep"

    def test_single_node_uses_its_name(self, mgr):
        mgr.add_node(make_node("Solo Node", context="Body"))
        assert mgr.name_community({"Solo Node"}) == "Solo Node"

    def test_list_communities_ranks_and_skips_small_clusters(self, mgr):
        for goal, ctx, value in (("Low", "Mind", 1), ("High", "Body", 10)):
            mgr.add_node(make_node(goal, type="Goal", context=ctx))
            for i in range(3):
                leaf = f"{goal}{i}"
                mgr.add_node(make_node(leaf, context=ctx, value=value))
                mgr.add_edge(leaf, goal, EDGE_NEEDS_HARD)
        mgr.add_node(make_node("Loner"))
        rows = mgr.list_communities(method="components")
        assert [label for label, _ in rows] == ["Body: High", "Mind: Low"]


# ============================================================================
# GraphManager — Goal Subtree
# ============================================================================

class TestGoalSubtree:
    def test_empty_goal_no_prereqs(self, mgr):
        mgr.add_node(make_node("Goal", type="Goal"))
        subtree = mgr.get_goal_subtree("Goal")
        assert subtree == set()

    def test_single_prereq(self, mgr):
        mgr.add_node(make_node("Prereq", status="Done"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Prereq", "Goal", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal")
        assert subtree == {"Prereq"}

    def test_transitive_prereqs(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("B", status="Done"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Goal", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal")
        assert subtree == {"A", "B"}

    def test_includes_soft_prereqs(self, mgr):
        mgr.add_node(make_node("Soft"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Soft", "Goal", EDGE_NEEDS_SOFT)
        subtree = mgr.get_goal_subtree("Goal")
        assert "Soft" in subtree

    def test_goal_itself_excluded(self, mgr):
        mgr.add_node(make_node("A", status="Done"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("A", "Goal", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal")
        assert "Goal" not in subtree

    def test_nonexistent_goal(self, mgr):
        subtree = mgr.get_goal_subtree("DoesNotExist")
        assert subtree == set()


class TestGoalSubtreeHelps:
    """Helps is bidirectional at the seed step only — it does not chain."""

    def test_helps_partner_source_to_goal(self, mgr):
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Partner", "Goal", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree

    def test_helps_partner_goal_to_target(self, mgr):
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree

    def test_no_helps_of_helps_chaining(self, mgr):
        # Goal --Helps-- Partner --Helps-- FarPartner
        # FarPartner must NOT be pulled in under seed-only semantics.
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("FarPartner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Partner", "FarPartner", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree
        assert "FarPartner" not in subtree

    def test_partner_hard_prereqs_included_with_directed_types(self, mgr):
        # Goal --Helps-- Partner, and Prereq --Needs_Hard--> Partner.
        # With HARD+SOFT+HELPS, Prereq should be pulled in via BFS from Partner.
        mgr.add_node(make_node("Prereq"))
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Prereq", "Partner", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        assert "Partner" in subtree
        assert "Prereq" in subtree

    def test_helps_only_returns_direct_partners(self, mgr):
        # edge_types=(HELPS,) alone = direct partners, nothing else.
        mgr.add_node(make_node("Prereq"))
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Prereq", "Partner", EDGE_NEEDS_HARD)
        subtree = mgr.get_goal_subtree("Goal", edge_types=(EDGE_HELPS,))
        assert subtree == {"Partner"}

    def test_hard_soft_only_unaffected_by_helps_edges(self, mgr):
        # Helps edges in the graph must not leak into a HARD/SOFT-only query.
        mgr.add_node(make_node("Prereq"))
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Prereq", "Goal", EDGE_NEEDS_HARD)
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        subtree = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
        assert subtree == {"Prereq"}

    def test_synergy_label_set_arithmetic(self, mgr):
        # The synergy_nodes = overall - hard_soft arithmetic used in
        # details_layout.build_details_subtasks_table must correctly identify
        # a partner's Hard prereq as Synergy, not Soft.
        mgr.add_node(make_node("Prereq"))
        mgr.add_node(make_node("Partner"))
        mgr.add_node(make_node("Goal", type="Goal"))
        mgr.add_edge("Goal", "Partner", EDGE_HELPS)
        mgr.add_edge("Prereq", "Partner", EDGE_NEEDS_HARD)

        overall = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS))
        hard_soft = mgr.get_goal_subtree(
            "Goal", edge_types=(EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
        synergy_nodes = overall - hard_soft

        assert "Partner" in synergy_nodes
        assert "Prereq" in synergy_nodes
        assert hard_soft == set()


# ============================================================================
# GraphManager — get_effective_time
# ============================================================================

class TestGetEffectiveTime:
    def test_manual_returns_node_time(self, mgr):
        mgr.add_node(make_node("A", time_o=2, time_m=4, time_p=6, time_mode='manual'))
        eff = mgr.get_effective_time("A")
        node = mgr.get_node("A")
        assert eff == node.time

    def test_inherited_sums_subtree(self, mgr):
        mgr.add_node(make_node("A", time_o=3, time_m=3, time_p=3))
        mgr.add_node(make_node("B", time_o=5, time_m=5, time_p=5))
        mgr.add_node(make_node("Parent", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "Parent", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Parent", EDGE_NEEDS_HARD)
        eff = mgr.get_effective_time("Parent")
        assert eff == pytest.approx(3.0 + 5.0)

    def test_inherited_excludes_done(self, mgr):
        mgr.add_node(make_node("A", time_o=3, time_m=3, time_p=3, status="Done"))
        mgr.add_node(make_node("B", time_o=5, time_m=5, time_p=5, status="Open"))
        mgr.add_node(make_node("Parent", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "Parent", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Parent", EDGE_NEEDS_HARD)
        eff = mgr.get_effective_time("Parent")
        assert eff == pytest.approx(5.0)

    def test_inherited_empty_subtree(self, mgr):
        mgr.add_node(make_node("Alone", time_mode='inherited'))
        eff = mgr.get_effective_time("Alone")
        assert eff == 0.0

    def test_nonexistent_node(self, mgr):
        eff = mgr.get_effective_time("Ghost")
        assert eff == 0.0

    def test_inherited_transitive(self, mgr):
        """Inherited time includes transitive dependencies."""
        mgr.add_node(make_node("A", time_o=2, time_m=2, time_p=2))
        mgr.add_node(make_node("B", time_o=3, time_m=3, time_p=3))
        mgr.add_node(make_node("Top", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Top", EDGE_NEEDS_HARD)
        eff = mgr.get_effective_time("Top")
        assert eff == pytest.approx(2.0 + 3.0)

    def test_inherited_leaves_out_soft_prerequisites(self, mgr):
        """Soft prerequisites are optional, so they are not inherited."""
        mgr.add_node(make_node("Hard", time_o=3, time_m=3, time_p=3))
        mgr.add_node(make_node("Soft", time_o=50, time_m=50, time_p=50))
        mgr.add_node(make_node("Under", time_o=7, time_m=7, time_p=7))
        mgr.add_node(make_node("Top", time_mode='inherited', type="Goal"))
        mgr.add_edge("Hard", "Top", EDGE_NEEDS_HARD)
        mgr.add_edge("Soft", "Top", EDGE_NEEDS_SOFT)
        mgr.add_edge("Under", "Soft", EDGE_NEEDS_HARD)
        assert mgr.get_effective_time("Top") == pytest.approx(3.0)
        completion = mgr.get_goal_completion("Top", include_soft=False)
        assert mgr.get_effective_time("Top") == completion["remaining_time"]

    def test_inherited_times_match_get_effective_time(self, mgr):
        """The filter's one-pass figures are the ones Details shows."""
        mgr.add_node(make_node("A", time_o=2, time_m=2, time_p=2))
        mgr.add_node(make_node("B", time_o=3, time_m=3, time_p=3, status="Done"))
        mgr.add_node(make_node("C", time_o=5, time_m=5, time_p=5))
        mgr.add_node(make_node("Box", time_mode='inherited'))
        mgr.add_node(make_node("Top", time_mode='inherited', type="Goal"))
        mgr.add_node(make_node("Side", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "Box", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "Box", EDGE_NEEDS_HARD)
        mgr.add_edge("Box", "Top", EDGE_NEEDS_HARD)
        mgr.add_edge("A", "Top", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "Top", EDGE_NEEDS_SOFT)
        times = graph_queries.inherited_times(mgr)
        assert times == {name: mgr.get_effective_time(name) for name in ("Box", "Top", "Side")}
        assert times == {"Box": 2.0, "Top": 2.0, "Side": 0.0}

    def test_inherited_times_follow_a_change(self, mgr):
        """They are cached, so a Done flip must still reach them."""
        mgr.add_node(make_node("A", time_o=2, time_m=2, time_p=2))
        mgr.add_node(make_node("Top", time_mode='inherited', type="Goal"))
        mgr.add_edge("A", "Top", EDGE_NEEDS_HARD)
        assert graph_queries.inherited_times(mgr) == {"Top": 2.0}
        done = mgr.get_node("A")
        done.status = STATUS_DONE
        mgr.update_node(done)
        assert graph_queries.inherited_times(mgr) == {"Top": 0.0}


# ============================================================================
# Community Detection
# ============================================================================

class TestDetectCommunities:

    def test_empty_graph(self, mgr):
        result = mgr.detect_communities()
        assert result == []

    def test_single_component(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="components")
        assert len(result) == 1
        assert {"A", "B"} == result[0]

    def test_two_disconnected_components(self, mgr):
        for name in ["A", "B", "C", "D"]:
            mgr.add_node(make_node(name))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "D", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="components")
        assert len(result) == 2
        names = [c for c in result]
        assert {"A", "B"} in names
        assert {"C", "D"} in names

    def test_orphan_detection(self, mgr):
        mgr.add_node(make_node("A"))
        mgr.add_node(make_node("B"))
        mgr.add_node(make_node("Lone"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="orphans")
        assert len(result) == 1
        assert {"Lone"} in result

    def test_louvain_returns_communities(self, mgr):
        for name in ["A", "B", "C", "D"]:
            mgr.add_node(make_node(name))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("C", "D", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="louvain")
        assert len(result) >= 2
        all_names = set()
        for c in result:
            all_names |= c
        assert all_names == {"A", "B", "C", "D"}

    def test_filters_restrict_communities(self, mgr):
        mgr.add_node(make_node("A", context="Work"))
        mgr.add_node(make_node("B", context="Work"))
        mgr.add_node(make_node("C", context="Play"))
        mgr.add_edge("A", "B", EDGE_NEEDS_HARD)
        mgr.add_edge("B", "C", EDGE_NEEDS_HARD)
        result = mgr.detect_communities(method="components", filters={"context": ["Work"]})
        all_names = set()
        for c in result:
            all_names |= c
        assert "C" not in all_names
