"""Community and Orphans narrow every view the filters reach, not just Nodes."""
import pytest

from skilltree.ui.filters import (
    SIDEBAR_FILTERS, filter_chip_state, filter_summary, filters_with_community,
    narrowed_to_community,
)
from support.graphs import graph


@pytest.fixture
def manager():
    manager = graph("A", "B", "C", "Island", "Alone")
    manager.add_edge("A", "B", "Needs_Hard")
    manager.add_edge("B", "C", "Needs_Hard")
    return manager


def _names(manager, filters):
    return {n.name for n in manager.filter_nodes(manager.get_all_nodes(), filters)}


def test_no_selection_changes_nothing(manager):
    filters = {"hide_done": True}
    assert narrowed_to_community(manager, filters, "All", "louvain") is filters
    assert narrowed_to_community(manager, filters, None, None) is filters


def test_a_community_narrows_filter_nodes(manager):
    rows = manager.list_communities(method="components", filters={})
    label, members = next((label, set(m)) for label, m in rows if "A" in m)
    filters = narrowed_to_community(manager, {}, label, "components")
    assert _names(manager, filters) == members == {"A", "B", "C"}


def test_all_in_orphans_mode_means_every_orphan(manager):
    filters = narrowed_to_community(manager, {}, "All", "orphans")
    assert _names(manager, filters) == {"Island", "Alone"}


def test_a_community_that_regrouped_narrows_nothing(manager):
    filters = {"hide_done": True}
    assert narrowed_to_community(manager, filters, "Gone", "louvain") is filters


def test_the_sidebar_group_carries_the_selection(manager):
    assert {"community", "community_method"} <= set(SIDEBAR_FILTERS)
    filters = filters_with_community(manager, {"community_method": "orphans"})
    assert _names(manager, filters) == {"Island", "Alone"}
    assert "community_names" not in filters_with_community(manager, None)


def test_the_list_reads_the_filters_without_the_selection(manager):
    # The rows come from the plain filters, so a selection can't shrink them.
    before = manager.list_communities(method="components", filters={})
    narrowed_to_community(manager, {}, "All", "orphans")
    assert manager.list_communities(method="components", filters={}) == before


def test_the_chip_names_it():
    text, _, hidden = filter_chip_state(filter_summary(community="Sleep"))
    assert text == "Community: Sleep" and not hidden
    text, _, hidden = filter_chip_state(filter_summary(community_method="orphans"))
    assert text == "Orphans" and not hidden
