"""Community filter labels and ranking (community_labels)."""
from types import SimpleNamespace

import community_labels
from community_labels import MAX_LISTED, build_listing, label_communities


def _n(name, type="Learn", context="Mind", subcontext=None):
    return SimpleNamespace(name=name, type=type, context=context,
                           subcontext=subcontext)


def _e(source, target, type="Needs_Hard"):
    return {'source': source, 'target': target, 'type': type}


def _label(nodes, edges, hub_score=None):
    by_name = {n.name: n for n in nodes}
    return label_communities([set(by_name)], by_name, edges, hub_score)[0]


def _star(goal, leaves, context="Mind", subcontext=None):
    """A Goal fed by its leaves: leaf --Needs_Hard--> goal."""
    nodes = [_n(goal, "Goal", context, subcontext)]
    nodes += [_n(x, "Learn", context, subcontext) for x in leaves]
    return nodes, [_e(x, goal) for x in leaves]


class TestPrefix:
    def test_pure_subcontext_shows_context_and_subcontext(self):
        nodes, edges = _star("Sleep", ["A", "B", "C"], "Health", "Rhythms")
        assert _label(nodes, edges) == "Health > Rhythms: Sleep"

    def test_pure_context_with_mixed_subcontexts_shows_context_only(self):
        nodes, edges = _star("Sleep", ["A", "B"], "Health", "Rhythms")
        nodes += [_n("C", context="Health", subcontext="Exercise"),
                  _n("D", context="Health", subcontext="Mobility")]
        edges += [_e("C", "Sleep"), _e("D", "Sleep")]
        assert _label(nodes, edges) == "Health: Sleep"

    def test_mixed_cluster_has_no_prefix(self):
        nodes, edges = _star("Sleep", ["A", "B"], "Health")
        nodes += [_n("C", context="Mind"), _n("D", context="Mind")]
        edges += [_e("C", "Sleep"), _e("D", "Sleep")]
        assert _label(nodes, edges) == "Sleep"

    def test_tied_contexts_label_the_same_every_time(self):
        # Two subcontexts tie; the label must not depend on set order.
        nodes = [_n("P", "Goal", "Life", "Productivity"),
                 _n("S", "Goal", "Life", "Satisfaction"),
                 _n("A", context="Life", subcontext="Productivity"),
                 _n("B", context="Life", subcontext="Satisfaction")]
        edges = [_e("A", "P"), _e("B", "S"), _e("A", "B", "Helps")]
        by_name = {n.name: n for n in nodes}
        labels = {label_communities([set(order)], by_name, edges)[0]
                  for order in (["P", "S", "A", "B"], ["B", "A", "S", "P"])}
        assert len(labels) == 1


class TestHubs:
    def test_goal_reach_beats_a_busier_concept(self):
        # "Hub" has more neighbors, but the Goal sums up the cluster.
        nodes, edges = _star("Goal", ["A", "B", "C", "D"])
        nodes += [_n("Hub")]
        edges += [_e("Hub", x, "Helps") for x in ("A", "B", "C", "D")]
        assert _label(nodes, edges) == "Mind: Goal"

    def test_second_goal_joins_when_it_reaches_new_nodes(self):
        nodes, edges = _star("Big", ["A", "B", "C", "D", "E"])
        more, more_edges = _star("Other", ["F", "G", "H"])
        nodes += more
        edges += more_edges + [_e("Big", "Other", "Helps")]
        assert _label(nodes, edges) == "Mind: Big + Other"

    def test_second_goal_inside_the_first_ones_reach_is_dropped(self):
        nodes, edges = _star("Big", ["A", "B", "C", "D", "E"])
        nodes += [_n("Small", "Goal")]
        edges += [_e("A", "Small")]
        assert _label(nodes, edges) == "Mind: Big"

    def test_at_most_three_hubs(self):
        nodes, edges = [], []
        for goal in ("G1", "G2", "G3", "G4"):
            more, more_edges = _star(goal, [f"{goal}a", f"{goal}b"])
            nodes += more
            edges += more_edges
        assert _label(nodes, edges).count(" + ") == 2

    def test_extra_hubs_stop_at_the_length_budget(self):
        long_a, long_b = "A" * 30, "B" * 30
        nodes, edges = [], []
        for goal in (long_a, long_b):
            more, more_edges = _star(goal, [f"{goal}1", f"{goal}2"])
            nodes += more
            edges += more_edges
        # The first hub always shows; the second would pass the budget.
        assert _label(nodes, edges) == f"Mind: {long_a}"

    def test_goal_named_like_a_context_is_skipped(self):
        nodes, edges = _star("Mind", ["A", "B"])
        nodes += [_n("Logic", "Goal")]
        edges += [_e("A", "Logic"), _e("B", "Logic")]
        assert _label(nodes, edges) == "Mind: Logic"

    def test_no_goal_falls_back_to_hub_score(self):
        nodes = [_n(x) for x in ("Plan", "Draft", "Edit", "Publish")]
        edges = [_e("Plan", "Draft"), _e("Draft", "Edit"), _e("Edit", "Publish")]
        scores = {"Draft": 1.0, "Edit": 1.0}
        assert _label(nodes, edges, scores) == "Mind: Draft + Edit"

    def test_last_resort_is_the_best_connected_members(self):
        nodes = [_n(x) for x in ("A", "B", "C")]
        edges = [_e("A", "B", "Helps"), _e("A", "C", "Helps")]
        assert _label(nodes, edges) == "Mind: A + B"


