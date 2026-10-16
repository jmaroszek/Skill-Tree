"""The node editor's Dormant switch and Event section.

Dormant is an ordinary form field. Flipping it writes nothing; Save applies it
(commands.apply_dormancy). These callbacks fill the section from the database,
keep its visibility in step with the switches, and collect it into
node-dormancy-form for Save and the unsaved-changes check.
"""
import time

from dash import Input, Output, State, ctx, no_update

from skilltree.features.editor.form import (
    NEW_EVENT_OPTION, build_dormancy_snapshot, norm_dormancy,
)
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager

event_manager = EventManager()
graph_manager = GraphManager()


def register_dormancy_callbacks(app, services=None):
    event_manager = services.events if services is not None else globals()['event_manager']
    graph_manager = services.graph if services is not None else globals()['graph_manager']

    def _event_options(current=None):
        """Pending events, plus the node's own event when that one has fired
        and still holds it on a wake date."""
        options = [{"label": e.name, "value": e.name}
                   for e in event_manager.get_all_events() if e.status == "Pending"]
        if current and current != NEW_EVENT_OPTION and current not in {o["value"] for o in options}:
            options.insert(0, {"label": current, "value": current})
        return options + [{"label": "New event…", "value": NEW_EVENT_OPTION}]

    @app.callback(
        Output("node-dormant", "value"),
        Output("node-dormant-event", "options"),
        Output("node-dormant-event", "value"),
        Output("node-dormant-event-name", "value"),
        Output("node-dormant-delay-on", "value"),
        Output("node-dormant-delay-value", "value"),
        Output("node-dormant-delay-unit", "value"),
        Output("node-dormant-wake-date", "value"),
        Output("node-dormant-now", "value"),
        Output("node-dormant-loaded", "data"),
        Output("editor-pristine-snapshot", "data", allow_duplicate=True),
        Output("editor-dormant-preset", "data", allow_duplicate=True),
        Input("node-original-name", "data"),
        Input("events-refresh-trigger", "data"),
        Input("editor-save-result-store", "data"),
        State("editor-dormant-preset", "data"),
        State("editor-pristine-snapshot", "data"),
        State("node-dormancy-form", "data"),
        prevent_initial_call=True,
    )
    def populate_node_dormancy(node_name, _refresh, save_result, preset, snapshot, form):
        node = graph_manager.get_node(node_name) if node_name else None
        dormancy = build_dormancy_snapshot(node, event_manager)
        consumed = no_update
        trigger = ctx.triggered_id

        if trigger == "editor-save-result-store":
            # Only a save that found the node woken from under the editor
            # (form.woke_during_edit) leaves the section stale. The
            # post-save sync already set the baseline to awake.
            if not (isinstance(save_result, dict) and save_result.get("woke")):
                return (no_update,) * 12
            snapshot = None
        elif trigger == "events-refresh-trigger":
            # Any event change lands here. Unsaved edits to this section stay
            # as the user left them: only the baseline moves to what is
            # stored, so the unsaved-changes check still sees them.
            loaded = snapshot.get("dormancy") if isinstance(snapshot, dict) else None
            if (isinstance(snapshot, dict) and isinstance(form, dict)
                    and norm_dormancy(form) != norm_dormancy(loaded)):
                return ((no_update,) + (_event_options((form or {}).get("event")),)
                        + (no_update,) * 8
                        + ({**snapshot, "dormancy": dormancy}, no_update))

        # The Events tab's "+" opens a blank editor with Dormant already on
        # and the event chosen. The preset is used once, by the next blank
        # form, and only while it is fresh.
        if node is None and preset and preset.get("event"):
            consumed = None
            if time.time() * 1000 - (preset.get("ts") or 0) < 30_000:
                dormancy = {**dormancy, "dormant": True, "event": preset["event"]}

        if isinstance(snapshot, dict):
            snapshot = {**snapshot, "dormancy": dormancy}
        else:
            snapshot = no_update
        delayed = bool(dormancy["delay_value"])
        return (
            ["dormant"] if dormancy["dormant"] else [],
            _event_options(dormancy["event"]),
            dormancy["event"],
            "",
            ["on"] if delayed else [],
            dormancy["delay_value"] if delayed else 0,
            dormancy["delay_unit"] if delayed else "days",
            dormancy["wake_date"] or "",
            ["on"] if dormancy["now"] else [],
            bool(node is not None and node.dormant),
            snapshot,
            consumed,
        )

    # The list is also filled whenever Dormant is switched on. A blank form
    # opened from the toolbar never loads a node, so the populator above
    # never runs for it, and an event created since the last load would be
    # missing anyway.
    @app.callback(
        Output("node-dormant-event", "options", allow_duplicate=True),
        Input("node-dormant", "value"),
        State("node-dormant-event", "value"),
        prevent_initial_call=True,
    )
    def refresh_dormant_event_options(dormant, current):
        if not dormant:
            return no_update
        return _event_options(current)

    # A cancelled unsaved-changes prompt means the "+" never got its blank
    # form, so its preset must not wait around for the next one.
    @app.callback(
        Output("editor-dormant-preset", "data", allow_duplicate=True),
        Input("btn-unsaved-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def drop_dormant_preset(n_clicks):
        return None if n_clicks else no_update

    # The wake date applies only while the node stays in the event that gave
    # it one; choosing another event moves the node, and a delay applies
    # there instead. The saved section in the pristine snapshot says which
    # event that is.
    app.clientside_callback(
        """
        function(dormant, event, eventName, delayOn, delayValue, delayUnit,
                 wakeDate, now, snapshot) {
            function on(v) { return !!(v && v.indexOf('on') >= 0); }
            var saved = (snapshot && snapshot.dormancy) || {};
            var scheduled = saved.wake_date != null && !!event && event === saved.event;
            var delay = 0;
            if (!scheduled && on(delayOn)) {
                delay = (delayValue === undefined || delayValue === '') ? null : delayValue;
            }
            return {
                dormant: !!(dormant && dormant.indexOf('dormant') >= 0),
                event: event || null,
                event_name: eventName || '',
                delay_value: delay,
                delay_unit: delayUnit || 'days',
                // A cleared date stays '' rather than null, so Save can tell
                // a wake date that was emptied from no wake date at all.
                wake_date: scheduled ? (wakeDate || '') : null,
                now: on(now)
            };
        }
        """,
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
        """
        function(dormant, now, done, event, delayOn, snapshot) {
            var hide = {display: 'none'}, show = {};
            var isDormant = !!(dormant && dormant.indexOf('dormant') >= 0);
            var isBusy = !!(now && now.length) || !!(done && done.length);
            var saved = (snapshot && snapshot.dormancy) || {};
            var scheduled = saved.wake_date != null && !!event && event === saved.event;
            var waking = !!saved.dormant && !isDormant;
            var warning = '';
            if (waking) {
                warning = saved.event
                    ? 'Saving wakes this node and removes it from ' + saved.event + '.'
                    : 'Saving wakes this node.';
            }
            return [
                isDormant ? hide : show,
                isDormant ? hide : show,
                (isBusy && !isDormant) ? hide : show,
                isDormant ? show : hide,
                event === '__new__' ? show : hide,
                event ? show : hide,
                scheduled ? show : hide,
                scheduled ? hide : show,
                (!scheduled && delayOn && delayOn.length) ? show : hide,
                waking ? show : hide,
                warning
            ];
        }
        """,
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

    # A save that put a node to sleep, changed its event or woke it has to
    # reach the Events tab and refill the section from the database. The save
    # message is written only after the save commits, so it is the signal.
    @app.callback(
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("save-output", "children"),
        State("node-dormancy-form", "data"),
        State("node-dormant-loaded", "data"),
        prevent_initial_call=True,
    )
    def refresh_events_after_save(message, dormancy, was_dormant):
        saved = isinstance(message, str) and message.startswith(("Updated node", "Added node"))
        if not saved or not ((dormancy or {}).get("dormant") or was_dormant):
            return no_update
        return f"editor-save-{int(time.time() * 1000)}"
