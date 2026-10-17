"""Details applies every sidebar filter, the Time filter's unit included.

Its callbacks listed the filter controls one by one and had lost the unit, so
a maximum of 10 weeks read as 10 hours on the Details graph, its subtasks and
its milestones, while the Nodes canvas and Details' own simulation used weeks.
They now take the controls as one group (ui/filters.SIDEBAR_FILTERS).
"""
import dash
import pytest

from skilltree.features.details import callbacks as details_callbacks
from skilltree.ui.filters import SIDEBAR_FILTERS, build_filters, filters_from
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import EDGE_NEEDS_HARD, Node
from skilltree.services import AppServices

APPLIES_THE_FILTERS = ("select_detail_node", "render_details_subtasks",
                       "toggle_details_subtask_filters", "update_details_graph")


def _registered():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    details_callbacks.register_details_callbacks(app, AppServices())
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found[getattr(fn, "__name__", None)] = (fn, spec)
    return found


@pytest.mark.parametrize("name", APPLIES_THE_FILTERS)
def test_every_details_view_reads_every_sidebar_filter(name):
    _fn, spec = _registered()[name]
    read = {(dep["id"], dep["property"]) for dep in spec["inputs"] + spec["state"]}

    assert set(SIDEBAR_FILTERS.values()) <= read


def test_the_group_builds_the_same_filters_as_the_controls():
    values = dict(context=["Mind"], done=["show_done"], value=[3, 9], time=10,
                  time_unit="weeks", time_min=1, types=["Learn"],
                  dormant=["show_dormant"], search={"text": "sleep"})

    assert filters_from(values) == build_filters(
        ["Mind"], None, ["show_done"], [3, 9], None, 10, None, ["Learn"],
        f_time_unit="weeks", f_show_dormant=["show_dormant"], f_time_min=1,
        f_search={"text": "sleep"})
    assert filters_from(None) == build_filters(None, None, None)


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=100.0, time_m=100.0, time_p=100.0, interest=5,
                  difficulty=5, status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


def test_a_maximum_in_weeks_reaches_the_details_graph():
    manager = GraphManager()
    manager.add_node(_node("Goal", type="Goal", time_mode="inherited"))
    manager.add_node(_node("Hundred Hours"))
    manager.add_edge("Hundred Hours", "Goal", EDGE_NEEDS_HARD)
    graph, _spec = _registered()["update_details_graph"]

    def shown(time, unit):
        elements = graph("Goal", 0, 0, [], [], None, [],
                         {"time": time, "time_unit": unit}, [])
        return {e["data"]["id"] for e in elements if "source" not in e["data"]}

    # 10 hours leaves the 100-hour task out; 10 weeks (200 hours at the
    # default 20 a week) keeps it.
    assert "Hundred Hours" not in shown(10, "hours")
    assert "Hundred Hours" in shown(10, "weeks")
