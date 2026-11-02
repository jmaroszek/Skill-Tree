"""Which node the canvas highlights after the node picker changes."""
from skilltree.engine.callbacks import searched_node
from skilltree.store.graph.manager import GraphManager


def test_a_picked_node_is_named_as_it_is():
    assert searched_node(GraphManager(), "SearchedNode", "stale") == "SearchedNode"


def test_a_cleared_picker_keeps_the_node_the_form_holds():
    assert searched_node(GraphManager(), None, "CurrentNode") == "CurrentNode"


def test_an_alias_nobody_has_stays_as_it_was_typed():
    assert searched_node(GraphManager(), "alias:Nobody", "stale") == "alias:Nobody"
