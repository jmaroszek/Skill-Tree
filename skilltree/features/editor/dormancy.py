"""The node editor's Dormant switch and Event section.

Dormant is an ordinary form field. Flipping it writes nothing; Save applies it
(commands.apply_dormancy). These callbacks keep its visibility in step with the switches, and collect it
into node-dormancy-form for Save and the unsaved-changes check. populate_editor
fills it, and the merge follows what changes elsewhere.
"""
import time

from dash import ClientsideFunction, Input, Output, State, ctx, no_update

from skilltree.features.editor.form import dormant_event_options


def register_dormancy_callbacks(app, services):
    event_manager = services.events

    # A blank form opened from the toolbar has the list it last had, and an event
    # created since would be missing. The merge sends the list with a section it
    # refills. A section being edited keeps the user's choice, so its list follows
    # here.
    @app.callback(
        Output("node-dormant-event", "options", allow_duplicate=True),
        Input("node-dormant", "value"),
        Input("events-refresh-trigger", "data"),
        State("node-dormant-event", "value"),
        prevent_initial_call=True,
    )
    def refresh_dormant_event_options(dormant, _refresh, current):
        if ctx.triggered_id == "node-dormant" and not dormant:
            return no_update
        return dormant_event_options(event_manager, current)

    # The wake date applies only while the node stays in the event that gave
    # it one; choosing another event moves the node, and a delay applies
    # there instead. The saved section in the pristine snapshot says which
    # event that is.
    app.clientside_callback(
        ClientsideFunction(namespace='editor_dormancy', function_name='collect_form'),
        Output("node-dormancy-form", "data"),
        Input("node-dormant", "value"),
        Input("node-dormant-event", "value"),
        Input("node-dormant-event-name", "value"),
        Input("node-dormant-delay-on", "value"),
        Input("node-dormant-delay-value", "value"),
        Input("node-dormant-delay-unit", "value"),
        Input("node-dormant-wake-date", "value"),
        Input("node-dormant-now", "value"),
        Input("editor-pristine-snapshot", "data"),
    )

    # Now and Done hide while Dormant is on, and Dormant hides while Now or
    # Done is on: a node being worked on, or finished, isn't asleep.
    # Unchecking Dormant on a sleeping node says what Save will do, which is
    # what the old wake-confirm modal used to ask.
    app.clientside_callback(
        ClientsideFunction(namespace='editor_dormancy', function_name='show_fields'),
        Output("node-now-wrapper", "style"),
        Output("node-status-done-wrapper", "style"),
        Output("node-dormant-wrapper", "style"),
        Output("node-dormant-section", "style"),
        Output("node-dormant-event-name", "style"),
        Output("node-dormant-settings", "style"),
        Output("node-dormant-wake-date-wrapper", "style"),
        Output("node-dormant-delay-switch", "style"),
        Output("node-dormant-delay-fields", "style"),
        Output("node-dormant-wake-warning", "style"),
        Output("node-dormant-wake-warning", "children"),
        Input("node-dormant", "value"),
        Input("node-now", "value"),
        Input("node-status-done", "value"),
        Input("node-dormant-event", "value"),
        Input("node-dormant-delay-on", "value"),
        Input("editor-pristine-snapshot", "data"),
    )

    # A save that put a node to sleep, changed its event or woke it has to reach
    # the Events tab, and its section has to follow what is stored now. The save
    # result is written only after the save commits, so it is the signal.
    @app.callback(
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("editor-save-result-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_events_after_save(save_result):
        if not isinstance(save_result, dict) or not save_result.get("sleeps_or_slept"):
            return no_update
        return f"editor-save-{int(time.time() * 1000)}"
