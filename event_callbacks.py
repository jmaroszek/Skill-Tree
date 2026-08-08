"""
Callback definitions for the Events tab.
"""

import json
import time
import dash
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction
from event_manager import EventManager
from graph_manager import GraphManager
from config import ConfigManager, sort_subcontexts, sort_contexts
from models import Node, Event, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from events_layout import build_event_card, build_dormant_nodes_table, _event_trigger_type
from callback_helpers import (render_link_rows, render_alias_rows, serialize_links,
                              spawn_local_file_picker,
                              strip_gdrive_prefix, habit_to_hours, compute_habit_time_omp,
                              habit_preview_text, habit_editor_view,
                              resolve_time_mode, resolve_value_mode)

event_manager = EventManager()
graph_manager = GraphManager()

_badge_hidden = {"fontSize": "0.85rem", "display": "none"}


def _normalize_trigger_nodes(value):
    """Coerces a trigger-node dropdown value into a de-duplicated list.

    A multi Dropdown yields a list, but the same component can hand back a
    bare string (single leftover selection) or None (cleared), so all three
    shapes are flattened here rather than at each call site.
    """
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    out = []
    for name in value:
        if name and name not in out:
            out.append(name)
    return out


def _trigger_mode_hint(trigger_mode, trigger_nodes):
    """Help text under a node-completion trigger, describing the live selection.

    At one node the any/all distinction is meaningless, so the text collapses
    to the plain single-node wording rather than naming a mode the user can't
    meaningfully act on.
    """
    names = _normalize_trigger_nodes(trigger_nodes)
    if not names:
        return "Auto-triggers when the selected node is marked complete."
    if len(names) == 1:
        return f"Auto-triggers when {names[0]} is marked complete."
    if trigger_mode == "all":
        return f"Auto-triggers once all {len(names)} selected nodes are marked complete."
    return "Auto-triggers as soon as any one of the selected nodes is marked complete."


def _render_announcements(entries):
    """Formats pending event notification entries into a readable list for the modal body.

    Only renders informational kinds — override_conflict entries are handled separately
    via a choice modal, not shown here.
    """
    items = []
    for entry in entries:
        kind = entry.get("kind")
        when = entry.get("when", "")
        event_name = entry.get("event")
        activated = entry.get("activated") or []
        scheduled = entry.get("scheduled") or []

        if kind == "date_triggered":
            summary = html.Strong(f"{event_name} — date-triggered ({when})")
            detail = _format_node_counts(activated, scheduled)
        elif kind == "node_triggered":
            trig = entry.get("trigger_node", "?")
            trig_set = entry.get("trigger_nodes") or []
            if len(trig_set) > 1 and entry.get("trigger_mode") == "all":
                summary = html.Strong(
                    f"{event_name} — triggered: all {len(trig_set)} nodes complete, "
                    f"last was {trig} ({when})")
            else:
                summary = html.Strong(f"{event_name} — triggered by completing {trig} ({when})")
            detail = _format_node_counts(activated, scheduled)
        elif kind == "delayed_activated":
            nodes = entry.get("nodes") or []
            summary = html.Strong(f"{event_name} — delayed nodes activated ({when})")
            detail = f"Nodes: {', '.join(nodes)}" if nodes else ""
        elif kind == "trigger_node_deleted":
            deleted = entry.get("deleted_node", "?")
            events = entry.get("events") or []
            # Older entries predate the narrowed/demoted split — fall back to
            # treating every affected event as demoted, which is what the
            # single-trigger era always meant.
            demoted = entry.get("demoted", events) or []
            narrowed = entry.get("narrowed") or []
            summary = html.Strong(f"Trigger node deleted: {deleted} ({when})")
            parts = []
            if narrowed:
                parts.append(f'{", ".join(narrowed)} — removed "{deleted}" from the '
                             "trigger set; remaining conditions still apply.")
            if demoted:
                parts.append(f'{", ".join(demoted)} — "{deleted}" was the only trigger '
                             "left, so these are now manual-trigger only.")
            detail = " ".join(parts) if parts else ""
        else:
            continue  # override_conflict and unknowns are not shown here

        items.append(html.Li([summary, html.Br(), html.Span(detail, className="text-muted small")] if detail else [summary]))
    return html.Ul(items, style={"marginBottom": 0})


def _format_override_conflict_body(entry):
    """Builds the conflict-modal body text for a deferred override_conflict entry."""
    ev = entry.get("event", "?")
    candidates = entry.get("candidate_nodes") or []
    desc = entry.get("current_override_descriptor") or {}
    if desc.get("kind") == "parent":
        current_desc = f'the node "{desc.get("parent")}"'
    else:
        nodes = desc.get("nodes") or []
        current_desc = f"{len(nodes)} event-pinned node(s): {', '.join(nodes)}"
    cand_desc = ", ".join(candidates)
    return (f'Event "{ev}" activated {len(candidates)} node(s) configured for priority '
            f'override: {cand_desc}. An override is already active for {current_desc}. '
            f'Only one override can be active at a time — which do you want to keep?')


def _format_node_counts(activated, scheduled):
    parts = []
    if activated:
        parts.append(f"{len(activated)} activated: {', '.join(activated)}")
    if scheduled:
        parts.append(f"{len(scheduled)} scheduled: {', '.join(scheduled)}")
    return " — ".join(parts) if parts else "No nodes"


