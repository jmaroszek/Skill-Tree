"""An event's sleeping nodes: their table, the + menu, Add to Event, and moving
or deleting a sleeping node."""
import time

from dash import ALL, Input, Output, State, ctx, no_update

from skilltree.domain.models import STATUS_DONE
from skilltree.features.events.layout import (
    build_dormant_nodes_table,
    dormant_delete_confirmation_body,
)
from skilltree.store import database
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.components.duration import duration_to_days, format_duration_days
from skilltree.ui.prerender import prerendered

event_manager = EventManager()
graph_manager = GraphManager()


def register_dormant_callbacks(app, services=None):
    event_manager = services.events if services is not None else globals()['event_manager']
    graph_manager = services.graph if services is not None else globals()['graph_manager']

    # Nodes join a saved, untriggered event. A Triggered event will not fire
    # again, so it stops accepting nodes; an unsaved one has no name for them
    # to join yet (its table says to save first).
    @app.callback(
        Output("dormant-add-btn-wrapper", "style"),
        Input("selected-event-store", "data"),
        Input("events-refresh-trigger", "data"),
        prevent_initial_call=True,
    )
    @prerendered
    def toggle_add_dormant_button(selected_event, _refresh):
        if not selected_event:
            return {"display": "none"}
        event = event_manager.get_event(selected_event)
        return {"display": "none"} if event and event.status == "Triggered" else {}

    # The node editor and the Add to Event modal change an event's roster
    # from outside the Events tab's own callbacks, which write the table
    # directly. A refresh redraws it for whichever event is open.
    @app.callback(
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Input("events-refresh-trigger", "data"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_dormant_nodes_table(_refresh, selected_event):
        event = event_manager.get_event(selected_event) if selected_event else None
        if event is None:
            return no_update
        return build_dormant_nodes_table(event_manager.get_event_nodes(selected_event), event)

    # --- Events tab: "+" > New node opens the node editor on a new dormant node ---
    # Clears the form through the editor's own New-node button, so the
    # unsaved-changes prompt behaves exactly as it does there. That button
    # lives inside the editor and never has to open it, so the sidebar is
    # opened here, the way the toolbar's fast path does (editor_sidebar.js).
    # The preset rides alongside and populate_node_dormancy applies it.
    app.clientside_callback(
        """
        function(choice, selectedEvent, editorStyle, goalStyle, eventsStyle) {
            var NO = window.dash_clientside.no_update;
            var parts = (choice || '').split('|');
            if (parts[0] !== 'new' || !selectedEvent) return [NO, NO, NO, NO];
            var n = Number(parts[1]) || 1;
            setTimeout(function() {
                var btn = document.getElementById('btn-editor-new');
                if (btn) btn.click();
            }, 0);
            var styles = window.dash_clientside.editor.open_on_add(
                n, editorStyle, goalStyle, eventsStyle);
            return [{event: selectedEvent, ts: Date.now()}].concat(styles);
        }
        """,
        Output("editor-dormant-preset", "data", allow_duplicate=True),
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Output("details-goal-sidebar", "style", allow_duplicate=True),
        Output("events-sidebar-container", "style", allow_duplicate=True),
        Input("dormant-add-choice-input", "value"),
        State("selected-event-store", "data"),
        State("sidebar-editor-container", "style"),
        State("details-goal-sidebar", "style"),
        State("events-sidebar-container", "style"),
        prevent_initial_call=True,
    )

    # --- Events tab: a row's Edit opens the node editor in place ---
    @app.callback(
        Output("details-edit-trigger-input", "value", allow_duplicate=True),
        Input({"type": "btn-edit-dormant-node", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def edit_dormant_node(n_clicks_list):
        triggered = ctx.triggered_id
        if not any(n_clicks_list or []) or not isinstance(triggered, dict):
            return no_update
        return f"{triggered['index']}|{int(time.time() * 1000)}"

    # --- Add to Event modal ---
    @app.callback(
        Output("modal-add-to-event", "is_open", allow_duplicate=True),
        Output("add-to-event-nodes", "options"),
        Output("add-to-event-nodes", "value"),
        Output("add-to-event-target", "options"),
        Output("add-to-event-target", "value"),
        Output("add-to-event-delay-value", "value"),
        Output("add-to-event-delay-unit", "value"),
        Output("add-to-event-now", "value"),
        Output("add-to-event-status", "children", allow_duplicate=True),
        Input("dormant-existing-trigger-input", "value"),
        Input("dormant-add-choice-input", "value"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_to_event_modal(trigger_val, choice, selected_event):
        _N = 9
        if not trigger_val and not choice:
            return (no_update,) * _N
        picked = []
        target = None
        if ctx.triggered_id == "dormant-existing-trigger-input":
            # context_menu.js writes a JSON list of node names plus "|<ms>".
            if not trigger_val:
                return (no_update,) * _N
            picked = bridge_payloads.names(trigger_val)
            if not picked:
                return (no_update,) * _N
        elif ctx.triggered_id == "dormant-add-choice-input":
            # The Events tab's "+" menu, "Existing nodes…".
            if not (choice or "").startswith("existing|") or not selected_event:
                return (no_update,) * _N
            target = selected_event
        else:
            return (no_update,) * _N

        # A node belongs to one event, and one its event already woke can't
        # sleep again, so only nodes with no event at all are offered. A
        # finished node has nothing to wait for; the editor won't make a Done
        # node dormant either.
        taken = event_manager.get_nodes_in_events()
        live = [n.name for n in graph_manager.get_all_nodes()
                if not n.dormant and n.name not in taken and n.status != STATUS_DONE]
        live_set = set(live)
        events = [{"label": e.name, "value": e.name}
                  for e in event_manager.get_all_events() if e.status == "Pending"]
        if target not in {e["value"] for e in events}:
            target = None
        return (
            True,
            [{"label": n, "value": n} for n in live],
            [n for n in picked if n in live_set],
            events,
            target,
            0, "days", [], "",
        )

    @app.callback(
        Output("modal-add-to-event", "is_open", allow_duplicate=True),
        Input("btn-add-to-event-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_add_to_event_modal(n_clicks):
        return False if n_clicks else no_update

    @database.atomic
    def _add_nodes_to_event(target, names, delay_days, now_on_trigger):
        # add_node_to_event refuses a node that already has an event, and
        # the refusal rolls back the whole batch.
        for name in names:
            if graph_manager.get_node(name):
                event_manager.add_node_to_event(target, name, delay_days,
                                                now_on_trigger=now_on_trigger)

    @app.callback(
        Output("modal-add-to-event", "is_open", allow_duplicate=True),
        Output("add-to-event-status", "children", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-add-to-event-save", "n_clicks"),
        State("add-to-event-nodes", "value"),
        State("add-to-event-target", "value"),
        State("add-to-event-delay-value", "value"),
        State("add-to-event-delay-unit", "value"),
        State("add-to-event-now", "value"),
        prevent_initial_call=True,
    )
    def save_add_to_event(n_clicks, names, target, delay_value, delay_unit, now_val):
        if not n_clicks:
            return (no_update,) * 3
        names = [n for n in (names or []) if n]
        if not names:
            return no_update, "Select at least one node.", no_update
        if not target:
            return no_update, "Pick an event.", no_update
        try:
            _add_nodes_to_event(target, names, duration_to_days(delay_value, delay_unit),
                                bool(now_val and "on" in now_val))
        except ValueError as e:
            return no_update, str(e), no_update
        return False, "", f"add-to-event-{target}-{int(time.time() * 1000)}"

    # --- Move a dormant node to another event ---

    @app.callback(
        Output("modal-move-dormant-node", "is_open", allow_duplicate=True),
        Output("move-dormant-title", "children"),
        Output("move-dormant-target-event", "options"),
        Output("move-dormant-target-event", "value"),
        Output("move-dormant-note", "children"),
        Output("move-dormant-status", "children", allow_duplicate=True),
        Output("move-dormant-node-store", "data"),
        Input({"type": "btn-move-dormant-node", "index": ALL}, "n_clicks"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def open_move_dormant_modal(n_clicks_list, selected_event):
        if not any(n_clicks_list) or not selected_event:
            return (no_update,) * 7
        node_name = ctx.triggered_id["index"]

        row = next((en for en in event_manager.get_event_nodes(selected_event)
                    if en['node'].name == node_name), None)
        if row is None:
            return (no_update,) * 7

        # Only pending events can take it: a fired one would never wake it.
        options = [{"label": e.name, "value": e.name}
                   for e in event_manager.get_all_events()
                   if e.status == "Pending" and e.name != selected_event]

        if not options:
            note = "There is no other pending event to move it to."
        elif row['delay_days']:
            note = (f"Its {format_duration_days(row['delay_days'])} delay moves "
                    "with it, measured from the new event's firing.")
        else:
            note = "It will wake when the new event fires."

        return (True, f'Move "{node_name}"', options, None, note, "", node_name)

    @app.callback(
        Output("modal-move-dormant-node", "is_open", allow_duplicate=True),
        Input("btn-move-dormant-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_move_dormant_modal(n_clicks):
        return False

    @app.callback(
        Output("modal-move-dormant-node", "is_open", allow_duplicate=True),
        Output("move-dormant-status", "children", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-move-dormant-confirm", "n_clicks"),
        State("move-dormant-node-store", "data"),
        State("move-dormant-target-event", "value"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_move_dormant_node(n_clicks, node_name, target_event, selected_event):
        if not n_clicks or not node_name or not selected_event:
            return no_update, no_update, no_update, no_update
        if not target_event:
            return no_update, "Pick an event to move it to.", no_update, no_update

        try:
            event_manager.move_node_to_event(selected_event, node_name, target_event)
        except ValueError as e:
            return no_update, str(e), no_update, no_update

        event = event_manager.get_event(selected_event)
        event_nodes = event_manager.get_event_nodes(selected_event)
        return (False, "", build_dormant_nodes_table(event_nodes, event),
                f"move-{node_name}-{int(time.time())}")

    # --- Delete Dormant Node ---
    # Deletes the node itself, not just this event's row: re-homing is Move's
    # job, and waking one is the editor's Dormant toggle. So it confirms first.
    @app.callback(
        Output("modal-delete-dormant-node", "is_open", allow_duplicate=True),
        Output("delete-dormant-body", "children"),
        Output("delete-dormant-node-store", "data"),
        Input({"type": "btn-delete-dormant-node", "index": ALL}, "n_clicks"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def open_delete_dormant_modal(n_clicks_list, selected_event):
        if not any(n_clicks_list) or not selected_event:
            return no_update, no_update, no_update
        node_name = ctx.triggered_id["index"]
        return True, dormant_delete_confirmation_body(node_name), node_name

    @app.callback(
        Output("modal-delete-dormant-node", "is_open", allow_duplicate=True),
        Input("btn-delete-dormant-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_delete_dormant_modal(n_clicks):
        return False

    @app.callback(
        Output("modal-delete-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-delete-dormant-confirm", "n_clicks"),
        State("delete-dormant-node-store", "data"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_delete_dormant_node(n_clicks, node_name, selected_event):
        if not n_clicks or not node_name or not selected_event:
            return no_update, no_update, no_update

        event_manager.delete_dormant_node(selected_event, node_name)

        event = event_manager.get_event(selected_event)
        event_nodes = event_manager.get_event_nodes(selected_event)
        # Timestamped like the move: deleting, re-creating, and deleting the
        # same name would otherwise write an unchanged value and not refresh.
        return (False, build_dormant_nodes_table(event_nodes, event),
                f"delete-{node_name}-{int(time.time())}")
