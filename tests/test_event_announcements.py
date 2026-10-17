"""The Events Triggered announcement appears while the app is open, and
closing it drops only what it showed.

It used to be checked once, half a second after launch, so an event that
fired on its date while the app was open waited for the next launch. And
Dismiss cleared every queued notification, including any queued while the
announcement was open, unread.
"""
import dash
import pytest

from skilltree.features.events import callbacks as event_callbacks
from skilltree.store.settings import ConfigManager


@pytest.fixture
def handlers(services):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    event_callbacks.register_event_callbacks(app, services)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


def _entry(event):
    return {"kind": "date_triggered", "event": event, "activated": ["A"],
            "scheduled": [], "when": "2026-10-12"}


def test_an_event_firing_while_open_is_announced(handlers):
    show = handlers["show_event_announcements"]
    assert show(None, None, 1, None) == (dash.no_update,) * 3
    ConfigManager.add_pending_event_notification(_entry("Spring"))
    is_open, _body, shown = show(None, None, 2, None)  # the graph changed
    assert is_open is True and shown == [_entry("Spring")]
    # Nothing new: an unrelated change doesn't redraw it.
    assert show(None, None, 3, shown) == (dash.no_update,) * 3


def test_closing_drops_only_what_was_shown(handlers):
    ConfigManager.add_pending_event_notification(_entry("Spring"))
    _, _, shown = handlers["show_event_announcements"](1, None, None, None)
    ConfigManager.add_pending_event_notification(_entry("Summer"))  # while open
    assert handlers["forget_shown_announcements"](False, shown) is None
    assert ConfigManager.get_pending_event_notifications() == [_entry("Summer")]
    # Opening it again forgets nothing.
    assert handlers["forget_shown_announcements"](True, [_entry("Summer")]) is dash.no_update
