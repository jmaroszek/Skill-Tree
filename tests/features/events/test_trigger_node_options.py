"""The trigger-node dropdown lists dormant nodes as well as awake ones.

A dormant node that wakes as Done fires the events watching it, so an event
can wait on a node another event holds. The dropdown used to list awake
nodes only, so such a trigger, saved and working, showed as a blank field.
"""

from skilltree.domain.models import Node
from skilltree.features.events import callbacks as event_callbacks
from skilltree.store.graph.manager import GraphManager
from support.callbacks import registered


def _node(name, dormant):
    return Node(
        name=name, type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open", context="Mind", dormant=dormant,
    )


def test_dormant_nodes_are_trigger_options(temp_database):
    GraphManager().add_node(_node("Awake", dormant=0))
    GraphManager().add_node(_node("Move Out", dormant=1))

    populate = registered(event_callbacks.register_events_callbacks)[
        "populate_trigger_node_dropdown"]
    values = [option["value"] for option in populate(None, None)]

    assert "Awake" in values
    assert "Move Out" in values