def register_event_callbacks(app):

    # --- Tab Visibility Toggle ---
    @app.callback(
        Output("next-tab-content", "style"),
        Output("canvas-tab-content", "style"),
        Output("details-tab-content", "style"),
        Output("events-tab-content", "style"),
        Output("analyze-tab-content", "style"),
        Input("main-tabs", "active_tab"),
    )
    def toggle_tab_content(active_tab):
        base = {"width": "100%", "height": "100%", "overflow": "hidden", "position": "absolute", "top": "0", "left": "0"}
        next_style = {**base,
                      "overflow": "auto",
                      "display": "block" if active_tab == "tab-next" else "none",
                      "visibility": "visible" if active_tab == "tab-next" else "hidden"}
        canvas_style = {**base,
                        "display": "flex" if active_tab == "tab-canvas" else "none",
                        "visibility": "visible" if active_tab == "tab-canvas" else "hidden"}
        details_style = {**base,
                         "display": "flex" if active_tab == "tab-details" else "none",
                         "visibility": "visible" if active_tab == "tab-details" else "hidden"}
        events_style = {**base,
                        "display": "flex" if active_tab == "tab-events" else "none",
                        "visibility": "visible" if active_tab == "tab-events" else "hidden"}
        analyze_style = {**base, "overflow": "auto",
                         "display": "block" if active_tab == "tab-analyze" else "none",
                         "visibility": "visible" if active_tab == "tab-analyze" else "hidden"}
        return next_style, canvas_style, details_style, events_style, analyze_style

    # --- Events List Rendering ---
    @app.callback(
        Output("events-list-container", "children"),
        Input("events-refresh-trigger", "data"),
        Input("events-ui-refresh-trigger", "data"),
        Input("main-tabs", "active_tab"),
        Input("event-order-store", "data"),
        Input("events-search-input", "value"),
        Input("events-hide-triggered-toggle", "value"),
        Input("events-sort-mode", "value"),
        State("selected-event-store", "data"),
    )
    def render_events_list(refresh_trigger, ui_refresh, active_tab, event_order, search_text, hide_triggered, sort_mode, selected_event):
        events = event_manager.get_all_events()
        if not events:
            return html.Div(
                html.P("No events yet.", className="text-muted"),
                className="text-center py-5"
            )

        # Apply ordering based on sort mode
        if sort_mode == "az":
            events = sorted(events, key=lambda e: (e.name or "").lower())
        else:
            # Manual: apply drag-and-drop order from store
            stored_order = event_order or []
            if stored_order:
                event_map = {e.name: e for e in events}
                ordered = [event_map[n] for n in stored_order if n in event_map]
                remaining = [e for e in events if e.name not in set(stored_order)]
                events = ordered + remaining

        # Filter: hide triggered events
        if hide_triggered:
            events = [e for e in events if e.status != "Triggered"]

        # Filter: search text (name or description, case-insensitive)
        query = (search_text or "").strip().lower()
        if query:
            events = [
                e for e in events
                if query in (e.name or "").lower() or query in (e.description or "").lower()
            ]

        if not events:
            return html.Div(
                html.P("No matching events.", className="text-muted"),
                className="text-center py-5"
            )

        is_manual = sort_mode != "az"
        cards = []
        for event in events:
            counts = event_manager.get_event_node_count(event.name)
            cards.append(build_event_card(
                event.name, event.description, event.status, counts,
                is_selected=(event.name == selected_event),
                trigger_date=event.trigger_date,
                trigger_nodes=event.trigger_nodes,
                trigger_mode=event.trigger_mode,
                show_drag_handle=is_manual,
            ))
        return cards

    # --- Autocomplete datalist for events search ---
    @app.callback(
        Output("events-search-datalist", "children"),
        Input("events-refresh-trigger", "data"),
        Input("main-tabs", "active_tab"),
    )
    def populate_events_search_datalist(refresh_trigger, active_tab):
        from dash import html as _html
        events = event_manager.get_all_events()
        return [_html.Option(value=e.name) for e in events]

    # --- Event Reordering (drag-and-drop) ---
    @app.callback(
        Output("event-order-store", "data"),
        Input("event-drag-order-input", "value"),
        prevent_initial_call=True,
    )
    def reorder_event(drag_order_json):
        import json as _json
        if drag_order_json:
            try:
                new_order = _json.loads(drag_order_json)
                if isinstance(new_order, list) and new_order:
                    return new_order
            except (ValueError, TypeError):
                pass
        return no_update

    # --- Populate trigger node dropdown when events tab opens ---
    @app.callback(
        Output("event-trigger-node", "options"),
        Input("main-tabs", "active_tab"),
        Input("events-refresh-trigger", "data"),
    )
    def populate_trigger_node_dropdown(active_tab, _refresh):
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name} for n in sorted(nodes, key=lambda n: n.name)]

    # --- Trigger mode hint text ---
    # Both trigger surfaces (event editor + dormant-node modal) share one
    # wording helper so they can't drift apart.
    @app.callback(
        Output("event-trigger-mode-hint", "children"),
        Input("event-trigger-mode", "value"),
        Input("event-trigger-node", "value"),
    )
    def describe_trigger_mode(trigger_mode, trigger_nodes):
        return _trigger_mode_hint(trigger_mode, trigger_nodes)

    @app.callback(
        Output("dormant-new-event-trigger-mode-hint", "children"),
        Input("dormant-new-event-trigger-mode", "value"),
        Input("dormant-new-event-trigger-node", "value"),
    )
    def describe_dormant_trigger_mode(trigger_mode, trigger_nodes):
        return _trigger_mode_hint(trigger_mode, trigger_nodes)

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

    # Outputs shared by create/select. Last output is `main-tabs.active_tab` so that
    # selecting/creating an event also switches to the Events tab (works from any tab).
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
        Output("event-trigger-mode", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
    ]
    _N_DETAIL = len(_DETAIL_OUTPUTS)

    # --- New Event ---
    @app.callback(
        *_DETAIL_OUTPUTS,
        Input("btn-new-event", "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def create_new_event(n_clicks, active_tab):
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
            [],                     # trigger nodes
            "any",                  # trigger mode
            "tab-events" if active_tab != "tab-events" else no_update,
        )

    # --- Close Event Detail ---
    @app.callback(
        *_DETAIL_OUTPUTS,
        Input("btn-event-close", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_event_detail(n_clicks):
        if not n_clicks:
            return (no_update,) * _N_DETAIL

        return (
            None,
            f"close-{time.time()}",
            {"display": "block"},
            {"display": "none"},
            "",
            "",
            "", "primary", _badge_hidden,
            [],
            {"display": "none"},
            "",
            "",
            "manual",
            [],
            "any",
            no_update,
        )

    # --- Event Selection ---
    @app.callback(
        *_DETAIL_OUTPUTS,
        Input({"type": "event-card", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def select_event(n_clicks_list, active_tab):
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
            list(event.trigger_nodes),
            event.trigger_mode or "any",
            "tab-events" if active_tab != "tab-events" else no_update,
        )

    # --- Event Context Menu (right-click on event card) ---
    @app.callback(
        *_DETAIL_OUTPUTS,
        Output("modal-confirm-trigger", "is_open", allow_duplicate=True),
        Output("modal-confirm-delete", "is_open", allow_duplicate=True),
        Input("event-ctx-action-input", "value"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def handle_event_context_action(action_value, active_tab):
        if not action_value:
            return (no_update,) * (_N_DETAIL + 2)
        parts = action_value.split("|")
        if len(parts) < 2:
            return (no_update,) * (_N_DETAIL + 2)
        event_name, action = parts[0], parts[1]
        event = event_manager.get_event(event_name)
        if not event:
            return (no_update,) * (_N_DETAIL + 2)

        event_nodes = event_manager.get_event_nodes(event_name)
        trigger_style = {"display": "none"} if event.status == "Triggered" else {
            "display": "flex", "alignItems": "center"
        }
        t_type = _event_trigger_type(event)

        detail = (
            event_name,
            f"ctx-{action}-{event_name}-{time.time()}",
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
            list(event.trigger_nodes),
            event.trigger_mode or "any",
            "tab-events" if active_tab != "tab-events" else no_update,
        )

        open_trigger = action == "trigger" and event.status != "Triggered"
        open_delete = action == "delete"
        return (*detail, open_trigger, open_delete)

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
        State("event-trigger-mode", "value"),
        prevent_initial_call=True,
    )
    def save_event(n_clicks, selected_event, name, description, trigger_type, trigger_date,
                   trigger_nodes, trigger_mode):
        if not n_clicks or not name or not name.strip():
            return no_update, no_update, "Event name is required.", no_update, no_update, no_update, no_update, no_update

        name = name.strip()
        description = (description or "").strip()

        # Resolve trigger fields based on type
        resolved_date = trigger_date if trigger_type == "date" else None
        resolved_nodes = _normalize_trigger_nodes(trigger_nodes) if trigger_type == "node" else []
        resolved_mode = trigger_mode if trigger_mode in ("any", "all") else "any"

        if trigger_type == "node" and not resolved_nodes:
            return (no_update, no_update, "Pick at least one trigger node.",
                    no_update, no_update, no_update, no_update, no_update)

        try:
            if selected_event is None:
                event_manager.add_event(Event(
                    name=name, description=description,
                    trigger_date=resolved_date, trigger_nodes=resolved_nodes,
                    trigger_mode=resolved_mode,
                ))
            else:
                existing = event_manager.get_event(selected_event)
                event_manager.update_event(selected_event, Event(
                    name=name, description=description,
                    status=existing.status if existing else "Pending",
                    trigger_date=resolved_date, trigger_nodes=resolved_nodes,
                    trigger_mode=resolved_mode,
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

    # The Trigger button was relocated to the Dormant Nodes header, but its
    # show/hide is still governed by event-trigger-section (hidden for new and
    # already-triggered events). Mirror that section's style onto the button's
    # wrapper so the four callbacks driving event-trigger-section need no change.
    @app.callback(
        Output("event-trigger-btn-wrapper", "style"),
        Input("event-trigger-section", "style"),
        prevent_initial_call=True,
    )
    def mirror_trigger_button_visibility(section_style):
        return section_style

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
        Output("pending-event-override-store", "data", allow_duplicate=True),
        Output("modal-override-conflict", "is_open", allow_duplicate=True),
        Output("override-conflict-body", "children", allow_duplicate=True),
        Output("override-store", "data", allow_duplicate=True),
        Output("override-conflict-mode-wrapper", "style", allow_duplicate=True),
        Input("btn-trigger-confirm", "n_clicks"),
        Input("btn-trigger-all-confirm", "n_clicks"),
        State("selected-event-store", "data"),
        State({"type": "dormant-node-select", "index": ALL}, "value"),
        State({"type": "dormant-node-select", "index": ALL}, "id"),
        State("manual-override-trigger-toggle", "value"),
        prevent_initial_call=True,
    )
    def trigger_event(checked_clicks, all_clicks, selected_event, checkbox_values, checkbox_ids, override_toggle):
        triggered = ctx.triggered_id
        if not triggered or not selected_event:
            return (no_update,) * 14

        if triggered == "btn-trigger-all-confirm":
            selected_nodes = None
        else:
            selected_nodes = [
                cb_id["index"]
                for cb_id, checked in zip(checkbox_ids, checkbox_values)
                if checked
            ] if checkbox_ids else []

        result = event_manager.trigger_event(selected_event, selected_nodes=selected_nodes)

        activated = list(result.get('activated', []))
        scheduled = list(result.get('scheduled', []))
        stored_intent = set(result.get('override_intent', []))
        pin_toggle_on = bool(override_toggle)

        # Candidates = stored intent ∪ (all triggered nodes if user ticked "Pin activated nodes")
        triggered_set = set(activated) | set(scheduled)
        if pin_toggle_on:
            candidates = sorted(triggered_set)
        else:
            candidates = sorted(triggered_set & stored_intent)

        override_store_update = no_update
        pending_store = no_update
        conflict_open = no_update
        conflict_body = no_update
        mode_wrapper_style = no_update

        if candidates:
            if ConfigManager.has_any_override_active():
                # Conflict — stash candidates, open modal. No override change yet.
                existing = ConfigManager.get_override()
                if existing.get("parent"):
                    current_desc = f'the node "{existing.get("parent")}"'
                else:
                    ev_nodes = ConfigManager.get_event_override_nodes()
                    current_desc = f"{len(ev_nodes)} event-pinned node(s): {', '.join(ev_nodes)}"
                cand_desc = ", ".join(candidates)
                conflict_body = (
                    f'Event "{selected_event}" activated {len(candidates)} node(s) configured '
                    f'for priority override: {cand_desc}. An override is already active for '
                    f'{current_desc}. Only one override can be active at a time — which do '
                    f'you want to keep?'
                )
                pending_store = {"event": selected_event, "candidates": candidates}
                conflict_open = True
                # Event-batch resolution ignores mode — hide the radio.
                mode_wrapper_style = {"display": "none"}
            else:
                ConfigManager.atomic_set_event_override(candidates, replace=False)
                import time as _t
                override_store_update = {"parent": None, "mode": "hard", "_t": _t.time()}

        event_nodes = event_manager.get_event_nodes(selected_event)
        msg_parts = []
        if activated:
            msg_parts.append(f"{len(activated)} node(s) activated")
        if scheduled:
            msg_parts.append(f"{len(scheduled)} node(s) scheduled")
        if candidates and conflict_open is not True:
            msg_parts.append(f"{len(candidates)} pinned to top of Next")
        elif candidates and conflict_open is True:
            msg_parts.append(f"{len(candidates)} override candidate(s) awaiting your choice")

        return (
            selected_event,
            f"trigger-{selected_event}",
            "Triggered", "success",
            {"display": "none"},
            build_dormant_nodes_table(event_nodes, "Triggered"),
            "Event triggered. " + (", ".join(msg_parts) if msg_parts else "No nodes selected."),
            False,
            "",
            pending_store,
            conflict_open,
            conflict_body,
            override_store_update,
            mode_wrapper_style,
        )

    # --- Open Dormant Node Modal ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-node-type", "options", allow_duplicate=True),
        Output("dormant-node-context", "options", allow_duplicate=True),
        Output("dormant-node-subcontext", "options", allow_duplicate=True),
        Output("dormant-node-name", "value", allow_duplicate=True),
        Output("dormant-node-desc", "value", allow_duplicate=True),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        Output("dormant-node-time-unit", "value", allow_duplicate=True),
        Output("dormant-node-needs-hard", "options", allow_duplicate=True),
        Output("dormant-node-needs-soft", "options", allow_duplicate=True),
        Output("dormant-node-supports-hard", "options", allow_duplicate=True),
        Output("dormant-node-supports-soft", "options", allow_duplicate=True),
        Output("dormant-node-helps", "options", allow_duplicate=True),
        Output("dormant-node-needs-hard", "value", allow_duplicate=True),
        Output("dormant-node-needs-soft", "value", allow_duplicate=True),
        Output("dormant-node-supports-hard", "value", allow_duplicate=True),
        Output("dormant-node-supports-soft", "value", allow_duplicate=True),
        Output("dormant-node-helps", "value", allow_duplicate=True),
        Output("dormant-node-time-mode", "value", allow_duplicate=True),
        Output("dormant-obsidian-links-store", "data", allow_duplicate=True),
        Output("dormant-drive-links-store", "data", allow_duplicate=True),
        Output("dormant-website-links-store", "data", allow_duplicate=True),
        Output("dormant-override-toggle", "value", allow_duplicate=True),
        Output("dormant-node-value-mode", "value", allow_duplicate=True),
        Output("dormant-node-value", "value", allow_duplicate=True),
        Output("dormant-node-interest", "value", allow_duplicate=True),
        Output("dormant-node-difficulty", "value", allow_duplicate=True),
        Output("dormant-node-time-o", "value", allow_duplicate=True),
        Output("dormant-node-time-m", "value", allow_duplicate=True),
        Output("dormant-node-time-p", "value", allow_duplicate=True),
        Output("dormant-node-delay-value", "value", allow_duplicate=True),
        Output("dormant-node-delay-unit", "value", allow_duplicate=True),
        Output("dormant-override-mode", "value", allow_duplicate=True),
        Output("editing-dormant-node-store", "data", allow_duplicate=True),
        Output("modal-dormant-node-title", "children", allow_duplicate=True),
        Output("btn-dormant-node-save", "children", allow_duplicate=True),
        # Habit-mode reset (7 new outputs)
        Output("dormant-node-time-habit-mode", "value", allow_duplicate=True),
        Output("dormant-node-habit-duration", "value", allow_duplicate=True),
        Output("dormant-node-habit-duration-unit", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-o", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-m", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-p", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-unit", "value", allow_duplicate=True),
        Output("dormant-node-habit-days", "value", allow_duplicate=True),
        # Mode toggle + existing-mode resets (8 new outputs)
        Output("dormant-node-mode", "value", allow_duplicate=True),
        Output("dormant-mode-toggle-wrapper", "style", allow_duplicate=True),
        Output("dormant-existing-picker", "options", allow_duplicate=True),
        Output("dormant-existing-picker", "value", allow_duplicate=True),
        Output("dormant-existing-event-picker", "options", allow_duplicate=True),
        Output("dormant-existing-event-picker", "value", allow_duplicate=True),
        Output("dormant-new-event-name", "value", allow_duplicate=True),
        Output("dormant-new-event-desc", "value", allow_duplicate=True),
        # New-event trigger-type resets (5 new outputs)
        Output("dormant-new-event-trigger-type", "value", allow_duplicate=True),
        Output("dormant-new-event-trigger-date", "value", allow_duplicate=True),
        Output("dormant-new-event-trigger-node", "options", allow_duplicate=True),
        Output("dormant-new-event-trigger-node", "value", allow_duplicate=True),
        Output("dormant-new-event-trigger-mode", "value", allow_duplicate=True),
        Input("btn-add-dormant-node", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_dormant_node_modal(n_clicks):
        if not n_clicks:
            return (no_update,) * 57

        types = ConfigManager.get_node_types()
        contexts = sort_contexts(ConfigManager.get_contexts())
        _ted = ConfigManager.get_time_estimate_defaults()
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": c, "value": c} for c in contexts]
        node_opts = [{"label": n.name, "value": n.name} for n in graph_manager.get_all_nodes()]
        existing_picker_opts = [{"label": n.name, "value": n.name}
                                for n in graph_manager.get_all_nodes() if not n.dormant]
        pending_event_opts = [{"label": e.name, "value": e.name}
                              for e in event_manager.get_all_events() if e.status == "Pending"]

        return (True, type_opts, ctx_opts, [{"label": "None", "value": ""}], "", "", "",
                _ted.get('unit', 'weeks'),
                node_opts, node_opts, node_opts, node_opts, node_opts,
                [], [], [], [], [],
                [],
                [''], [''], [''],
                [], [],
                5, 5, 5,
                _ted.get('optimistic', 2),
                _ted.get('expected', 4),
                _ted.get('pessimistic', 6),
                0, "days", "hard",
                None, "Add Dormant Node", "Add Node",
                # Habit reset
                [], 0, 'weeks', 0, 0, 0, 'min_per_session', [0, 1, 2, 3, 4, 5, 6],
                # Mode toggle + existing-mode resets
                "new", {"display": "block"},
                existing_picker_opts, [], pending_event_opts, None,
                "", "",
                # New-event trigger-type resets
                "manual", None, existing_picker_opts, [], "any")

    # --- Update Dormant Node Subcontexts ---
    @app.callback(
        Output("dormant-node-subcontext", "options"),
        Input("dormant-node-context", "value"),
    )
    def update_dormant_subcontexts(context):
        base = [{"label": "None", "value": ""}]
        if not context:
            return base
        subs = sort_subcontexts(ConfigManager.get_subcontexts().get(context, []))
        return base + [{"label": s, "value": s} for s in subs]

    # --- Dormant Node Modal: Aliases (mirrors the main node editor) ---
    @app.callback(
        Output("collapse-dormant-aliases", "is_open"),
        Input("btn-dormant-aliases-toggle", "n_clicks"),
        State("collapse-dormant-aliases", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_dormant_aliases(n, is_open):
        if n:
            return not is_open
        return is_open

    app.clientside_callback(
        "function(isOpen){ return 'editor-chevron' + (isOpen ? ' open' : ''); }",
        Output("dormant-aliases-chevron", "className"),
        Input("collapse-dormant-aliases", "is_open"),
    )

    @app.callback(
        Output("dormant-aliases-container", "children"),
        Input("dormant-aliases-store", "data"),
    )
    def render_dormant_aliases(aliases):
        return render_alias_rows(aliases, 'dormant-alias-input', 'btn-dormant-alias-remove')

    @app.callback(
        [Output("dormant-aliases-store", "data", allow_duplicate=True),
         Output("collapse-dormant-aliases", "is_open", allow_duplicate=True)],
        [Input("btn-dormant-alias-add", "n_clicks"),
         Input({"type": "btn-dormant-alias-remove", "index": ALL}, "n_clicks")],
        [State({"type": "dormant-alias-input", "index": ALL}, "value"),
         State("dormant-aliases-store", "data")],
        prevent_initial_call=True,
    )
    def modify_dormant_aliases(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        aliases = list(current_values) if current_values else list(store_data or [''])
        collapse_update = no_update
        if trigger == "btn-dormant-alias-add":
            aliases.append('')
        elif isinstance(trigger, dict) and trigger.get("type") == "btn-dormant-alias-remove":
            idx = trigger["index"]
            if 0 <= idx < len(aliases):
                aliases.pop(idx)
                if not aliases:
                    collapse_update = False
        return aliases, collapse_update

    # Load aliases when the modal opens: existing node's aliases on edit, a
    # single blank row for a fresh add. Keyed off the editing-store (set by both
    # the open-new and edit-populate callbacks) so it stays decoupled from those
    # large multi-output callbacks.
    @app.callback(
        Output("dormant-aliases-store", "data", allow_duplicate=True),
        Input("modal-dormant-node", "is_open"),
        State("editing-dormant-node-store", "data"),
        prevent_initial_call=True,
    )
    def load_dormant_aliases(is_open, editing_name):
        if not is_open:
            return no_update
        if editing_name:
            return graph_manager.get_aliases(editing_name) or ['']
        return ['']

    # --- Dormant Node Modal: Mode toggles control OMP / Habit visibility ---
    @app.callback(
        Output("dormant-node-time-omp", "style"),
        Output("section-dormant-node-time-habit", "style"),
        Input("dormant-node-time-mode", "value"),
        Input("dormant-node-time-habit-mode", "value"),
        prevent_initial_call=True,
    )
    def toggle_dormant_time_mode(inherit_val, habit_val):
        inherit_on = bool(inherit_val and "inherited" in inherit_val)
        habit_on = bool(habit_val and "habit" in habit_val)
        if inherit_on:
            return {"display": "none"}, {"display": "none"}
        if habit_on:
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # --- Dormant Node Modal: Habit / Inherit mutual exclusivity ---
    @app.callback(
        Output("dormant-node-time-mode", "value", allow_duplicate=True),
        Output("dormant-node-time-habit-mode", "value", allow_duplicate=True),
        Input("dormant-node-time-mode", "value"),
        Input("dormant-node-time-habit-mode", "value"),
        prevent_initial_call=True,
    )
    def enforce_dormant_time_exclusivity(inherit_val, habit_val):
        trig = ctx.triggered_id
        if trig == "dormant-node-time-mode" and inherit_val and "inherited" in inherit_val:
            return inherit_val, []
        if trig == "dormant-node-time-habit-mode" and habit_val and "habit" in habit_val:
            return [], habit_val
        return inherit_val, habit_val

    # --- Dormant Node Modal: Inherit-ratings toggle hides/shows V/I/E sliders ---
    # Mirrors the main node editor (callbacks.py). Clientside to avoid a flash.
    app.clientside_callback(
        """
        function(value_mode_val) {
            if (value_mode_val && value_mode_val.indexOf('inherited') >= 0) {
                return {display: 'none'};
            }
            return {display: 'block'};
        }
        """,
        Output("section-dormant-ratings", "style"),
        Input("dormant-node-value-mode", "value"),
        prevent_initial_call=True,
    )

    # --- Dormant Node Modal: Hide Effort slider on Goals; show caption ---
    app.clientside_callback(
        """
        function(node_type) {
            if (node_type === 'Goal') return [{display: 'none'}, {}];
            return [{}, {display: 'none'}];
        }
        """,
        Output("dormant-node-effort-row", "style"),
        Output("dormant-node-effort-caption", "style"),
        Input("dormant-node-type", "value"),
    )

    # --- Dormant Node Modal: Lock Inherit-value ON for Milestones ---
    # Milestones are transparent checkpoints: their own value never enters
    # scoring. Force the value toggle ON and warn if the user tries to clear
    # it — the symmetric partner to the Goal/Milestone time lock in the main
    # editor (callbacks.py). Goals are NOT locked: they carry their own value.
    app.clientside_callback(
        """
        function(value_mode_val, node_type) {
            var no_update = window.dash_clientside.no_update;
            var hidden = {display: "none"};
            var visible = {display: "block", color: "#dc3545", fontSize: "0.85rem"};
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
            var only_value_mode = ids.length === 1 && ids[0] === 'dormant-node-value-mode';

            if (node_type !== 'Milestone') {
                return [no_update, hidden, ""];
            }
            var inherited_on = !!(value_mode_val && value_mode_val.indexOf('inherited') >= 0);
            if (inherited_on) {
                if (only_value_mode) return [no_update, no_update, no_update];
                return [no_update, hidden, ""];
            }
            var msg = "Inherit is required for Milestone nodes — they are " +
                      "checkpoints, so their own ratings don't affect scoring.";
            if (only_value_mode) return [['inherited'], visible, msg];
            return [['inherited'], hidden, ""];
        }
        """,
        Output('dormant-node-value-mode', 'value', allow_duplicate=True),
        Output('dormant-value-mode-warning', 'style'),
        Output('dormant-value-mode-warning', 'children'),
        Input('dormant-node-value-mode', 'value'),
        Input('dormant-node-type', 'value'),
        prevent_initial_call=True,
    )

    # --- Dormant Node Modal: Live total-hours preview for habit ---
    @app.callback(
        Output("dormant-node-habit-total-preview", "children"),
        Input("dormant-node-habit-duration", "value"),
        Input("dormant-node-habit-duration-unit", "value"),
        Input("dormant-node-habit-intensity-m", "value"),
        Input("dormant-node-habit-intensity-unit", "value"),
        Input("dormant-node-habit-days", "value"),
    )
    def update_dormant_habit_preview(duration, dur_unit, intensity_m, int_unit, days):
        return habit_preview_text(duration, dur_unit, intensity_m, int_unit, days)

    # --- Dormant Node Modal: Mode toggle (New / Existing) visibility ---
    @app.callback(
        Output("dormant-mode-new-fields", "style"),
        Output("dormant-mode-existing-fields", "style"),
        Input("dormant-node-mode", "value"),
    )
    def toggle_dormant_mode_fields(mode):
        if mode == "existing":
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # --- Dormant Node Modal: Event-target sub-section visibility ---
    # Only shown when in "existing" mode AND no event is currently selected.
    @app.callback(
        Output("dormant-event-target-wrapper", "style"),
        Input("dormant-node-mode", "value"),
        Input("selected-event-store", "data"),
    )
    def toggle_dormant_event_target_wrapper(mode, selected_event):
        if mode == "existing" and not selected_event:
            return {"display": "block"}
        return {"display": "none"}

    # --- Dormant Node Modal: New-event vs Existing-event sub-sections ---
    @app.callback(
        Output("dormant-new-event-section", "style"),
        Output("dormant-existing-event-section", "style"),
        Input("dormant-event-target-mode", "value"),
    )
    def toggle_dormant_event_target_section(target_mode):
        if target_mode == "existing":
            return {"display": "none"}, {"display": "block"}
        return {"display": "block"}, {"display": "none"}

    # --- Dormant Node Modal: New event trigger-type sub-sections ---
    @app.callback(
        Output("dormant-new-event-date-section", "style"),
        Output("dormant-new-event-node-section", "style"),
        Input("dormant-new-event-trigger-type", "value"),
    )
    def toggle_dormant_new_event_trigger_sections(trigger_type):
        date_style = {"display": "block"} if trigger_type == "date" else {"display": "none"}
        node_style = {"display": "block"} if trigger_type == "node" else {"display": "none"}
        return date_style, node_style

    # --- Open Dormant Node Modal from canvas (Add to event…) ---
    # Triggered by context_menu.js writing JSON node IDs to dormant-existing-trigger-input.
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-node-mode", "value", allow_duplicate=True),
        Output("dormant-mode-toggle-wrapper", "style", allow_duplicate=True),
        Output("dormant-existing-picker", "options", allow_duplicate=True),
        Output("dormant-existing-picker", "value", allow_duplicate=True),
        Output("dormant-existing-event-picker", "options", allow_duplicate=True),
        Output("dormant-existing-event-picker", "value", allow_duplicate=True),
        Output("dormant-event-target-mode", "value", allow_duplicate=True),
        Output("dormant-new-event-name", "value", allow_duplicate=True),
        Output("dormant-new-event-desc", "value", allow_duplicate=True),
        Output("dormant-node-delay-value", "value", allow_duplicate=True),
        Output("dormant-node-delay-unit", "value", allow_duplicate=True),
        Output("dormant-override-toggle", "value", allow_duplicate=True),
        Output("dormant-override-mode", "value", allow_duplicate=True),
        Output("editing-dormant-node-store", "data", allow_duplicate=True),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        Output("modal-dormant-node-title", "children", allow_duplicate=True),
        Output("btn-dormant-node-save", "children", allow_duplicate=True),
        # New-event trigger-type resets (5 new outputs)
        Output("dormant-new-event-trigger-type", "value", allow_duplicate=True),
        Output("dormant-new-event-trigger-date", "value", allow_duplicate=True),
        Output("dormant-new-event-trigger-node", "options", allow_duplicate=True),
        Output("dormant-new-event-trigger-node", "value", allow_duplicate=True),
        Output("dormant-new-event-trigger-mode", "value", allow_duplicate=True),
        # Clear any sticky event selection so each canvas trigger forces an
        # explicit new/existing event choice in the modal. Without this, the
        # event_target_wrapper stays hidden after a previous save and the user
        # silently keeps adding nodes to whichever event was most recent.
        Output("selected-event-store", "data", allow_duplicate=True),
        Input("dormant-existing-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def open_modal_for_existing_nodes(trigger_val):
        _N = 24
        if not trigger_val:
            return (no_update,) * _N
        try:
            json_part = trigger_val.split("|")[0]
            node_ids = json.loads(json_part)
            if not isinstance(node_ids, list):
                return (no_update,) * _N
        except (ValueError, json.JSONDecodeError):
            return (no_update,) * _N

        existing_picker_opts = [{"label": n.name, "value": n.name}
                                for n in graph_manager.get_all_nodes() if not n.dormant]
        valid_names = {opt["value"] for opt in existing_picker_opts}
        valid_ids = [nid for nid in node_ids if nid in valid_names]

        pending_event_opts = [{"label": e.name, "value": e.name}
                              for e in event_manager.get_all_events() if e.status == "Pending"]

        return (
            True,                               # modal is_open
            "existing",                         # mode
            {"display": "block"},               # toggle wrapper visible
            existing_picker_opts,               # picker options
            valid_ids,                          # picker pre-fill
            pending_event_opts,                 # existing-event-picker options
            None,                               # existing-event-picker value
            "new",                              # event-target-mode default
            "",                                 # new-event-name
            "",                                 # new-event-desc
            0,                                  # delay-value
            "days",                             # delay-unit
            [],                                 # override-toggle (checklist list)
            "hard",                             # override-mode
            None,                               # editing store cleared
            "",                                 # save status cleared
            "Add to Event",                     # title
            "Add to Event",                     # save button text
            # New-event trigger-type resets
            "manual",                           # trigger-type default
            None,                               # trigger-date cleared
            existing_picker_opts,               # trigger-node options
            [],                                 # trigger-node value
            "any",                              # trigger-mode default
            None,                               # selected-event-store cleared
        )

    # --- Cancel Dormant Node Modal ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("editing-dormant-node-store", "data", allow_duplicate=True),
        Input("btn-dormant-node-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_dormant_node_modal(n_clicks):
        if n_clicks:
            return False, None
        return no_update, no_update

    # --- Editor Dormant Toggle: populate switch + "In event: X" line ---
    # Re-runs whenever the loaded node changes OR something dormant-related
    # might have happened (events-refresh, modal close). The DB is the SSOT;
    # the toggle never holds a value the DB doesn't agree with.
    @app.callback(
        Output("node-dormant", "value"),
        Output("node-dormant-event-info", "children"),
        Input("node-original-name", "data"),
        Input("events-refresh-trigger", "data"),
        Input("modal-dormant-node", "is_open"),
        Input("modal-dormant-deactivate-confirm", "is_open"),
    )
    def populate_node_dormant_state(node_name, _refresh, dormant_modal_open,
                                    deactivate_modal_open):
        # Only sync after a modal closes — opening shouldn't reset the user's
        # in-progress toggle click before the modal flow has a chance to save.
        trig = ctx.triggered_id
        if trig == "modal-dormant-node" and dormant_modal_open:
            return no_update, no_update
        if trig == "modal-dormant-deactivate-confirm" and deactivate_modal_open:
            return no_update, no_update

        if not node_name:
            return [], ""
        node = graph_manager.get_node(node_name)
        if not node:
            return [], ""

        toggle_val = ["dormant"] if node.dormant else []
        if node.dormant:
            events = event_manager.get_events_for_node(node_name)
            if events:
                info = f"In event: {', '.join(events)}"
            else:
                info = "Dormant (not linked to any event)"
        else:
            info = ""
        return toggle_val, info

    # --- Editor Dormant Toggle: dispatcher ---
    # Compares the toggle's new value to the loaded node's actual dormant
    # state. On a real transition, opens the appropriate modal (Add-to-Event
    # for ON, confirm for OFF) without touching the DB. The DB change happens
    # inside those modal flows; populate_node_dormant_state syncs the switch
    # back when they close.
    @app.callback(
        Output("dormant-existing-trigger-input", "value", allow_duplicate=True),
        Output("modal-dormant-deactivate-confirm", "is_open", allow_duplicate=True),
        Output("dormant-deactivate-confirm-body", "children"),
        Output("pending-dormant-toggle-store", "data"),
        Input("node-dormant", "value"),
        State("node-original-name", "data"),
        prevent_initial_call=True,
    )
    def dispatch_dormant_toggle(toggle_val, node_name):
        if not node_name:
            return no_update, no_update, no_update, no_update
        node = graph_manager.get_node(node_name)
        if not node:
            return no_update, no_update, no_update, no_update

        wants_dormant = bool(toggle_val and "dormant" in toggle_val)
        is_dormant = bool(node.dormant)

        if wants_dormant == is_dormant:
            # Toggle matches DB — this fire was the populate sync, not a user click.
            return no_update, no_update, no_update, no_update

        if wants_dormant and not is_dormant:
            # Make-dormant: open Add-to-Event modal pre-filled with this node.
            payload = json.dumps([node_name]) + "|" + str(int(time.time() * 1000))
            return payload, no_update, no_update, node_name

        # Wake: open confirm modal.
        events = event_manager.get_events_for_node(node_name)
        if events:
            body = f"Remove '{node_name}' from event{'s' if len(events) != 1 else ''} '{', '.join(events)}' and wake it?"
        else:
            body = f"'{node_name}' is dormant but not linked to any event. Wake it?"
        return no_update, True, body, node_name

    # --- Editor Dormant Toggle: confirm wake ---
    @app.callback(
        Output("modal-dormant-deactivate-confirm", "is_open", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("pending-dormant-toggle-store", "data", allow_duplicate=True),
        Input("btn-dormant-deactivate-confirm", "n_clicks"),
        State("pending-dormant-toggle-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_wake(n_clicks, pending_node):
        if not n_clicks or not pending_node:
            return no_update, no_update, no_update
        try:
            event_manager.detach_node_from_all_events(pending_node)
        except Exception as e:
            # Don't leave the modal open on error; surface via save-output channel.
            return False, no_update, None
        return False, f"detach-{pending_node}-{int(time.time())}", None

    # --- Editor Dormant Toggle: cancel wake ---
    # Just closes the modal; populate_node_dormant_state will re-sync the
    # toggle to the DB's actual (still-dormant) state.
    @app.callback(
        Output("modal-dormant-deactivate-confirm", "is_open", allow_duplicate=True),
        Output("pending-dormant-toggle-store", "data", allow_duplicate=True),
        Input("btn-dormant-deactivate-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_wake(n_clicks):
        if not n_clicks:
            return no_update, no_update
        return False, None

    # --- Save Dormant Node ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("event-trigger-section", "style", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Output("editing-dormant-node-store", "data", allow_duplicate=True),
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
        State("dormant-node-time-unit", "value"),
        State("dormant-node-time-mode", "value"),
        # Habit-mode states
        State("dormant-node-time-habit-mode", "value"),
        State("dormant-node-habit-duration", "value"),
        State("dormant-node-habit-duration-unit", "value"),
        State("dormant-node-habit-intensity-o", "value"),
        State("dormant-node-habit-intensity-m", "value"),
        State("dormant-node-habit-intensity-p", "value"),
        State("dormant-node-habit-intensity-unit", "value"),
        State("dormant-node-habit-days", "value"),
        State("dormant-node-delay-value", "value"),
        State("dormant-node-delay-unit", "value"),
        State("dormant-node-needs-hard", "value"),
        State("dormant-node-needs-soft", "value"),
        State("dormant-node-supports-hard", "value"),
        State("dormant-node-supports-soft", "value"),
        State("dormant-node-helps", "value"),
        State({"type": "dormant-obsidian-link", "index": ALL}, "value"),
        State({"type": "dormant-drive-link", "index": ALL}, "value"),
        State({"type": "dormant-website-link", "index": ALL}, "value"),
        # Override
        State("dormant-override-toggle", "value"),
        State("dormant-override-mode", "value"),
        # Value-inherit toggle (Inherit ratings)
        State("dormant-node-value-mode", "value"),
        State("editing-dormant-node-store", "data"),
        # Mode + existing-mode states
        State("dormant-node-mode", "value"),
        State("dormant-existing-picker", "value"),
        State("dormant-event-target-mode", "value"),
        State("dormant-new-event-name", "value"),
        State("dormant-new-event-desc", "value"),
        State("dormant-existing-event-picker", "value"),
        # New-event trigger info (used when creating an event via the modal)
        State("dormant-new-event-trigger-type", "value"),
        State("dormant-new-event-trigger-date", "value"),
        State("dormant-new-event-trigger-node", "value"),
        State("dormant-new-event-trigger-mode", "value"),
        State({"type": "dormant-alias-input", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_dormant_node(n_clicks, selected_event,
                          event_name_val, event_desc_val, event_date_val,
                          name, node_type, context, subcontext, desc,
                          value, interest, difficulty, time_o, time_m, time_p, time_unit,
                          time_mode_val,
                          time_habit_mode_val,
                          habit_duration, habit_duration_unit,
                          habit_int_o, habit_int_m, habit_int_p, habit_int_unit,
                          habit_days,
                          delay_value, delay_unit,
                          needs_hard, needs_soft, supports_hard, supports_soft, helps,
                          obsidian_vals, drive_vals, website_vals,
                          override_toggle, override_mode,
                          value_mode_val,
                          editing_original_name,
                          mode, existing_picker_vals,
                          event_target_mode, new_event_name, new_event_desc,
                          existing_event_pick,
                          new_event_trigger_type, new_event_trigger_date,
                          new_event_trigger_node, new_event_trigger_mode, alias_values):
        _nu8 = (no_update,) * 8
        if not n_clicks:
            return _nu8

        # Override toggle is now a switch-style Checklist (value is a list like
        # ["on"]) to match the main editor — normalize to a bool for the
        # event-manager calls below.
        override_toggle = bool(override_toggle and "on" in override_toggle)

        is_edit = bool(editing_original_name)

        # --- Existing-nodes bulk conversion path ---
        if mode == "existing" and not is_edit:
            picker_vals = [v for v in (existing_picker_vals or []) if v]
            if not picker_vals:
                return no_update, "Select at least one node.", no_update, no_update, no_update, no_update, no_update, no_update

            target_event = selected_event
            event_status_msg = no_update
            event_trigger_style = no_update
            if not target_event:
                if event_target_mode == "existing":
                    if not existing_event_pick:
                        return no_update, "Pick an existing event.", no_update, no_update, no_update, no_update, no_update, no_update
                    target_event = existing_event_pick
                else:
                    ev_name = (new_event_name or "").strip()
                    if not ev_name:
                        return no_update, "Enter a name for the new event.", no_update, no_update, no_update, no_update, no_update, no_update
                    ev_desc = (new_event_desc or "").strip()
                    # Trigger type is "manual" by default; only forward date /
                    # node when explicitly selected, so leftover values in the
                    # other field don't get persisted.
                    trig_type = new_event_trigger_type or "manual"
                    resolved_date = new_event_trigger_date if trig_type == "date" else None
                    resolved_trigger_nodes = (
                        _normalize_trigger_nodes(new_event_trigger_node)
                        if trig_type == "node" else []
                    )
                    resolved_trigger_mode = (
                        new_event_trigger_mode if new_event_trigger_mode in ("any", "all") else "any"
                    )
                    try:
                        event_manager.add_event(Event(
                            name=ev_name,
                            description=ev_desc,
                            trigger_date=resolved_date,
                            trigger_nodes=resolved_trigger_nodes,
                            trigger_mode=resolved_trigger_mode,
                        ))
                    except ValueError as e:
                        return no_update, str(e), no_update, no_update, no_update, no_update, no_update, no_update
                    target_event = ev_name
                    event_status_msg = "Event auto-saved."
                    event_trigger_style = {"display": "flex", "alignItems": "center"}

            delay_value_int = int(delay_value or 0)
            if delay_unit == "weeks":
                delay_days_val = delay_value_int * 7
            elif delay_unit == "months":
                delay_days_val = delay_value_int * 30
            elif delay_unit == "years":
                delay_days_val = delay_value_int * 365
            else:
                delay_days_val = delay_value_int

            # Skip nodes already linked to this event (idempotent re-adds would
            # create duplicate EventNodes rows and break the composite index).
            already_linked = {
                en['node'].name for en in event_manager.get_event_nodes(target_event)
            }
            existing_nodes = {n.name for n in graph_manager.get_all_nodes(include_dormant=True)}

            added = 0
            for node_name in picker_vals:
                if node_name in already_linked:
                    continue
                if node_name not in existing_nodes:
                    continue
                event_manager.add_node_to_event(
                    target_event, node_name, delay_days_val,
                    override_on_trigger=bool(override_toggle),
                    override_mode=(override_mode or "hard") if override_toggle else None,
                )
                added += 1

            event = event_manager.get_event(target_event)
            event_nodes = event_manager.get_event_nodes(target_event)
            return (
                False,
                "",
                build_dormant_nodes_table(event_nodes, event.status if event else "Pending"),
                f"add-existing-{target_event}-{added}-{int(time.time())}",
                target_event,
                event_trigger_style,
                event_status_msg,
                None,
            )

        # --- New-node single path (existing behavior) ---
        if not name or not name.strip():
            return no_update, "Node name is required.", no_update, no_update, no_update, no_update, no_update, no_update

        event_status_msg = no_update
        event_trigger_style = no_update

        if is_edit:
            if not selected_event:
                return no_update, "Internal error: no event context for edit.", no_update, no_update, no_update, no_update, no_update, no_update
        else:
            if not selected_event:
                ev_name = (event_name_val or "").strip()
                if not ev_name:
                    return no_update, "Enter an event name first, then add nodes.", no_update, no_update, no_update, no_update, no_update, no_update
                ev_desc = (event_desc_val or "").strip()
                ev_date = event_date_val or None
                try:
                    event_manager.add_event(Event(name=ev_name, description=ev_desc, trigger_date=ev_date))
                except ValueError as e:
                    return no_update, str(e), no_update, no_update, no_update, no_update, no_update, no_update
                selected_event = ev_name
                event_status_msg = "Event auto-saved."
                event_trigger_style = {"display": "flex", "alignItems": "center"}

        name = name.strip()
        delay_value = int(delay_value or 0)
        if delay_unit == "weeks":
            delay_days = delay_value * 7
        elif delay_unit == "months":
            delay_days = delay_value * 30
        elif delay_unit == "years":
            delay_days = delay_value * 365
        else:
            delay_days = delay_value

        multiplier = ConfigManager.get_time_multiplier(time_unit)
        # Resolve time_mode via the shared helper — Goal/Milestone always
        # inherit; otherwise habit > inherited > manual.
        t_mode = resolve_time_mode(node_type or "Learn", time_mode_val, time_habit_mode_val)
        if t_mode == 'habit':
            t_o, t_m, t_p = compute_habit_time_omp(
                habit_duration or 0, habit_duration_unit or 'weeks',
                habit_int_o or 0, habit_int_m or 0, habit_int_p or 0,
                habit_int_unit or 'min_per_session', habit_days,
            )
        else:
            t_o = float(time_o or 0) * multiplier
            t_m = float(time_m or 0) * multiplier
            t_p = float(time_p or 0) * multiplier
        # Mirror time_mode — Milestones always inherit value; Goals keep their
        # own; otherwise the toggle wins.
        v_mode = resolve_value_mode(node_type or "Learn", value_mode_val)

        node = Node(
            name=name,
            type=node_type or "Learn",
            description=desc or "",
            value=value or 5,
            time_o=t_o,
            time_m=t_m,
            time_p=t_p,
            interest=interest or 5,
            difficulty=difficulty or 5,
            status=STATUS_OPEN,
            context=context or None,
            subcontext=(subcontext or '').strip() or None,
            obsidian_path=serialize_links(obsidian_vals) or None,
            google_drive_path=serialize_links(drive_vals) or None,
            website=serialize_links(website_vals) or None,
            time_mode=t_mode,
            value_mode=v_mode,
            habit_duration=habit_duration or 0,
            habit_duration_unit=habit_duration_unit or 'weeks',
            habit_intensity_o=habit_int_o or 0,
            habit_intensity_m=habit_int_m or 0,
            habit_intensity_p=habit_int_p or 0,
            habit_intensity_unit=habit_int_unit or 'min_per_session',
            **({'habit_days': habit_days} if habit_days is not None else {}),
        )

        if is_edit:
            try:
                event_manager.update_dormant_node(
                    selected_event, editing_original_name, node,
                    delay_days=delay_days,
                    override_on_trigger=bool(override_toggle),
                    override_mode=(override_mode or "hard") if override_toggle else None,
                )
            except ValueError as e:
                return no_update, str(e), no_update, no_update, no_update, no_update, no_update, no_update
        else:
            try:
                event_manager.create_dormant_node(
                    node, selected_event, delay_days=delay_days,
                    override_on_trigger=bool(override_toggle),
                    override_mode=(override_mode or "hard") if override_toggle else None,
                )
            except ValueError as e:
                return no_update, str(e), no_update, no_update, selected_event, event_trigger_style, event_status_msg, no_update

        graph_manager.set_aliases(
            node.name, [a for a in (alias_values or []) if a and a.strip()])

        graph_manager.sync_edges(node.name, needs_hard or [], needs_soft or [],
                                 supports_hard or [], supports_soft or [], helps or [])

        event = event_manager.get_event(selected_event)
        event_nodes = event_manager.get_event_nodes(selected_event)

        return (
            False,
            "",
            build_dormant_nodes_table(event_nodes, event.status if event else "Pending"),
            f"{'edit' if is_edit else 'add'}-node-{node.name}",
            selected_event,
            event_trigger_style,
            event_status_msg,
            None,
        )

    # --- Dormant Node Override toggle visibility ---
    @app.callback(
        Output("dormant-override-options", "style"),
        Input("dormant-override-toggle", "value"),
        prevent_initial_call=True,
    )
    def toggle_dormant_override_options(on):
        # Checklist value is a list (e.g. ["on"]); show options when non-empty.
        return {"display": "block"} if (on and "on" in on) else {"display": "none"}

    # --- Dormant Node Link Render Callbacks ---
    @app.callback(
        Output('dormant-obsidian-links-container', 'children'),
        Input('dormant-obsidian-links-store', 'data'),
    )
    def render_dormant_obsidian_links(links):
        return render_link_rows(links, 'dormant-obsidian-link', has_browse=True, has_open=False)

    @app.callback(
        Output('dormant-drive-links-container', 'children'),
        Input('dormant-drive-links-store', 'data'),
    )
    def render_dormant_drive_links(links):
        return render_link_rows(strip_gdrive_prefix(links), 'dormant-drive-link', has_browse=True, has_open=False)

    @app.callback(
        Output('dormant-website-links-container', 'children'),
        Input('dormant-website-links-store', 'data'),
    )
    def render_dormant_website_links(links):
        return render_link_rows(links, 'dormant-website-link', has_browse=False, has_open=False)

    # --- Dormant Node Link Modify Callbacks ---
    @app.callback(
        Output('dormant-obsidian-links-store', 'data', allow_duplicate=True),
        [Input('btn-dormant-obsidian-add', 'n_clicks'),
         Input({'type': 'btn-dormant-obsidian-link-remove', 'index': ALL}, 'n_clicks'),
         Input({'type': 'btn-dormant-obsidian-browse', 'index': ALL}, 'n_clicks')],
        [State({'type': 'dormant-obsidian-link', 'index': ALL}, 'value'),
         State('dormant-obsidian-links-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_dormant_obsidian_links(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-dormant-obsidian-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-dormant-obsidian-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-dormant-obsidian-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return no_update
                vault = ConfigManager.get_obsidian_vault()
                import os
                abs_path = spawn_local_file_picker(
                    initial_dir=vault,
                    title="Select Obsidian File",
                    filetypes_list=[("Markdown files", "*.md"), ("All files", "*.*")]
                )
                if abs_path:
                    vault_norm = os.path.normpath(vault)
                    if abs_path.startswith(vault_norm):
                        rel = abs_path[len(vault_norm):].lstrip(os.sep)
                    else:
                        rel = abs_path
                    if 0 <= idx < len(links):
                        links[idx] = rel
                else:
                    return no_update
        return links

    @app.callback(
        Output('dormant-drive-links-store', 'data', allow_duplicate=True),
        [Input('btn-dormant-drive-add', 'n_clicks'),
         Input({'type': 'btn-dormant-drive-link-remove', 'index': ALL}, 'n_clicks'),
         Input({'type': 'btn-dormant-drive-browse', 'index': ALL}, 'n_clicks')],
        [State({'type': 'dormant-drive-link', 'index': ALL}, 'value'),
         State('dormant-drive-links-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_dormant_drive_links(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-dormant-drive-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-dormant-drive-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-dormant-drive-browse':
                idx = trigger['index']
                if not any(browse_clicks):
                    return no_update
                abs_path = spawn_local_file_picker(
                    initial_dir=ConfigManager.get_gdrive_path() or '',
                    title="Select Google Drive File",
                    filetypes_list=[("All files", "*.*")]
                )
                if abs_path:
                    if 0 <= idx < len(links):
                        links[idx] = abs_path
                else:
                    return no_update
        return links

    @app.callback(
        Output('dormant-website-links-store', 'data', allow_duplicate=True),
        [Input('btn-dormant-website-add', 'n_clicks'),
         Input({'type': 'btn-dormant-website-link-remove', 'index': ALL}, 'n_clicks')],
        [State({'type': 'dormant-website-link', 'index': ALL}, 'value'),
         State('dormant-website-links-store', 'data')],
        prevent_initial_call=True,
    )
    def modify_dormant_website_links(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-dormant-website-add':
            links.append('')
        elif isinstance(trigger, dict) and trigger.get('type') == 'btn-dormant-website-link-remove':
            idx = trigger['index']
            if 0 <= idx < len(links) and len(links) > 1:
                links.pop(idx)
        return links

    # --- Edit Dormant Node → Open Dormant Node modal pre-filled ---
    @app.callback(
        Output("modal-dormant-node", "is_open", allow_duplicate=True),
        Output("editing-dormant-node-store", "data", allow_duplicate=True),
        Output("modal-dormant-node-title", "children", allow_duplicate=True),
        Output("btn-dormant-node-save", "children", allow_duplicate=True),
        Output("dormant-node-name", "value", allow_duplicate=True),
        Output("dormant-node-type", "value", allow_duplicate=True),
        Output("dormant-node-type", "options", allow_duplicate=True),
        Output("dormant-node-context", "value", allow_duplicate=True),
        Output("dormant-node-context", "options", allow_duplicate=True),
        Output("dormant-node-subcontext", "value", allow_duplicate=True),
        Output("dormant-node-subcontext", "options", allow_duplicate=True),
        Output("dormant-node-desc", "value", allow_duplicate=True),
        Output("dormant-node-value-mode", "value", allow_duplicate=True),
        Output("dormant-node-value", "value", allow_duplicate=True),
        Output("dormant-node-interest", "value", allow_duplicate=True),
        Output("dormant-node-difficulty", "value", allow_duplicate=True),
        Output("dormant-node-time-o", "value", allow_duplicate=True),
        Output("dormant-node-time-m", "value", allow_duplicate=True),
        Output("dormant-node-time-p", "value", allow_duplicate=True),
        Output("dormant-node-time-unit", "value", allow_duplicate=True),
        Output("dormant-node-time-mode", "value", allow_duplicate=True),
        Output("dormant-node-delay-value", "value", allow_duplicate=True),
        Output("dormant-node-delay-unit", "value", allow_duplicate=True),
        Output("dormant-node-needs-hard", "value", allow_duplicate=True),
        Output("dormant-node-needs-hard", "options", allow_duplicate=True),
        Output("dormant-node-needs-soft", "value", allow_duplicate=True),
        Output("dormant-node-needs-soft", "options", allow_duplicate=True),
        Output("dormant-node-supports-hard", "value", allow_duplicate=True),
        Output("dormant-node-supports-hard", "options", allow_duplicate=True),
        Output("dormant-node-supports-soft", "value", allow_duplicate=True),
        Output("dormant-node-supports-soft", "options", allow_duplicate=True),
        Output("dormant-node-helps", "value", allow_duplicate=True),
        Output("dormant-node-helps", "options", allow_duplicate=True),
        Output("dormant-obsidian-links-store", "data", allow_duplicate=True),
        Output("dormant-drive-links-store", "data", allow_duplicate=True),
        Output("dormant-website-links-store", "data", allow_duplicate=True),
        Output("dormant-override-toggle", "value", allow_duplicate=True),
        Output("dormant-override-mode", "value", allow_duplicate=True),
        Output("dormant-node-save-status", "children", allow_duplicate=True),
        # Habit-mode pre-fill (7 new outputs)
        Output("dormant-node-time-habit-mode", "value", allow_duplicate=True),
        Output("dormant-node-habit-duration", "value", allow_duplicate=True),
        Output("dormant-node-habit-duration-unit", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-o", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-m", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-p", "value", allow_duplicate=True),
        Output("dormant-node-habit-intensity-unit", "value", allow_duplicate=True),
        Output("dormant-node-habit-days", "value", allow_duplicate=True),
        # Mode-toggle wrapper hidden during edit (single-node only)
        Output("dormant-mode-toggle-wrapper", "style", allow_duplicate=True),
        Output("dormant-node-mode", "value", allow_duplicate=True),
        Input({"type": "btn-edit-dormant-node", "index": ALL}, "n_clicks"),
        Input("dormant-edit-trigger-input", "value"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def open_dormant_node_modal_for_edit(n_clicks_list, edit_trigger_val, selected_event):
        _N = 49
        if not selected_event:
            return (no_update,) * _N
        triggered = ctx.triggered_id
        if triggered == "dormant-edit-trigger-input":
            # Context-menu Edit on a dormant node in the events canvas.
            # JS appends "|<timestamp>" to force a fresh value on repeat clicks.
            if not edit_trigger_val:
                return (no_update,) * _N
            node_name = edit_trigger_val.split("|")[0]
        else:
            if not any(n_clicks_list) or not triggered:
                return (no_update,) * _N
            node_name = triggered["index"]

        # Locate EventNodes row for this node within the selected event.
        matching = None
        for en in event_manager.get_event_nodes(selected_event):
            if en['node'].name == node_name:
                matching = en
                break
        if not matching:
            return (no_update,) * _N

        node = matching['node']
        delay_days = matching['delay_days'] or 0
        override_on_trigger = bool(matching['override_on_trigger'])
        override_mode_val = matching['override_mode'] or "hard"

        # Derive edge buckets for this node (same mapping as callbacks.populate_editor).
        from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS
        from callback_helpers import parse_links
        from callbacks import _friendly_time_estimates

        edges = graph_manager.get_edges()
        needs_hard_v = [e['source'] for e in edges if e['target'] == node_name and e['type'] == EDGE_NEEDS_HARD]
        needs_soft_v = [e['source'] for e in edges if e['target'] == node_name and e['type'] == EDGE_NEEDS_SOFT]
        supp_hard_v = [e['target'] for e in edges if e['source'] == node_name and e['type'] == EDGE_NEEDS_HARD]
        supp_soft_v = [e['target'] for e in edges if e['source'] == node_name and e['type'] == EDGE_NEEDS_SOFT]
        helps_v = [e['target'] for e in edges if e['source'] == node_name and e['type'] == EDGE_HELPS]

        # Dropdown options — edit mode includes dormant nodes (excluding self) so
        # dormant→dormant edges round-trip correctly.
        node_opts = [{"label": n.name, "value": n.name}
                     for n in graph_manager.get_all_nodes(include_dormant=True)
                     if n.name != node_name]

        # Type / context / subcontext options
        types = ConfigManager.get_node_types()
        contexts = sort_contexts(ConfigManager.get_contexts())
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": c, "value": c} for c in contexts]
        subctx_opts = [{"label": "None", "value": ""}]
        if node.context:
            subs = sort_subcontexts(ConfigManager.get_subcontexts().get(node.context, []))
            subctx_opts += [{"label": s, "value": s} for s in subs]

        # Time fields: convert stored hours back to friendly unit.
        friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
            node.time_o, node.time_m, node.time_p
        )
        time_mode_val = ["inherited"] if node.time_mode == 'inherited' else []
        time_habit_mode_val = ["habit"] if node.time_mode == 'habit' else []
        value_mode_val = ["inherited"] if node.value_mode == 'inherited' else []
        override_toggle_val = ["on"] if override_on_trigger else []
        # Fold stored habit fields onto the per-session editor widgets.
        h_unit, h_o, h_m, h_p, h_days = habit_editor_view(
            node.habit_intensity_unit, node.habit_intensity_o,
            node.habit_intensity_m, node.habit_intensity_p, node.habit_days)

        # Delay: invert to form fields via the shared helper.
        from events_layout import _delay_days_to_form
        delay_val, delay_unit = _delay_days_to_form(delay_days)

        # Link stores
        obs_links = parse_links(node.obsidian_path)
        drive_links = parse_links(node.google_drive_path)
        website_links = parse_links(node.website)

        return (
            True,                              # modal is_open
            node_name,                         # editing-dormant-node-store (original name)
            "Edit Dormant Node",               # title
            "Save",                            # save button text
            node.name,                         # name
            node.type or "Learn",              # type value
            type_opts,                         # type options
            node.context or "",                # context value
            ctx_opts,                          # context options
            node.subcontext or "",             # subcontext value
            subctx_opts,                       # subcontext options
            node.description or "",            # desc
            value_mode_val,                    # value-mode (Inherit ratings)
            node.value or 5,                   # value
            node.interest or 5,                # interest
            node.difficulty or 5,              # difficulty
            friendly_o,                        # time-o
            friendly_m,                        # time-m
            friendly_p,                        # time-p
            friendly_unit,                     # time-unit
            time_mode_val,                     # time-mode
            delay_val,                         # delay-value
            delay_unit,                        # delay-unit
            needs_hard_v,                      # needs-hard value
            node_opts,                         # needs-hard options
            needs_soft_v,                      # needs-soft value
            node_opts,                         # needs-soft options
            supp_hard_v,                       # supports-hard value
            node_opts,                         # supports-hard options
            supp_soft_v,                       # supports-soft value
            node_opts,                         # supports-soft options
            helps_v,                           # helps value
            node_opts,                         # helps options
            obs_links,                         # obsidian store
            drive_links,                       # drive store
            website_links,                     # website store
            override_toggle_val,               # override toggle (checklist list)
            override_mode_val,                 # override mode
            "",                                # save-status
            # Habit-mode pre-fill
            time_habit_mode_val,
            node.habit_duration or 0,
            node.habit_duration_unit or 'weeks',
            h_o,
            h_m,
            h_p,
            h_unit,
            h_days,
            # Hide mode toggle during edit; force "new" so the existing fields render
            {"display": "none"},
            "new",
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

    # --- App-load Announcement Modal ---
    @app.callback(
        Output("modal-event-announcements", "is_open", allow_duplicate=True),
        Output("event-announcements-body", "children"),
        Output("modal-override-conflict", "is_open", allow_duplicate=True),
        Output("override-conflict-body", "children", allow_duplicate=True),
        Output("pending-event-override-store", "data", allow_duplicate=True),
        Output("override-conflict-mode-wrapper", "style", allow_duplicate=True),
        Input("app-load-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def show_event_announcements_on_load(n_intervals):
        if not n_intervals:
            return no_update, no_update, no_update, no_update, no_update, no_update
        entries = ConfigManager.get_pending_event_notifications()
        info_entries = [e for e in entries if e.get("kind") != "override_conflict"]
        if info_entries:
            return True, _render_announcements(info_entries), no_update, no_update, no_update, no_update
        # No informational entries — jump straight to first override conflict (if any).
        # Event-batch resolution ignores mode, so hide the radio.
        first = ConfigManager.pop_next_override_conflict()
        if first:
            return (
                False, no_update,
                True, _format_override_conflict_body(first),
                {"event": first.get("event"), "candidates": first.get("candidate_nodes", [])},
                {"display": "none"},
            )
        return False, no_update, no_update, no_update, no_update, no_update

    @app.callback(
        Output("modal-event-announcements", "is_open", allow_duplicate=True),
        Output("modal-override-conflict", "is_open", allow_duplicate=True),
        Output("override-conflict-body", "children", allow_duplicate=True),
        Output("pending-event-override-store", "data", allow_duplicate=True),
        Output("override-conflict-mode-wrapper", "style", allow_duplicate=True),
        Input("btn-event-announcements-dismiss", "n_clicks"),
        prevent_initial_call=True,
    )
    def dismiss_event_announcements(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update
        # Drop informational entries only; override_conflict entries stay queued.
        ConfigManager.clear_pending_announcements_only()
        first = ConfigManager.pop_next_override_conflict()
        if first:
            return (
                False,
                True,
                _format_override_conflict_body(first),
                {"event": first.get("event"), "candidates": first.get("candidate_nodes", [])},
                {"display": "none"},
            )
        return False, no_update, no_update, no_update, no_update

    # --- Event Graph: render dormant nodes + immediate neighbors ---
    # Outputs to events-elements-pending-store; freeze bypass applied by a
    # clientside callback in callbacks.py.
    @app.callback(
        Output("events-elements-pending-store", "data"),
        Input("selected-event-store", "data"),
        Input("events-refresh-trigger", "data"),
    )
    def render_event_graph(selected_event, _refresh):
        if not selected_event:
            return []

        event_nodes_data = event_manager.get_event_nodes(selected_event)
        dormant_names = {en['node'].name for en in event_nodes_data}
        if not dormant_names:
            return []

        all_edges = graph_manager.get_edges()
        neighbor_names = set()
        for e in all_edges:
            if e['source'] in dormant_names and e['target'] not in dormant_names:
                neighbor_names.add(e['target'])
            if e['target'] in dormant_names and e['source'] not in dormant_names:
                neighbor_names.add(e['source'])

        all_names = dormant_names | neighbor_names
        node_colors = ConfigManager.get_node_colors()
        node_shapes = ConfigManager.get_node_shapes()
        trigger_names = event_manager.get_trigger_node_names()

        elements = []
        for name in all_names:
            node = graph_manager.get_node(name)
            if not node:
                continue
            element = {
                "data": {
                    "id": name,
                    "label": name,
                    "type": node.type,
                    "color": node_colors.get(node.type, "#6c757d"),
                    "shape": node_shapes.get(node.type, "rectangle"),
                    "dormant": 1 if name in dormant_names else 0,
                },
            }
            classes = []
            if name in dormant_names:
                classes.append("dormant")
            if name in trigger_names:
                classes.append("trigger")
            if node.now:
                classes.append("now")
                element["data"]["now_color"] = node_colors.get("Now", "#ffd000")
            # Always emit `classes` (possibly empty) so Cytoscape's diff
            # clears the class when it leaves the new render — see
            # callbacks.py:generate_elements for the rationale.
            element["classes"] = " ".join(classes)
            elements.append(element)

        for e in all_edges:
            if e['source'] in all_names and e['target'] in all_names:
                elements.append({
                    "data": {
                        "id": f"{e['source']}_{e['target']}_{e['type']}",
                        "source": e['source'],
                        "target": e['target'],
                        "type": e['type'],
                    },
                })

        return elements

    # --- Event Graph: single-click populates the editor only if it's already open ---
    # Why: the user wants tapping a node to re-populate an open editor the way it
    # does on other canvases, but never to open the editor from a closed state.
    # Right-click -> Edit (via context_menu.js) remains the explicit open path.
    @app.callback(
        Output("details-edit-trigger-input", "value", allow_duplicate=True),
        Input("events-detail-graph", "tapNodeData"),
        State("sidebar-editor-container", "style"),
        prevent_initial_call=True,
    )
    def populate_editor_from_event_graph(tap_data, editor_style):
        if not tap_data or not tap_data.get("id"):
            return no_update
        editor_open = bool(editor_style) and editor_style.get("transform", "") == "translateX(0px)"
        if not editor_open:
            return no_update
        return f"{tap_data['id']}|{int(time.time())}"

    # --- Events Tab: Node Count Canvas Overlay ---
    @app.callback(
        Output('events-canvas-node-count', 'children'),
        Input('events-detail-graph', 'elements'),
    )
    def update_events_node_count(elements):
        n = sum(1 for el in (elements or []) if 'source' not in el.get('data', {}))
        return f"{n} node{'s' if n != 1 else ''}"

    # --- Events Graph Layout: Toggle Panel ---
    @app.callback(
        Output('events-graph-settings-panel', 'style'),
        Input('btn-events-graph-settings', 'n_clicks'),
        Input('btn-close-events-graph-settings', 'n_clicks'),
        State('events-graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_events_graph_settings(_n_open, _n_close, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Events Graph Layout: Reset to Stored Defaults ---
    @app.callback(
        Output('events-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('events-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('events-graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('events-graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-events-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_events_graph_settings(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update, no_update
        gl = ConfigManager.get_events_graph_layout_defaults()
        return (
            gl.get('edge_length', 50),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )

    # --- Events Graph Layout: Apply Layout Parameters ---
    # Clientside so allowOneLayout('events') is set in the same synchronous
    # function that returns the layout dict — see callbacks.py for the rationale.
    app.clientside_callback(
        """
        function(edge_length, gravity, repulsion, relayout_n, sidebar_relayout_n, elements, freeze_on) {
            var ctx = window.dash_clientside.callback_context;
            var trig = ctx.triggered_id
                || (ctx.triggered && ctx.triggered.length
                    ? ctx.triggered[0].prop_id.split('.')[0]
                    : null);
            var relayout_triggers = ['events-graph-settings-relayout', 'btn-sidebar-relayout'];
            if (freeze_on && relayout_triggers.indexOf(trig) === -1) {
                return window.dash_clientside.no_update;
            }
            var is_relayout = relayout_triggers.indexOf(trig) !== -1;
            var randomize = is_relayout || (trig === 'events-detail-graph');
            if (is_relayout && window.SkillTree && window.SkillTree.allowOneLayout) {
                window.SkillTree.allowOneLayout('events');
            }
            return {
                name: 'fcose',
                quality: 'proof',
                animate: false,
                fit: true,
                randomize: randomize,
                padding: 20,
                idealEdgeLength: edge_length || 100,
                nodeRepulsion: repulsion || 4500,
                gravity: (gravity !== null && gravity !== undefined) ? gravity : 0.25,
                numIter: 2500,
            };
        }
        """,
        Output('events-detail-graph', 'layout'),
        Input('events-graph-settings-edge-length', 'value'),
        Input('events-graph-settings-gravity', 'value'),
        Input('events-graph-settings-repulsion', 'value'),
        Input('events-graph-settings-relayout', 'n_clicks'),
        Input('btn-sidebar-relayout', 'n_clicks'),
        Input('events-detail-graph', 'elements'),
        State('events-freeze-rerender-store', 'data'),
    )

    # --- Events Sidebar Toggle + Tab-Inner Shift (CLIENTSIDE) ---
    # Prior server-side implementations of this toggle exhibited a persistent
    # "sidebar won't reopen after close" bug that resisted multiple fixes. Moving
    # the logic to clientside JS in assets/events_sidebar.js eliminates server-
    # state sync as a failure mode. The handlers also BASE-merge the style dict
    # so a corrupted/partial state can't strand the sidebar off-screen.
    app.clientside_callback(
        ClientsideFunction(namespace='events', function_name='toggle_sidebar'),
        Output("events-sidebar-container", "style"),
        Output("events-ui-refresh-trigger", "data", allow_duplicate=True),
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Output("details-goal-sidebar", "style", allow_duplicate=True),
        Input("btn-events-sidebar-toggle", "n_clicks"),
        Input("btn-events-sidebar-close", "n_clicks"),
        Input("btn-open-events-sidebar", "n_clicks"),
        State("events-sidebar-container", "style"),
        State("sidebar-editor-container", "style"),
        State("details-goal-sidebar", "style"),
        State("events-ui-refresh-trigger", "data"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace='events', function_name='adjust_tab_inner'),
        Output("events-tab-inner", "style"),
        Input("events-sidebar-container", "style"),
    )
