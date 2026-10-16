"""List sorts and the Events manual order are saved in Settings.

They used to live only in browser localStorage. That is per origin, so a new
port (P3.2 moves to dynamic ports), a different browser, or a cleared profile
silently reset them.
"""
from contextvars import copy_context

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict

from skilltree.features.events import callbacks as event_callbacks
from skilltree.ui.components import list_toolbar
from skilltree.store.settings import ConfigManager
from skilltree.store.events import EventManager
from skilltree.ui.components.list_toolbar import EVENTS_SORT, GOALS_SORT, build_list_toolbar
from skilltree.domain.models import Event


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


# --- A drag under a search ------------------------------------------------------
# A list posts only the cards it shows. Saving that as the whole order put
# every hidden item back in database order once the search was cleared.

def test_a_drag_reorders_the_shown_names_within_the_saved_order():
    from skilltree.ui.callback_helpers import merge_manual_order

    saved = ["A", "B", "C", "D", "E"]
    # A search shows B and D, and D is dragged above B.
    assert merge_manual_order(saved, ["D", "B"]) == ["A", "D", "C", "B", "E"]
    # Showing everything, the post is the order.
    assert merge_manual_order(saved, ["E", "D", "C", "B", "A"]) == ["E", "D", "C", "B", "A"]
    # A name the saved order lacks joins at its end, then takes its place.
    assert merge_manual_order(["A", "B"], ["New", "A"]) == ["New", "B", "A"]
    assert merge_manual_order(None, ["B", "A"]) == ["B", "A"]
    # Repeats and junk in the post count once.
    assert merge_manual_order(saved, ["D", "B", "D", 7]) == ["A", "D", "C", "B", "E"]


def test_an_event_drag_under_a_search_keeps_the_other_events_in_place():
    events = EventManager()
    for name in ("Trip", "Move", "Launch", "Party"):
        events.add_event(Event(name=name))
    ConfigManager.set_event_order(["Trip", "Move", "Launch", "Party"])
    reorder = _callbacks(event_callbacks.register_event_callbacks)["reorder_event"][0]

    # A search for "a" shows Launch and Party; Party is dragged above Launch.
    reorder('["Party", "Launch"]')

    assert ConfigManager.get_event_order() == ["Trip", "Move", "Party", "Launch"]


def test_a_goal_drag_under_a_search_keeps_the_other_goals_and_pins_in_place():
    from skilltree.features.goals import callbacks as sidebars_callbacks
    from test_atomic_saves import graph, node

    manager = graph()
    saved = ["Video", "Training", "Values", "Writing", "Stress", "Running"]
    for name in saved:
        manager.add_node(node(name, type="Goal", time_mode="inherited"))
    ConfigManager.set_goal_order(saved)
    ConfigManager.set_priority_goals(["Writing"])
    reorder = _callbacks(sidebars_callbacks.register_sidebars_callbacks)["reorder_goals"][0]

    # A search for "ing" shows the pinned Writing first, then Training and
    # Running. Running is dragged above Training.
    reorder('["Writing", "Running", "Training"]')

    # Running and Training swap slots. Writing leads the list because it is
    # pinned, not because of the drag, so its own slot stays.
    assert ConfigManager.get_goal_order() == [
        "Video", "Running", "Values", "Writing", "Stress", "Training"]
