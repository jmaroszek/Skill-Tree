"""An open app wakes date-due events without waiting for a click.

Date triggers and wake dates were only checked when core_engine ran, so a
node due overnight stayed asleep, and off the Home list, until the first
interaction. event-clock checks them on an interval.
"""
from datetime import date, timedelta

import dash

import event_callbacks
from event_manager import EventManager
from graph_manager import GraphManager
from layout import build_app_layout
from models import Event, Node


def _clock():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app)
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if getattr(fn, "__name__", None) == "run_event_clock":
            return fn
    raise LookupError("run_event_clock")


def _find(component, component_id):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if hasattr(child, "children") or hasattr(child, "id"):
            found = _find(child, component_id)
            if found is not None:
                return found
    return None


def test_the_layout_runs_the_clock():
    clock = _find(build_app_layout([], env="sandbox"), "event-clock")
    assert clock is not None and not getattr(clock, "disabled", False)


def test_nothing_due_sends_no_refresh():
    assert _clock()(1) is dash.no_update


def test_a_due_date_trigger_fires_and_refreshes():
    GraphManager().add_node(Node(
        name="Plant", type="Action", description="", value=5, time_o=1,
        time_m=2, time_p=4, interest=5, difficulty=5, status="Open",
        context="Life"))
    events = EventManager()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    events.add_event(Event(name="Spring", trigger_date=yesterday))
    events.add_node_to_event("Spring", "Plant")

    refresh = _clock()(1)

    assert isinstance(refresh, str) and refresh.startswith("event-clock-")
    assert events.get_event("Spring").status == "Triggered"
    assert GraphManager().get_node("Plant").dormant == 0

def test_with_nothing_due_the_sweeps_only_read(monkeypatch):
    """core_engine runs both sweeps on every interaction. When nothing is due
    they only read, so another program holding the write lock (a backup or
    sync tool) doesn't hold up the page."""
    import sqlite3
    import database
    monkeypatch.setattr(database, "BUSY_TIMEOUT_S", 0.1)
    other = sqlite3.connect(database.get_db_path())
    other.execute("BEGIN IMMEDIATE")
    try:
        events = EventManager()
        assert events.check_pending_activations() == []
        assert events.check_scheduled_triggers() == []
    finally:
        other.rollback()
        other.close()
