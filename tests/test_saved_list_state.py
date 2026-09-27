"""List sorts and the Events manual order are saved in Settings.

They used to live only in browser localStorage. That is per origin, so a new
port (P3.2 moves to dynamic ports), a different browser, or a cleared profile
silently reset them.
"""
from contextvars import copy_context

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict

import event_callbacks
import list_toolbar
from config import ConfigManager
from event_manager import EventManager
from list_toolbar import EVENTS_SORT, GOALS_SORT, build_list_toolbar
from models import Event


def _callbacks(register):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found.setdefault(fn.__name__, []).append(fn)
    return found


def _store(toolbar, store_id):
    for child in toolbar.children:
        if getattr(child, "id", None) == store_id:
            return child
    raise LookupError(store_id)


def test_a_sort_choice_is_saved_and_loads_with_the_next_page():
    save_sort = _callbacks(list_toolbar.register_list_toolbar_callbacks)["save_sort"]
    goals_save = next(fn for fn in save_sort
                      if fn.__defaults__[0] is GOALS_SORT)

    assert goals_save("alpha-asc") == "alpha-asc"
    assert goals_save("not-an-option") is dash.no_update

    toolbar = build_list_toolbar(dash.html.Div(), GOALS_SORT)
    assert _store(toolbar, GOALS_SORT.store_id).data == "alpha-asc"
    other = build_list_toolbar(dash.html.Div(), EVENTS_SORT)
    assert _store(other, EVENTS_SORT.store_id).data == EVENTS_SORT.default


def test_event_order_is_saved_and_follows_renames_and_deletes():
    events = EventManager()
    for name in ("Trip", "Move", "Launch"):
        events.add_event(Event(name=name))
    reorder = _callbacks(event_callbacks.register_event_callbacks)["reorder_event"][0]

    reorder('["Launch", "Trip", "Move"]')
    assert ConfigManager.get_event_order() == ["Launch", "Trip", "Move"]

    existing = events.get_event("Trip")
    events.update_event("Trip", Event(name="Voyage", trigger_mode=existing.trigger_mode))
    assert ConfigManager.get_event_order() == ["Launch", "Voyage", "Move"]

    events.delete_event("Move")
    assert ConfigManager.get_event_order() == ["Launch", "Voyage"]


def test_manual_event_list_uses_the_saved_order():
    events = EventManager()
    for name in ("Trip", "Move", "Launch"):
        events.add_event(Event(name=name))
    ConfigManager.set_event_order(["Move", "Launch", "Trip"])
    render = _callbacks(event_callbacks.register_event_callbacks)["render_events_list"][0]

    def run():
        context_value.set(AttributeDict(triggered_inputs=[
            {"prop_id": "events-refresh-trigger.data", "value": 1}]))
        # The store's page-load copy is stale; the saved order wins.
        return render(1, 0, None, ["Trip"], "", False, "manual", None)

    cards = copy_context().run(run)
    text = str(cards)
    assert text.index("Move") < text.index("Launch") < text.index("Trip")
