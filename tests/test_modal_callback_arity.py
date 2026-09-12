"""Early exits must return one value per Output.

Removing the priority override dropped an Output from four modal openers but
left their no-op returns one value too long. Dash rejects a return of the wrong
length, so each fired a callback error whenever it had nothing to do, such as
when an event's dormant-node table rendered its edit buttons.
"""

import dash

import details_callbacks
import event_callbacks


def _callbacks(register):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register(app)
    found = {}
    for key, spec in app.callback_map.items():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            outputs = len(key.strip(".").split("...")) if key.startswith("..") else 1
            found[fn.__name__] = (fn, outputs)
    return found


def test_event_modal_openers_do_nothing_with_the_right_arity():
    found = _callbacks(event_callbacks.register_event_callbacks)
    for name, args in (("open_dormant_node_modal", (None,)),
                       ("open_modal_for_existing_nodes", ("",)),
                       ("open_dormant_node_modal_for_edit", ([], "", None))):
        fn, outputs = found[name]
        assert len(fn(*args)) == outputs, name


def test_details_add_node_opener_does_nothing_with_the_right_arity():
    fn, outputs = _callbacks(details_callbacks.register_details_callbacks)["open_add_node_modal"]
    assert len(fn(None, None)) == outputs
