"""Callbacks as a feature registers them, for tests that call one directly.

registered(register_editor_callbacks)["populate_editor"] is the function as
written: Dash's wrapper is taken off, so a test calls it with plain values.
"""
import dash

from skilltree.services import AppServices


def app_with(*registers, services=None):
    """A new Dash app with each ``register(app, services)`` run on it."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    services = services or AppServices()
    for register in registers:
        register(app, services)
    return app


def unwrapped(fn):
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def callbacks_of(app):
    """{name: function} for the server callbacks ``app`` holds. Of two
    callbacks with one name, the one registered first is kept."""
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        if fn is not None:
            fn = unwrapped(fn)
            found.setdefault(fn.__name__, fn)
    return found


def registered(*registers, services=None):
    """{name: function} for the callbacks ``registers`` add to a new app."""
    return callbacks_of(app_with(*registers, services=services))
