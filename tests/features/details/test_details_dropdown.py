"""The Details tab's node picker holds every node View Details can reach."""
from skilltree.domain.models import Node
from skilltree.features.details.callbacks import register_details_callbacks
from support.callbacks import registered


def _node(name, **fields):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind", **fields)


def test_a_dormant_node_is_in_the_picker(services):
    # View Details sets the picker's value. A dropdown drops a value it has no
    # option for, so on a fresh page a dormant node's Details never loaded.
    services.graph.add_node(_node("Awake"))
    services.graph.add_node(_node("Asleep", dormant=1))
    fn = registered(register_details_callbacks, services=services)["populate_details_dropdown"]

    assert [o["value"] for o in fn(None, None)] == ["Asleep", "Awake"]
