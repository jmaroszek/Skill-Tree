"""
Callback definitions for the Events tab.
"""

import dash
from dash import html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
from event_manager import EventManager
from graph_manager import GraphManager
from config import ConfigManager
from models import Node, Event
from events_layout import build_event_card, build_dormant_nodes_table

event_manager = EventManager()
graph_manager = GraphManager()


def register_event_callbacks(app):

    # --- Tab Visibility Toggle ---
    @app.callback(
        Output("canvas-tab-content", "style"),
        Output("events-tab-content", "style"),
        Input("main-tabs", "active_tab"),
    )
    def toggle_tab_content(active_tab):
        base = {"width": "100%", "height": "100%", "overflow": "hidden", "position": "absolute", "top": "0", "left": "0"}
        canvas_style = {**base,
                        "display": "flex" if active_tab == "tab-canvas" else "none",
                        "visibility": "visible" if active_tab == "tab-canvas" else "hidden"}
        events_style = {**base,
                        "display": "flex" if active_tab == "tab-events" else "none",
                        "visibility": "visible" if active_tab == "tab-events" else "hidden"}
        return canvas_style, events_style

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
                html.P("No events yet. Click '+ New Event' to create one.", className="text-muted"),
                className="text-center py-5"
            )

        cards = []
        for event in events:
            counts = event_manager.get_event_node_count(event.name)
            cards.append(build_event_card(
                event.name, event.description, event.status, counts,
                is_selected=(event.name == selected_event)
            ))
        return cards

    # --- New Event ---
    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-detail-empty", "style", allow_duplicate=True),
        Output("event-detail-content", "style", allow_duplicate=True),
        Output("event-name", "value", allow_duplicate=True),
        Output("event-description", "value", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Input("btn-new-event", "n_clicks"),
        prevent_initial_call=True,
    )
    def create_new_event(n_clicks):
        if not n_clicks:
            return (no_update,) * 11

        return (
            None,  # selected_event_store — clear (new unsaved event)
            dash.callback_context.triggered_id,  # refresh trigger
            {"display": "none"},  # hide empty state
            {"display": "block"},  # show detail
            "",  # name
            "",  # description
            "New", "info",  # badge
            html.Div(
                html.P("Save the event first, then add dormant nodes.", className="text-muted"),
                className="text-center py-3"
            ),
            {"display": "none"},  # hide trigger section for new event
            "",  # save status
        )

    # --- Event Selection ---
    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-detail-empty", "style", allow_duplicate=True),
        Output("event-detail-content", "style", allow_duplicate=True),
        Output("event-name", "value", allow_duplicate=True),
        Output("event-description", "value", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Input({"type": "event-card", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def select_event(n_clicks_list):
        if not any(n_clicks_list):
            return (no_update,) * 11

        triggered = ctx.triggered_id
        if not triggered:
            return (no_update,) * 11

        event_name = triggered["index"]
        event = event_manager.get_event(event_name)
        if not event:
            return (no_update,) * 11

        event_nodes = event_manager.get_event_nodes(event_name)
        badge_color = "success" if event.status == "Triggered" else "primary"
        trigger_style = {"display": "none"} if event.status == "Triggered" else {"display": "flex", "alignItems": "center", "justifyContent": "flex-end"}

        return (
            event_name,  # selected_event_store
            f"select-{event_name}",  # refresh trigger
            {"display": "none"},  # hide empty state
            {"display": "block"},  # show detail
            event.name,
            event.description,
            event.status,
            badge_color,
            build_dormant_nodes_table(event_nodes, event.status),
            trigger_style,
            "",  # save status
        )

    # --- Save Event ---
    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Input("btn-event-save", "n_clicks"),
        State("selected-event-store", "data"),
        State("event-name", "value"),
        State("event-description", "value"),
        prevent_initial_call=True,
    )
    def save_event(n_clicks, selected_event, name, description):
        if not n_clicks or not name or not name.strip():
            return no_update, no_update, "Event name is required.", no_update, no_update, no_update

        name = name.strip()
        description = (description or "").strip()

        try:
            if selected_event is None:
                # New event
                event_manager.add_event(Event(name=name, description=description))
            else:
                # Update existing
                existing = event_manager.get_event(selected_event)
                event_manager.update_event(selected_event, Event(
                    name=name, description=description,
                    status=existing.status if existing else "Pending"
                ))
        except ValueError as e:
            return no_update, no_update, str(e), no_update, no_update, no_update

        event = event_manager.get_event(name)
        trigger_style = {"display": "none"} if event and event.status == "Triggered" else {"display": "flex", "alignItems": "center", "justifyContent": "flex-end"}
        badge_text = event.status if event else "Pending"
        badge_color = "success" if badge_text == "Triggered" else "primary"

        return name, f"save-{name}", "Saved.", trigger_style, badge_text, badge_color

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
            {"display": "block"},  # show empty state
            {"display": "none"},  # hide detail
            False,  # close modal
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
        Input("btn-trigger-confirm", "n_clicks"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def trigger_event(confirm_clicks, selected_event):
        if not confirm_clicks or not selected_event:
            return (no_update,) * 8

        result = event_manager.trigger_event(selected_event)
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
            {"display": "none"},  # hide trigger button
            build_dormant_nodes_table(event_nodes, "Triggered"),
            "Event triggered. " + ", ".join(msg_parts) + ".",
            False,  # close modal
        )

    # --- Open Dormant Node Modal ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-node-type", "options"),
        Output("dormant-node-context", "options"),
        Output("dormant-node-name", "value"),
        Output("dormant-node-desc", "value"),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        Input("btn-add-dormant-node", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_dormant_node_modal(n_clicks):
        if not n_clicks:
            return (no_update,) * 6

        types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": c, "value": c} for c in contexts]

        return True, type_opts, ctx_opts, "", "", ""

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
        Input("btn-dormant-node-save", "n_clicks"),
        State("selected-event-store", "data"),
        State("dormant-node-name", "value"),
        State("dormant-node-type", "value"),
        State("dormant-node-context", "value"),
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
    def save_dormant_node(n_clicks, selected_event, name, node_type, context, desc,
                          value, interest, difficulty, time_o, time_m, time_p,
                          delay_value, delay_unit):
        if not n_clicks:
            return (no_update,) * 4

        if not name or not name.strip():
            return no_update, "Node name is required.", no_update, no_update

        if not selected_event:
            return no_update, "Save the event first.", no_update, no_update

        name = name.strip()

        # Convert delay to days
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
        )

        try:
            event_manager.create_dormant_node(node, selected_event, delay_days=delay_days)
        except ValueError as e:
            return no_update, str(e), no_update, no_update

        event = event_manager.get_event(selected_event)
        event_nodes = event_manager.get_event_nodes(selected_event)

        return (
            False,  # close modal
            "",
            build_dormant_nodes_table(event_nodes, event.status if event else "Pending"),
            f"add-node-{name}",
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
