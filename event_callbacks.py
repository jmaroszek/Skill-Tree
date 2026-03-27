"""
Callback definitions for the Events tab.
"""

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update
from event_manager import EventManager
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, Event
from events_layout import build_event_card, build_dormant_nodes_table, _event_badge, _event_trigger_type

event_manager = EventManager()
graph_manager = GraphManager()

_badge_hidden = {"fontSize": "0.85rem", "display": "none"}


def register_event_callbacks(app):

    # --- Tab Visibility Toggle ---
    @app.callback(
        Output("canvas-tab-content", "style"),
        Output("suggestions-tab-content", "style"),
        Output("goals-tab-content", "style"),
        Output("simulate-tab-content", "style"),
        Output("settings-tab-content", "style"),
        Output("events-tab-content", "style"),
        Input("main-tabs", "active_tab"),
    )
    def toggle_tab_content(active_tab):
        base = {"width": "100%", "height": "100%", "overflow": "hidden", "position": "absolute", "top": "0", "left": "0"}
        canvas_style = {**base,
                        "display": "flex" if active_tab == "tab-canvas" else "none",
                        "visibility": "visible" if active_tab == "tab-canvas" else "hidden"}
        suggestions_style = {**base,
                             "overflow": "auto",
                             "display": "block" if active_tab == "tab-suggestions" else "none",
                             "visibility": "visible" if active_tab == "tab-suggestions" else "hidden"}
        goals_style = {**base,
                       "display": "flex" if active_tab == "tab-goals" else "none",
                       "visibility": "visible" if active_tab == "tab-goals" else "hidden"}
        simulate_style = {**base, "overflow": "visible",
                          "display": "flex" if active_tab == "tab-simulate" else "none",
                          "visibility": "visible" if active_tab == "tab-simulate" else "hidden"}
        settings_style = {**base, "overflow": "auto",
                          "display": "block" if active_tab == "tab-settings" else "none",
                          "visibility": "visible" if active_tab == "tab-settings" else "hidden"}
        events_style = {**base,
                        "display": "flex" if active_tab == "tab-events" else "none",
                        "visibility": "visible" if active_tab == "tab-events" else "hidden"}
        return canvas_style, suggestions_style, goals_style, simulate_style, settings_style, events_style

    # --- Events List Rendering ---
    @app.callback(
        Output("events-list-container", "children"),
        Input("events-refresh-trigger", "data"),
        Input("main-tabs", "active_tab"),
        State("selected-event-store", "data"),
    )
    def render_events_list(refresh_trigger, active_tab, selected_event):
        events = event_manager.get_all_events()
        if not events:
            return html.Div(
                html.P("No events yet.", className="text-muted"),
                className="text-center py-5"
            )

        cards = []
        for event in events:
            counts = event_manager.get_event_node_count(event.name)
            cards.append(build_event_card(
                event.name, event.description, event.status, counts,
                is_selected=(event.name == selected_event),
                trigger_date=event.trigger_date,
                trigger_node=event.trigger_node,
            ))
        return cards

    # --- Populate trigger node dropdown when events tab opens ---
    @app.callback(
        Output("event-trigger-node", "options"),
        Input("main-tabs", "active_tab"),
        Input("events-refresh-trigger", "data"),
    )
    def populate_trigger_node_dropdown(active_tab, _refresh):
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name} for n in sorted(nodes, key=lambda n: n.name)]

    # --- Trigger Type Section Visibility ---
    @app.callback(
        Output("event-date-section", "style"),
        Output("event-node-section", "style"),
        Input("event-trigger-type", "value"),
    )
    def toggle_trigger_sections(trigger_type):
        date_style = {"display": "block"} if trigger_type == "date" else {"display": "none"}
        node_style = {"display": "block"} if trigger_type == "node" else {"display": "none"}
        return date_style, node_style

    # 13 outputs for create/select (same set of fields)
    _DETAIL_OUTPUTS = [
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-detail-empty", "style", allow_duplicate=True),
        Output("event-detail-content", "style", allow_duplicate=True),
        Output("event-name", "value", allow_duplicate=True),
        Output("event-description", "value", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Output("event-status-badge", "style", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Output("event-trigger-date", "value", allow_duplicate=True),
        Output("event-trigger-type", "value", allow_duplicate=True),
        Output("event-trigger-node", "value", allow_duplicate=True),
    ]
    _N_DETAIL = len(_DETAIL_OUTPUTS)

    # --- New Event ---
    @app.callback(
        *_DETAIL_OUTPUTS,
        Input("btn-new-event", "n_clicks"),
        prevent_initial_call=True,
    )
    def create_new_event(n_clicks):
        if not n_clicks:
            return (no_update,) * _N_DETAIL

        return (
            None,                   # selected_event_store — clear
            dash.callback_context.triggered_id,
            {"display": "none"},    # hide empty state
            {"display": "block"},   # show detail
            "",                     # name
            "",                     # description
            "", "primary", _badge_hidden,
            html.Div(
                html.P("Save the event first, then add dormant nodes.", className="text-muted"),
                className="text-center py-3"
            ),
            {"display": "none"},    # hide trigger/delete for new event
            "",                     # save status
            "",                     # trigger date
            "manual",               # trigger type
            None,                   # trigger node
        )

    # --- Event Selection ---
    @app.callback(
        *_DETAIL_OUTPUTS,
        Input({"type": "event-card", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def select_event(n_clicks_list):
        if not any(n_clicks_list):
            return (no_update,) * _N_DETAIL

        triggered = ctx.triggered_id
        if not triggered:
            return (no_update,) * _N_DETAIL

        event_name = triggered["index"]
        event = event_manager.get_event(event_name)
        if not event:
            return (no_update,) * _N_DETAIL

        event_nodes = event_manager.get_event_nodes(event_name)
        trigger_style = {"display": "none"} if event.status == "Triggered" else {
            "display": "flex", "alignItems": "center"
        }
        t_type = _event_trigger_type(event)

        return (
            event_name,
            f"select-{event_name}",
            {"display": "none"},
            {"display": "block"},
            event.name,
            event.description,
            "", "primary", _badge_hidden,
            build_dormant_nodes_table(event_nodes, event.status),
            trigger_style,
            "",
            event.trigger_date or "",
            t_type,
            event.trigger_node or None,
        )

    # --- Save Event ---
    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Output("event-status-badge", "style", allow_duplicate=True),
        Output("event-clear-interval", "disabled", allow_duplicate=True),
        Input("btn-event-save", "n_clicks"),
        State("selected-event-store", "data"),
        State("event-name", "value"),
        State("event-description", "value"),
        State("event-trigger-type", "value"),
        State("event-trigger-date", "value"),
        State("event-trigger-node", "value"),
        prevent_initial_call=True,
    )
    def save_event(n_clicks, selected_event, name, description, trigger_type, trigger_date, trigger_node):
        if not n_clicks or not name or not name.strip():
            return no_update, no_update, "Event name is required.", no_update, no_update, no_update, no_update, no_update

        name = name.strip()
        description = (description or "").strip()

        # Resolve trigger fields based on type
        resolved_date = trigger_date if trigger_type == "date" else None
        resolved_node = trigger_node if trigger_type == "node" else None

        try:
            if selected_event is None:
                event_manager.add_event(Event(
                    name=name, description=description,
                    trigger_date=resolved_date, trigger_node=resolved_node,
                ))
            else:
                existing = event_manager.get_event(selected_event)
                event_manager.update_event(selected_event, Event(
                    name=name, description=description,
                    status=existing.status if existing else "Pending",
                    trigger_date=resolved_date, trigger_node=resolved_node,
                ))
        except ValueError as e:
            return no_update, no_update, str(e), no_update, no_update, no_update, no_update, no_update

        event = event_manager.get_event(name)
        trigger_style = {"display": "none"} if event and event.status == "Triggered" else {
            "display": "flex", "alignItems": "center"
        }

        return name, f"save-{name}", "Saved.", trigger_style, "", "primary", _badge_hidden, False

    # --- Auto-dismiss save status ---
    @app.callback(
        Output("event-save-status", "children", allow_duplicate=True),
        Output("event-clear-interval", "disabled", allow_duplicate=True),
        Input("event-clear-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def clear_event_save_status(n):
        if n and n > 0:
            return "", True
        return no_update, no_update

    # --- Delete Event ---
    @app.callback(
        Output("modal-confirm-delete", "is_open", allow_duplicate=True),
        Input("btn-event-delete", "n_clicks"),
        Input("btn-delete-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_delete_modal(delete_clicks, cancel_clicks):
        trigger = ctx.triggered_id
        if trigger == "btn-event-delete" and delete_clicks:
            return True
        return False

    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-detail-empty", "style", allow_duplicate=True),
        Output("event-detail-content", "style", allow_duplicate=True),
        Output("modal-confirm-delete", "is_open", allow_duplicate=True),
        Input("btn-delete-confirm", "n_clicks"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def delete_event(confirm_clicks, selected_event):
        if not confirm_clicks or not selected_event:
            return (no_update,) * 5

        event_manager.delete_event(selected_event, delete_nodes=True)
        return (
            None,
            f"delete-{selected_event}",
            {"display": "block"},
            {"display": "none"},
            False,
        )

    # --- Trigger Event ---
    @app.callback(
        Output("modal-confirm-trigger", "is_open", allow_duplicate=True),
        Input("btn-trigger-event", "n_clicks"),
        Input("btn-trigger-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_trigger_modal(trigger_clicks, cancel_clicks):
        trigger = ctx.triggered_id
        if trigger == "btn-trigger-event" and trigger_clicks:
            return True
        return False

    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Output("modal-confirm-trigger", "is_open", allow_duplicate=True),
        Output("event-trigger-date", "value", allow_duplicate=True),
        Input("btn-trigger-confirm", "n_clicks"),
        Input("btn-trigger-all-confirm", "n_clicks"),
        State("selected-event-store", "data"),
        State({"type": "dormant-node-select", "index": ALL}, "value"),
        State({"type": "dormant-node-select", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def trigger_event(checked_clicks, all_clicks, selected_event, checkbox_values, checkbox_ids):
        triggered = ctx.triggered_id
        if not triggered or not selected_event:
            return (no_update,) * 9

        if triggered == "btn-trigger-all-confirm":
            selected_nodes = None
        else:
            selected_nodes = [
                cb_id["index"]
                for cb_id, checked in zip(checkbox_ids, checkbox_values)
                if checked
            ] if checkbox_ids else []

        result = event_manager.trigger_event(selected_event, selected_nodes=selected_nodes)
        event_nodes = event_manager.get_event_nodes(selected_event)
        msg_parts = []
        if result['activated']:
            msg_parts.append(f"{len(result['activated'])} node(s) activated")
        if result['scheduled']:
            msg_parts.append(f"{len(result['scheduled'])} node(s) scheduled")

        return (
            selected_event,
            f"trigger-{selected_event}",
            "Triggered", "success",
            {"display": "none"},
            build_dormant_nodes_table(event_nodes, "Triggered"),
            "Event triggered. " + (", ".join(msg_parts) if msg_parts else "No nodes selected."),
            False,
            "",
        )

    # --- Node Completion Confirmation Modal ---
    @app.callback(
        Output("modal-node-completion", "is_open", allow_duplicate=True),
        Output("node-completion-modal-desc", "children", allow_duplicate=True),
        Output("node-completion-event-list", "children", allow_duplicate=True),
        Input("node-completion-events-store", "data"),
        prevent_initial_call=True,
    )
    def show_node_completion_modal(event_names):
        if not event_names:
            return False, no_update, no_update

        desc = f"Completing this node triggers {len(event_names)} event(s). Select which to trigger:"
        event_list = html.Div([
            dbc.Checkbox(
                id={"type": "completion-event-select", "index": name},
                label=name,
                value=True,
                className="mb-1",
            )
            for name in event_names
        ])
        return True, desc, event_list

    @app.callback(
        Output("modal-node-completion", "is_open", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-node-completion-confirm", "n_clicks"),
        Input("btn-node-completion-skip", "n_clicks"),
        State({"type": "completion-event-select", "index": ALL}, "value"),
        State({"type": "completion-event-select", "index": ALL}, "id"),
        prevent_initial_call=True,
    )
    def handle_node_completion_confirm(confirm_clicks, skip_clicks, checkbox_values, checkbox_ids):
        triggered = ctx.triggered_id
        if triggered == "btn-node-completion-skip" or not confirm_clicks:
            return False, no_update

        # Trigger selected events
        import time
        for cb_id, checked in zip(checkbox_ids, checkbox_values):
            if checked:
                event_name = cb_id["index"]
                try:
                    event_manager.trigger_event(event_name, selected_nodes=None)
                except Exception:
                    pass

        return False, time.time()

    # --- Open Dormant Node Modal ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-node-type", "options"),
        Output("dormant-node-context", "options"),
        Output("dormant-node-subcontext", "options", allow_duplicate=True),
        Output("dormant-node-name", "value"),
        Output("dormant-node-desc", "value"),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        Input("btn-add-dormant-node", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_dormant_node_modal(n_clicks):
        if not n_clicks:
            return (no_update,) * 7

        types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": "None", "value": ""}] + [{"label": c, "value": c} for c in contexts]

        return True, type_opts, ctx_opts, [{"label": "None", "value": ""}], "", "", ""

    # --- Update Dormant Node Subcontexts ---
    @app.callback(
        Output("dormant-node-subcontext", "options"),
        Input("dormant-node-context", "value"),
    )
    def update_dormant_subcontexts(context):
        base = [{"label": "None", "value": ""}]
        if not context:
            return base
        subs = ConfigManager.get_subcontexts().get(context, [])
        return base + [{"label": s, "value": s} for s in subs]

    # --- Cancel Dormant Node Modal ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Input("btn-dormant-node-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_dormant_node_modal(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Save Dormant Node ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Input("btn-dormant-node-save", "n_clicks"),
        State("selected-event-store", "data"),
        State("event-name", "value"),
        State("event-description", "value"),
        State("event-trigger-date", "value"),
        State("dormant-node-name", "value"),
        State("dormant-node-type", "value"),
        State("dormant-node-context", "value"),
        State("dormant-node-subcontext", "value"),
        State("dormant-node-desc", "value"),
        State("dormant-node-value", "value"),
        State("dormant-node-interest", "value"),
        State("dormant-node-difficulty", "value"),
        State("dormant-node-time-o", "value"),
        State("dormant-node-time-m", "value"),
        State("dormant-node-time-p", "value"),
        State("dormant-node-delay-value", "value"),
        State("dormant-node-delay-unit", "value"),
        prevent_initial_call=True,
    )
    def save_dormant_node(n_clicks, selected_event,
                          event_name_val, event_desc_val, event_date_val,
                          name, node_type, context, subcontext, desc,
                          value, interest, difficulty, time_o, time_m, time_p,
                          delay_value, delay_unit):
        _nu7 = (no_update,) * 7
        if not n_clicks:
            return _nu7

        if not name or not name.strip():
            return no_update, "Node name is required.", no_update, no_update, no_update, no_update, no_update

        event_status_msg = no_update
        event_trigger_style = no_update
        if not selected_event:
            ev_name = (event_name_val or "").strip()
            if not ev_name:
                return no_update, "Enter an event name first, then add nodes.", no_update, no_update, no_update, no_update, no_update
            ev_desc = (event_desc_val or "").strip()
            ev_date = event_date_val or None
            try:
                event_manager.add_event(Event(name=ev_name, description=ev_desc, trigger_date=ev_date))
            except ValueError as e:
                return no_update, str(e), no_update, no_update, no_update, no_update, no_update
            selected_event = ev_name
            event_status_msg = "Event auto-saved."
            event_trigger_style = {"display": "flex", "alignItems": "center"}

        name = name.strip()
        delay_value = int(delay_value or 0)
        if delay_unit == "weeks":
            delay_days = delay_value * 7
        elif delay_unit == "months":
            delay_days = delay_value * 30
        else:
            delay_days = delay_value

        node = Node(
            name=name,
            type=node_type or "Learn",
            description=desc or "",
            value=value or 5,
            time_o=float(time_o or 0),
            time_m=float(time_m or 0),
            time_p=float(time_p or 0),
            interest=interest or 5,
            difficulty=difficulty or 5,
            status="Open",
            context=context or None,
            subcontext=(subcontext or '').strip() or None,
        )

        try:
            event_manager.create_dormant_node(node, selected_event, delay_days=delay_days)
        except ValueError as e:
            return no_update, str(e), no_update, no_update, selected_event, event_trigger_style, event_status_msg

        event = event_manager.get_event(selected_event)
        event_nodes = event_manager.get_event_nodes(selected_event)

        return (
            False,
            "",
            build_dormant_nodes_table(event_nodes, event.status if event else "Pending"),
            f"add-node-{name}",
            selected_event,
            event_trigger_style,
            event_status_msg,
        )

    # --- Remove Dormant Node ---
    @app.callback(
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input({"type": "btn-remove-dormant-node", "index": ALL}, "n_clicks"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def remove_dormant_node(n_clicks_list, selected_event):
        if not any(n_clicks_list) or not selected_event:
            return no_update, no_update

        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update

        node_name = triggered["index"]
        event_manager.remove_node_from_event(selected_event, node_name)

        event = event_manager.get_event(selected_event)
        event_nodes = event_manager.get_event_nodes(selected_event)

        return (
            build_dormant_nodes_table(event_nodes, event.status if event else "Pending"),
            f"remove-{node_name}",
        )