class TestForeignHubs:
    def test_prefixed_cluster_takes_hubs_from_its_own_context(self):
        # Three Money nodes ride along with a Data Science cluster. Cash Flow
        # has the best hub score, but the cluster is 79% Data Science.
        ds = [_n(f"DS{i}", context="STEM", subcontext="Data Science") for i in range(11)]
        money = [_n(x, context="Money", subcontext="Personal Finance")
                 for x in ("Cash Flow", "Expenses", "Income")]
        edges = [_e(f"DS{i}", f"DS{i + 1}") for i in range(10)]
        edges += [_e("Expenses", "Cash Flow"), _e("Income", "Cash Flow"),
                  _e("Cash Flow", "DS0")]
        scores = {"Cash Flow": 5.0, "DS3": 1.0}
        label = _label(ds + money, edges, scores)
        assert "Cash Flow" not in label
        assert label == "STEM > Data Science: DS3"

    def test_mixed_cluster_ignores_contexts_under_a_fifth(self):
        # Stray reaches the whole cluster, but Money is 1 node in 7.
        nodes, edges = _star("Sleep", ["A", "B"], "Health")
        nodes += [_n("C", context="Health"), _n("D", context="Mind"),
                  _n("E", context="Mind"), _n("Stray", "Goal", "Money")]
        edges += [_e(x, "Stray") for x in ("A", "B", "C", "D", "E")]
        assert _label(nodes, edges) == "Sleep"


class TestSmallAndEdgeCases:
    def test_small_clusters_are_named_by_their_nodes(self):
        nodes = [_n("beta"), _n("Alpha")]
        assert _label(nodes, []) == "Alpha + beta"
        assert _label([_n("Solo")], []) == "Solo"

    def test_empty_and_unknown(self):
        assert label_communities([set()], {}, []) == ["Empty"]
        assert label_communities([{"Ghost"}], {}, []) == ["Unknown"]

    def test_labels_are_unique(self):
        a, ea = _star("G1", ["A", "B"])
        b, eb = _star("G2", ["C", "D"])
        by_name = {n.name: n for n in a + b}
        labels = label_communities([{"G1", "A", "B"}, {"G2", "C", "D"}],
                                   by_name, ea + eb)
        assert labels == ["Mind: G1", "Mind: G2"]


class TestListing:
    def test_ranked_by_summed_priority_not_size(self):
        big, small = {"a", "b", "c", "d"}, {"x", "y", "z"}
        priority = {"a": 1, "b": 1, "c": 1, "d": 1, "x": 5, "y": 5, "z": -1}
        listing = build_listing([big, small], ["Big", "Small"], priority)
        assert [label for label, _ in listing.listed] == ["Small", "Big"]

    def test_tiny_clusters_and_overflow_fold_into_other(self):
        clusters = [{f"c{i}a", f"c{i}b", f"c{i}c"} for i in range(MAX_LISTED + 2)]
        clusters += [{"solo"}, {"p1", "p2"}]
        labels = [f"L{i}" for i in range(len(clusters))]
        priority = {x: 1.0 for c in clusters for x in c}
        listing = build_listing(clusters, labels, priority)
        assert len(listing.listed) == MAX_LISTED
        assert listing.other_clusters == 4
        assert {"solo", "p1", "p2"} <= listing.other

    def test_orphan_mode_lists_single_nodes(self):
        clusters = [{"a"}, {"b"}]
        listing = build_listing(clusters, ["a", "b"], {"b": 2.0},
                                fold_small=False)
        assert [label for label, _ in listing.listed] == ["b", "a"]
        assert not listing.other

    def test_ties_fall_back_to_size_then_label(self):
        listing = build_listing([{"a", "b", "c"}, {"d", "e", "f", "g"}],
                                ["Zed", "Alpha"], {})
        assert [label for label, _ in listing.listed] == ["Alpha", "Zed"]


class TestCanvasOptions:
    @staticmethod
    def _view(manager, f_community, method="components"):
        from canvas_view import build_canvas_view
        from callbacks import generate_elements
        return build_canvas_view(manager, generate_elements, 'filter-community',
                                 None, method, {}, f_community, None, None, None)

    @staticmethod
    def _shown(view):
        return {e['data']['id'] for e in view.elements if 'source' not in e['data']}

    @staticmethod
    def _graph():
        from test_atomic_saves import graph
        manager = graph('Hub', 'A', 'B', 'Loner')
        manager.add_edge('A', 'Hub', 'Needs_Hard')
        manager.add_edge('B', 'Hub', 'Needs_Hard')
        return manager

    def test_options_are_keyed_by_label_and_end_with_other(self, temp_database):
        options = self._view(self._graph(), 'All').community_options
        assert options[0] == {"label": "All", "value": "All"}
        assert options[1]["value"] == options[1]["label"].rsplit(" (", 1)[0]
        assert options[1]["label"].endswith("(3 nodes)")
        assert options[-1] == {"label": "Other clusters (1 node)",
                               "value": community_labels.OTHER_VALUE}

    def test_selecting_a_row_or_other_narrows_the_canvas(self, temp_database):
        manager = self._graph()
        label = self._view(manager, 'All').community_options[1]["value"]
        assert self._shown(self._view(manager, label)) == {'Hub', 'A', 'B'}
        assert self._shown(self._view(manager, community_labels.OTHER_VALUE)) == {'Loner'}

    def test_a_stale_selection_shows_everything(self, temp_database):
        manager = self._graph()
        assert self._shown(self._view(manager, 'Gone')) == {'Hub', 'A', 'B', 'Loner'}

    def test_orphans_all_still_means_only_orphans(self, temp_database):
        view = self._view(self._graph(), 'All', method="orphans")
        assert self._shown(view) == {'Loner'}
        assert view.community_options[1] == {"label": "Loner (1 node)", "value": "Loner"}
