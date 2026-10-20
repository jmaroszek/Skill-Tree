"""A Date event needs a date.

The editor saved a Date event with its date left blank. The empty string went
into the database, and the sweep read it as a date before every other: the
event fired on the next click and woke every node it held, while its card
still said Manual.
"""
import dash

from skilltree.store import database
from skilltree.features.events import callbacks as event_callbacks
from skilltree.store.events import EventManager
from skilltree.domain.models import Event, Node
from skilltree.services import AppServices
from skilltree.store.graph.manager import GraphManager


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind")


def _save_event():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_events_callbacks(app, AppServices())
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if getattr(fn, "__name__", None) == "save_event":
            return fn
    raise LookupError("save_event")


def _save(selected, trigger_date, name="Spring"):
    return _save_event()(1, selected, name, "", "date", trigger_date, [], "any")


def test_a_date_event_without_a_date_is_refused():
    for blank in (None, "", "   ", "not a date"):
        result = _save(None, blank)
        assert result[2] == "Pick a date."
    assert EventManager(GraphManager()).get_event("Spring") is None


def test_an_edit_that_clears_the_date_is_refused():
    events = EventManager(GraphManager())
    events.add_event(Event(name="Spring", trigger_date="2030-04-01"))

    assert _save("Spring", "")[2] == "Pick a date."
    assert events.get_event("Spring").trigger_date == "2030-04-01"


def test_a_date_event_with_a_date_saves():
    result = _save(None, "2030-04-01")

    assert result[2] == "Saved."
    assert EventManager(GraphManager()).get_event("Spring").trigger_date == "2030-04-01"


def test_a_blank_date_is_stored_as_none():
    events = EventManager(GraphManager())
    events.add_event(Event(name="Spring", trigger_date="  "))
    assert events.get_event("Spring").trigger_date is None

    events.update_event("Spring", Event(name="Spring", trigger_date=""))
    assert events.get_event("Spring").trigger_date is None

    events.update_event("Spring", Event(name="Summer", trigger_date=""))
    assert events.get_event("Summer").trigger_date is None


def test_a_date_with_a_time_after_it_fires_on_its_day():
    # An import accepts a date with a time after it, as Analyze reads one.
    # The sweep read the whole text as a date and raised, which rolled back
    # every event due with it, so none of them ever fired.
    events = EventManager(GraphManager())
    events.add_event(Event(name="Spring", trigger_date="2026-04-01"))
    events.add_event(Event(name="Summer", trigger_date="2026-06-01"))
    events.create_dormant_node(_node("Garden"), "Summer")
    with database.transaction() as conn:
        conn.execute("UPDATE Events SET trigger_date = '2026-04-01T09:30:00' "
                     "WHERE name = 'Spring'")

    assert sorted(events.check_scheduled_triggers()) == ["Spring", "Summer"]
    assert events.get_event("Spring").status == "Triggered"
    assert GraphManager().get_node("Garden").dormant == 0


def test_an_empty_date_saved_before_the_fix_never_fires():
    events = EventManager(GraphManager())
    events.add_event(Event(name="Spring"))
    events.create_dormant_node(_node("Garden"), "Spring")
    with database.transaction() as conn:
        conn.execute("UPDATE Events SET trigger_date = '' WHERE name = 'Spring'")

    assert events.check_scheduled_triggers() == []
    assert events.get_event("Spring").status == "Pending"
    assert events.get_node_membership("Garden") is not None  # still waiting
