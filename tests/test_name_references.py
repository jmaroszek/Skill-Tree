"""Settings that store node names follow a node through rename and delete."""
from contextvars import copy_context

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict

from skilltree.features.goals import callbacks as sidebars_callbacks
from skilltree.store import settings
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node
from skilltree.services import AppServices


def _goal(name):
    return Node(name=name, type="Goal", description="", value=5, interest=5,
                difficulty=5, time_o=1, time_m=2, time_p=4, context="Mind",
                status="Open")


def _add_goals(*names):
    manager = GraphManager()
    for name in names:
        manager.add_node(_goal(name))
    return manager


def test_rename_carries_the_goal_through_the_manual_order_and_priorities():
    manager = _add_goals("Alpha", "Beta", "Gamma")
    settings.GOAL_ORDER.set(["Gamma", "Alpha", "Beta"])
    settings.PRIORITY_GOALS.set(["Alpha"])

    manager.rename_node("Alpha", "Aleph")

    assert settings.GOAL_ORDER.get() == ["Gamma", "Aleph", "Beta"]
    assert settings.PRIORITY_GOALS.get() == ["Aleph"]


def test_delete_drops_the_goal_from_the_manual_order_and_priorities():
    manager = _add_goals("Alpha", "Beta", "Gamma")
    settings.GOAL_ORDER.set(["Gamma", "Alpha", "Beta"])
    settings.PRIORITY_GOALS.set(["Alpha", "Beta"])

    manager.delete_node("Alpha")

    assert settings.GOAL_ORDER.get() == ["Gamma", "Beta"]
    assert settings.PRIORITY_GOALS.get() == ["Beta"]


def _render_goal_names(stale_store_order):
    """Run render_goal_list in manual sort, with whatever the store holds."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_goals_callbacks(app, AppServices())
    render = next(
        spec["callback"].__wrapped__ for spec in app.callback_map.values()
        if getattr(spec.get("callback"), "__wrapped__", None) is not None
        and spec["callback"].__wrapped__.__name__ == "render_goal_list"
    )

    def run():
        context_value.set(AttributeDict(
            triggered_inputs=[{"prop_id": "goals-ui-refresh-trigger.data", "value": 1}]))
        return render("tab-next", None, None, None, None, "manual", stale_store_order,
                      None, {"transform": "translateX(0px)"})

    cards = copy_context().run(run)
    return [card.id["index"] if isinstance(card.id, dict) else card.id for card in cards]


def test_goals_sidebar_orders_a_renamed_goal_where_it_was(monkeypatch):
    manager = _add_goals("Alpha", "Beta", "Gamma")
    settings.GOAL_ORDER.set(["Gamma", "Alpha", "Beta"])
    # The page loaded the order before the rename; the store never hears of it.
    stale = settings.GOAL_ORDER.get()

    manager.rename_node("Alpha", "Aleph")

    names = _render_goal_names(stale)
    assert names.index("Gamma") < names.index("Aleph") < names.index("Beta")
