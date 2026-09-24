"""
Callback definitions for the Events tab.
"""

import database
import json
import time
import dash
from dash import html, Input, Output, State, ALL, MATCH, ctx, no_update, ClientsideFunction
from event_manager import EventManager
from graph_manager import GraphManager
from config import ConfigManager
from models import Event, STATUS_BLOCKED, STATUS_DONE
from events_layout import (build_event_card, build_dormant_nodes_table, _event_trigger_type,
                           build_triggered_divider, trigger_confirmation_body,
                           build_event_membership_rows,
                           dormant_delete_confirmation_body)
from duration_ui import duration_to_days, format_duration_days
from prerender import prerendered
from callback_helpers import (build_node_element, build_edge_element,
                              canvas_node_styles, build_dormancy_snapshot,
                              NEW_EVENT_OPTION)
import style_tokens as tokens

event_manager = EventManager()
graph_manager = GraphManager()

_badge_hidden = {"fontSize": tokens.FS_BASE, "display": "none"}


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
    """Formats pending event notification entries into a readable list for the modal body."""
    items = []
    for entry in entries:
        kind = entry.get("kind")
        when = entry.get("when", "")
        event_name = entry.get("event")
        activated = entry.get("activated") or []
        scheduled = entry.get("scheduled") or []
        now_pinned = entry.get("now_pinned") or []
        now_skipped = entry.get("now_skipped") or []
        already_awake = entry.get("already_awake") or []

        if kind == "date_triggered":
            summary = html.Strong(f"{event_name} — date-triggered ({when})")
            detail = _format_node_counts(activated, scheduled, now_pinned, now_skipped,
                                         already_awake)
        elif kind == "manual_triggered":
            summary = html.Strong(f"{event_name} — triggered manually ({when})")
            detail = _format_node_counts(activated, scheduled, now_pinned, now_skipped,
                                         already_awake)
        elif kind == "node_triggered":
            trig = entry.get("trigger_node", "?")
            trig_set = entry.get("trigger_nodes") or []
            if len(trig_set) > 1 and entry.get("trigger_mode") == "all":
                summary = html.Strong(
                    f"{event_name} — triggered: all {len(trig_set)} nodes complete, "
                    f"last was {trig} ({when})")
            else:
                summary = html.Strong(f"{event_name} — triggered by completing {trig} ({when})")
            detail = _format_node_counts(activated, scheduled, now_pinned, now_skipped,
                                         already_awake)
        elif kind == "delayed_activated":
            nodes = entry.get("nodes") or []
            summary = html.Strong(f"{event_name} — delayed nodes activated ({when})")
            # A delayed node flagged "Add to Now" is pinned when it wakes, not
            # when its event fired, so this is where the outcome shows up.
            parts = [f"Nodes: {', '.join(nodes)}"] if nodes else []
            if now_pinned:
                parts.append(f"added to Now: {', '.join(now_pinned)}")
            if now_skipped:
                parts.append("Now is full, so these stayed off it: "
                             f"{', '.join(now_skipped)}")
            detail = " — ".join(parts)
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
            continue  # unknown kinds are not shown here

        items.append(html.Li([summary, html.Br(), html.Span(detail, className="text-muted small")] if detail else [summary]))
    return html.Ul(items, style={"marginBottom": 0})


def _format_node_counts(activated, scheduled, now_pinned=(), now_skipped=(),
                        already_awake=()):
    parts = []
    if activated:
        parts.append(f"{len(activated)} activated: {', '.join(activated)}")
    if scheduled:
        parts.append(f"{len(scheduled)} scheduled: {', '.join(scheduled)}")
    # A node another event woke first. Counting it as activated here would
    # claim a wake that did not happen.
    if already_awake:
        parts.append(f"{len(already_awake)} already awake: {', '.join(already_awake)}")
    if now_pinned:
        parts.append(f"added to Now: {', '.join(now_pinned)}")
    # A skip is the Now cap doing its job, but the user still needs telling —
    # they asked for these on the list and they aren't there.
    if now_skipped:
        parts.append(f"Now is full, so these stayed off it: {', '.join(now_skipped)}")
    return " — ".join(parts) if parts else "No nodes"


def register_event_callbacks(app, services=None):
    event_manager = services.events if services is not None else globals()['event_manager']
    graph_manager = services.graph if services is not None else globals()['graph_manager']

    # Events arrival gate. The three data-heavy Events callbacks below still
    # refresh when the user opens Events, but switching between any other tabs
    # now stays entirely clientside instead of posting their hidden content.
    app.clientside_callback(
        """
        function(active_tab) {
            if (active_tab !== 'tab-events') {
                return window.dash_clientside.no_update;
            }
            return Date.now();
        }
        """,
        Output("events-active-store", "data"),
        Input("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )

    # --- Tab Visibility Toggle ---
    @app.callback(
        Output("next-tab-content", "style"),
        Output("canvas-tab-content", "style"),
        Output("details-tab-content", "style"),
        Output("events-tab-content", "style"),
        Output("analyze-tab-content", "style"),
        Input("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    @prerendered
    def toggle_tab_content(active_tab):
        base = {"width": "100%", "height": "100%", "overflow": "hidden", "position": "absolute", "top": "0", "left": "0"}
        next_style = {**base,
                      "display": "flex" if active_tab == "tab-next" else "none",
                      "flexDirection": "column",
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
        Input("events-active-store", "data"),
        Input("event-order-store", "data"),
        Input("events-search-input", "value"),
        Input("events-show-triggered-store", "data"),
        Input("events-sort-mode", "data"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    @prerendered
    def render_events_list(refresh_trigger, ui_refresh, _arrived, event_order, search_text, show_triggered, sort_mode, selected_event):
        events = event_manager.get_all_events()
        if not events:
            return html.Div(
                html.P("No events yet.", className="text-muted"),
                className="text-center py-5"
            )

        # One grouped query for every card and for the impact sort. Both used
        # to ask per event, which made a render cost one query per row.
        node_counts = event_manager.get_event_node_counts()

        # Apply ordering based on sort mode
        if sort_mode == "az":
            events = sorted(events, key=lambda e: (e.name or "").lower())
        elif sort_mode == "type":
            # Group by trigger type; within Scheduled, soonest date first.
            type_order = {"date": 0, "node": 1, "manual": 2}
            events = sorted(
                events,
                key=lambda e: (
                    type_order[_event_trigger_type(e)],
                    e.trigger_date or "" if _event_trigger_type(e) == "date" else "",
                    (e.name or "").lower(),
                ),
            )
        elif sort_mode == "impact":
            # Most dormant nodes unlocked first.
            events = sorted(
                events,
                key=lambda e: (-node_counts[e.name]["total"], (e.name or "").lower()),
            )
        else:
            # Manual: apply drag-and-drop order from store
            stored_order = event_order or []
            if stored_order:
                event_map = {e.name: e for e in events}
                ordered = [event_map[n] for n in stored_order if n in event_map]
                remaining = [e for e in events if e.name not in set(stored_order)]
                events = ordered + remaining

        # Filter: search text (name or description, case-insensitive). It runs
        # before the triggered split so the hidden count only counts matches.
        query = (search_text or "").strip().lower()
        if query:
            events = [
                e for e in events
                if query in (e.name or "").lower() or query in (e.description or "").lower()
            ]

        # An event leaves the list when it is *finished*, not merely fired.
        # Status alone used to decide, so an event with three nodes waking in
        # March vanished the moment it triggered.
        def _finished(event):
            counts = node_counts[event.name]
            return (event.status == "Triggered"
                    and counts['activated'] >= counts['total'])

        active = [e for e in events if not _finished(e)]
        triggered = [e for e in events if _finished(e)]

        is_manual = sort_mode not in ("az", "type", "impact")

        def _cards(group):
            cards = []
            for event in group:
                counts = node_counts[event.name]
                cards.append(build_event_card(
                    event.name, event.description, event.status, counts,
                    is_selected=(event.name == selected_event),
                    trigger_date=event.trigger_date,
                    trigger_nodes=event.trigger_nodes,
                    trigger_mode=event.trigger_mode,
                    show_drag_handle=is_manual,
                ))
            return cards

        if not active and not triggered:
            return html.Div(
                html.P("No matching events.", className="text-muted"),
                className="text-center py-5"
            )

        # Each group is its own sortable (event_sortable.js), so a drag can't
        # carry a card across the triggered divider.
        if active:
            children = [html.Div(_cards(active), className="events-sort-group")]
        else:
            children = [html.Div(
                html.P("No matching events." if query else "No events to show.",
                       className="text-muted"),
                className="text-center py-4"
            )]
        if triggered:
            children.append(build_triggered_divider(len(triggered), bool(show_triggered)))
            if show_triggered:
                children.append(html.Div(_cards(triggered), className="events-sort-group"))
        return children

    # The divider is rebuilt with the list, so its n_clicks resets to None on
    # every render; only a real click flips the store.
    app.clientside_callback(
        """function(clicks, shown) {
            if (!(clicks || []).some(Boolean)) {
                return window.dash_clientside.no_update;
            }
            return !shown;
        }""",
        Output("events-show-triggered-store", "data"),
        Input({"type": "events-triggered-toggle", "index": ALL}, "n_clicks"),
        State("events-show-triggered-store", "data"),
        prevent_initial_call=True,
    )

    # Selection only changes card decoration; keep the cards and their
    # tooltips mounted while the graph opens. Rebuilt lists already carry
    # the selected style from render_events_list's State.
    app.clientside_callback(
        """function(selected, ids, styles) {
            return (ids || []).map(function(id, index) {
                var style = Object.assign({}, (styles || [])[index] || {});
                var active = id.index === selected;
                style.border = active ? '2px solid #0d6efd' : '1px solid #495057';
                style.backgroundColor = active ? 'var(--st-bg-raised)' : 'var(--st-bg-panel)';
                return style;
            });
        }""",
        Output({'type': 'event-card', 'index': ALL}, 'style'),
        Input('selected-event-store', 'data'),
        Input({'type': 'event-card', 'index': ALL}, 'id'),
        State({'type': 'event-card', 'index': ALL}, 'style'),
    )

    # --- Autocomplete datalist for events search ---
    @app.callback(
        Output("events-search-datalist", "children"),
        Input("events-refresh-trigger", "data"),
        Input("events-active-store", "data"),
        prevent_initial_call=True,
    )
    @prerendered
    def populate_events_search_datalist(refresh_trigger, _arrived):
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

    # --- Populate trigger node dropdown when Events data changes/arrives ---
    @app.callback(
        Output("event-trigger-node", "options"),
        Input("events-refresh-trigger", "data"),
        Input("events-active-store", "data"),
        prevent_initial_call=True,
    )
    @prerendered
    def populate_trigger_node_dropdown(_refresh, _arrived):
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name} for n in sorted(nodes, key=lambda n: n.name)]

    # --- Trigger mode hint text ---
    @app.callback(
        Output("event-trigger-mode-hint", "children"),
        Input("event-trigger-mode", "value"),
        Input("event-trigger-node", "value"),
        prevent_initial_call=True,
    )
    @prerendered
    def describe_trigger_mode(trigger_mode, trigger_nodes):
        return _trigger_mode_hint(trigger_mode, trigger_nodes)

    # --- Trigger Type Section Visibility ---
    @app.callback(
        Output("event-date-section", "style"),
        Output("event-node-section", "style"),
        Input("event-trigger-type", "value"),
        prevent_initial_call=True,
    )
    @prerendered
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
        Output("event-delete-wrapper", "style", allow_duplicate=True),
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
            no_update,  # Selection does not invalidate event data or dropdowns.
            {"display": "none"},
            {"display": "block"},
            event.name,
            event.description,
            "", "primary", _badge_hidden,
            build_dormant_nodes_table(event_nodes, event),
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
            no_update,
            {"display": "none"},
            {"display": "block"},
            event.name,
            event.description,
            "", "primary", _badge_hidden,
            build_dormant_nodes_table(event_nodes, event),
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
        Output("event-delete-wrapper", "style", allow_duplicate=True),
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

    # All three verbs sit in the Actions section now, but they do not share a
    # visibility rule: Delete and Trigger exist only for a saved, untriggered
    # event, while Save has to stay live so a new event can be created at all.
    # Four callbacks drive the Delete wrapper's style and the Trigger wrapper
    # mirrors it; Save is deliberately in neither wrapper.
    #
    # Neither wrapper may carry a Bootstrap display utility (.d-flex and
    # friends are `!important` and beat an inline style). That is exactly how
    # the old event-trigger-section lost this argument: it boxed Delete and
    # Save together in a .d-flex, so the `display: none` these callbacks write
    # was silently ignored and Delete stayed on screen for new and already-
    # triggered events.
    @app.callback(
        Output("event-trigger-btn-wrapper", "style"),
        Input("event-delete-wrapper", "style"),
        prevent_initial_call=True,
    )
    def mirror_trigger_button_visibility(section_style):
        return section_style

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

    # Fills the confirm modal once it is open. Three separate callbacks already
    # write this modal's `is_open`, and one of them splats _DETAIL_OUTPUTS and
    # counts its no_updates by hand -- adding a body Output to each would mean
    # three edits in lockstep every time that count moves. Reading `is_open` as
    # an Input costs one round trip after the modal appears and keeps them all
    # untouched.
    @app.callback(
        Output("trigger-confirm-body", "children"),
        Input("modal-confirm-trigger", "is_open"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def fill_trigger_confirmation(is_open, selected_event):
        if not is_open or not selected_event:
            return no_update
        return trigger_confirmation_body(
            selected_event, event_manager.get_event_nodes(selected_event))

    @app.callback(
        Output("selected-event-store", "data", allow_duplicate=True),
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Output("event-status-badge", "children", allow_duplicate=True),
        Output("event-status-badge", "color", allow_duplicate=True),
        Output("event-delete-wrapper", "style", allow_duplicate=True),
        Output("dormant-nodes-table-container", "children", allow_duplicate=True),
        Output("event-save-status", "children", allow_duplicate=True),
        Output("modal-confirm-trigger", "is_open", allow_duplicate=True),
        Output("event-trigger-date", "value", allow_duplicate=True),
        Input("btn-trigger-confirm", "n_clicks"),
        State("selected-event-store", "data"),
        State("manual-now-trigger-toggle", "value"),
        prevent_initial_call=True,
    )
    def trigger_event(n_clicks, selected_event, now_toggle):
        if not n_clicks or not selected_event:
            return (no_update,) * 9

        # One button, every node. The Now pinning and the announcement live in
        # the manager now, so this path behaves exactly like the date and
        # node-completion ones.
        result = event_manager.trigger_event_manually(
            selected_event, pin_all_now=bool(now_toggle))

        activated = result['activated']
        scheduled = result['scheduled']
        already_awake = result['already_awake']
        now_pinned = result['now_pinned']
        now_skipped = result['now_skipped']

        event_nodes = event_manager.get_event_nodes(selected_event)
        msg_parts = []
        if activated:
            msg_parts.append(f"{len(activated)} node(s) activated")
        if scheduled:
            msg_parts.append(f"{len(scheduled)} node(s) scheduled")
        if already_awake:
            msg_parts.append(f"{len(already_awake)} already awake")
        if now_pinned:
            msg_parts.append(f"{len(now_pinned)} added to Now")
        if now_skipped:
            msg_parts.append(f"{len(now_skipped)} left off Now (cap reached)")

        return (
            selected_event,
            f"trigger-{selected_event}",
            "Triggered", "success",
            {"display": "none"},
            build_dormant_nodes_table(event_nodes,
                                      event_manager.get_event(selected_event)),
            "Event triggered. " + (", ".join(msg_parts) if msg_parts
                                   else "It had no dormant nodes."),
            False,
            "",
        )

    # --- Node editor: Dormant switch and Events section ---
    #
    # Dormant is an ordinary form field. Flipping it writes nothing; Save
    # applies it (node_commands.apply_dormancy). These callbacks fill the
    # section from the database, keep its visibility in step with the
    # switches, and collect it into node-dormancy-form for Save and the
    # unsaved-changes check.

    def _pending_event_options(exclude=()):
        options = [{"label": e.name, "value": e.name}
                   for e in event_manager.get_all_events()
                   if e.status == "Pending" and e.name not in exclude]
        # A native <select> can't hold an <hr>, so the divider is a disabled
        # option drawn with box-drawing characters.
        divider = [{"label": "─" * 16, "value": "__divider__", "disabled": True}] if options else []
        return options + divider + [{"label": "New event…", "value": NEW_EVENT_OPTION}]

    @app.callback(
        Output("node-dormant", "value"),
        Output("node-event-memberships", "children"),
        Output("node-join-event", "options"),
        Output("node-join-event", "value"),
        Output("node-join-event-label", "children"),
        Output("node-join-event-name", "value"),
        Output("node-join-delay-value", "value"),
        Output("node-join-delay-unit", "value"),
        Output("node-join-delay-on", "value"),
        Output("node-join-now", "value"),
        Output("node-dormant-loaded", "data"),
        Output("editor-pristine-snapshot", "data", allow_duplicate=True),
        Output("editor-dormant-preset", "data", allow_duplicate=True),
        Input("node-original-name", "data"),
        Input("events-refresh-trigger", "data"),
        State("editor-dormant-preset", "data"),
        State("editor-pristine-snapshot", "data"),
        prevent_initial_call=True,
    )
    def populate_node_dormancy(node_name, _refresh, preset, snapshot):
        node = graph_manager.get_node(node_name) if node_name else None
        dormancy = build_dormancy_snapshot(node, event_manager)
        consumed = no_update

        # The Events tab's "+" opens a blank editor with Dormant already on
        # and the event chosen. The preset is used once, by the next blank
        # form, and only while it is fresh.
        if node is None and preset and preset.get("event"):
            consumed = None
            if time.time() * 1000 - (preset.get("ts") or 0) < 30_000:
                dormancy = {"dormant": True, "rows": [],
                            "join": preset["event"], "join_name": ""}

        rows = dormancy["rows"]
        in_events = {row[0] for row in rows}
        if isinstance(snapshot, dict):
            snapshot = {**snapshot, "dormancy": dormancy}
        else:
            snapshot = no_update
        return (
            ["dormant"] if dormancy["dormant"] else [],
            build_event_membership_rows(rows),
            _pending_event_options(exclude=in_events),
            dormancy["join"],
            "Also add to event" if rows else "Add to event",
            "", 0, "days", [], [],
            bool(node is not None and node.dormant),
            snapshot,
            consumed,
        )

    # The list is also filled whenever Dormant is switched on. A blank form
    # opened from the toolbar never loads a node, so the populator above
    # never runs for it, and an event created since the last load would be
    # missing anyway.
    @app.callback(
        Output("node-join-event", "options", allow_duplicate=True),
        Input("node-dormant", "value"),
        State("node-dormancy-form", "data"),
        prevent_initial_call=True,
    )
    def refresh_join_event_options(dormant, dormancy):
        if not dormant:
            return no_update
        in_events = {row[0] for row in (dormancy or {}).get("rows") or []}
        return _pending_event_options(exclude=in_events)

    # A cancelled unsaved-changes prompt means the "+" never got its blank
    # form, so its preset must not wait around for the next one.
    @app.callback(
        Output("editor-dormant-preset", "data", allow_duplicate=True),
        Input("btn-unsaved-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def drop_dormant_preset(n_clicks):
        return None if n_clicks else no_update

    app.clientside_callback(
        """
        function(dormant, delayOns, delayValues, delayUnits, wakeDates, nows,
                 join, joinName, joinDelayOn, joinDelay, joinUnit, joinNow,
                 delayOnIds, delayIds, unitIds, wakeIds, nowIds) {
            function on(v) { return !!(v && v.indexOf('on') >= 0); }
            var rows = {};
            function row(ev) {
                if (!rows[ev]) rows[ev] = [ev, null, null, null, false];
                return rows[ev];
            }
            // A delay behind a switched-off Delay is no delay.
            var delayed = {};
            (delayOnIds || []).forEach(function(id, i) { delayed[id.index] = on(delayOns[i]); });
            (delayIds || []).forEach(function(id, i) {
                var v = delayValues[i];
                row(id.index)[1] = !delayed[id.index] ? 0
                    : ((v === undefined || v === '') ? null : v);
            });
            (unitIds || []).forEach(function(id, i) { row(id.index)[2] = delayUnits[i]; });
            // A cleared date stays '' rather than null, so Save can tell a
            // wake-date row that lost its date from a delay row.
            (wakeIds || []).forEach(function(id, i) { row(id.index)[3] = wakeDates[i] || ''; });
            (nowIds || []).forEach(function(id, i) {
                row(id.index)[4] = on(nows[i]);
            });
            var list = Object.keys(rows).sort().map(function(k) { return rows[k]; });
            return {
                dormant: !!(dormant && dormant.indexOf('dormant') >= 0),
                rows: list,
                join: join || null,
                join_name: joinName || '',
                join_delay_value: on(joinDelayOn) ? joinDelay : 0,
                join_delay_unit: joinUnit,
                join_now: on(joinNow)
            };
        }
        """,
        Output("node-dormancy-form", "data"),
        Input("node-dormant", "value"),
        Input({"type": "membership-delay-on", "index": ALL}, "value"),
        Input({"type": "membership-delay-value", "index": ALL}, "value"),
        Input({"type": "membership-delay-unit", "index": ALL}, "value"),
        Input({"type": "membership-wake-date", "index": ALL}, "value"),
        Input({"type": "membership-now", "index": ALL}, "value"),
        Input("node-join-event", "value"),
        Input("node-join-event-name", "value"),
        Input("node-join-delay-on", "value"),
        Input("node-join-delay-value", "value"),
        Input("node-join-delay-unit", "value"),
        Input("node-join-now", "value"),
        State({"type": "membership-delay-on", "index": ALL}, "id"),
        State({"type": "membership-delay-value", "index": ALL}, "id"),
        State({"type": "membership-delay-unit", "index": ALL}, "id"),
        State({"type": "membership-wake-date", "index": ALL}, "id"),
        State({"type": "membership-now", "index": ALL}, "id"),
    )

    # Now and Done hide while Dormant is on, and Dormant hides while Now or
    # Done is on: a node being worked on, or finished, isn't asleep.
    # Unchecking Dormant on a sleeping node says what Save will do, which is
    # what the old wake-confirm modal used to ask.
    app.clientside_callback(
        """
        function(dormant, now, done, join, joinDelayOn, snapshot) {
            var hide = {display: 'none'}, show = {};
            var isDormant = !!(dormant && dormant.indexOf('dormant') >= 0);
            var isBusy = !!(now && now.length) || !!(done && done.length);
            var saved = (snapshot && snapshot.dormancy) || {};
            var waking = !!saved.dormant && !isDormant;
            var events = (saved.rows || []).map(function(r) { return r[0]; });
            var warning = '';
            if (waking) {
                warning = events.length
                    ? 'Saving wakes this node and removes it from ' + events.join(', ') + '.'
                    : 'Saving wakes this node.';
            }
            return [
                isDormant ? hide : show,
                isDormant ? hide : show,
                (isBusy && !isDormant) ? hide : show,
                isDormant ? show : hide,
                join === '__new__' ? show : hide,
                join ? show : hide,
                (joinDelayOn && joinDelayOn.length) ? show : hide,
                waking ? show : hide,
                warning
            ];
        }
        """,
        Output("node-now-wrapper", "style"),
        Output("node-status-done-wrapper", "style"),
        Output("node-dormant-wrapper", "style"),
        Output("node-dormant-section", "style"),
        Output("node-join-event-name", "style"),
        Output("node-join-settings", "style"),
        Output("node-join-delay-fields", "style"),
        Output("node-dormant-wake-warning", "style"),
        Output("node-dormant-wake-warning", "children"),
        Input("node-dormant", "value"),
        Input("node-now", "value"),
        Input("node-status-done", "value"),
        Input("node-join-event", "value"),
        Input("node-join-delay-on", "value"),
        Input("editor-pristine-snapshot", "data"),
    )

    # Each event row's Delay switch shows or hides its own delay fields.
    app.clientside_callback(
        """
        function(on) {
            return (on && on.length) ? {} : {display: 'none'};
        }
        """,
        Output({"type": "membership-delay-fields", "index": MATCH}, "style"),
        Input({"type": "membership-delay-on", "index": MATCH}, "value"),
        prevent_initial_call=True,
    )

    # A save that put a node to sleep, changed its events or woke it has to
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

    # --- Events tab: "+" opens the node editor on a new dormant node ---
    # Clears the form through the editor's own New-node button, so the
    # unsaved-changes prompt behaves exactly as it does there. That button
    # lives inside the editor and never has to open it, so the sidebar is
    # opened here, the way the toolbar's fast path does (editor_sidebar.js).
    # The preset rides alongside and populate_node_dormancy applies it.
    app.clientside_callback(
        """
        function(n, selectedEvent, editorStyle, goalStyle, eventsStyle) {
            var NO = window.dash_clientside.no_update;
            if (!n || !selectedEvent) return [NO, NO, NO, NO];
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
        Input("btn-add-dormant-node", "n_clicks"),
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
        Input("btn-add-existing-to-event", "n_clicks"),
        State("selected-event-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_to_event_modal(trigger_val, n_clicks, selected_event):
        _N = 9
        if not trigger_val and not n_clicks:
            return (no_update,) * _N
        picked = []
        target = None
        if ctx.triggered_id == "dormant-existing-trigger-input":
            # context_menu.js writes a JSON list of node names plus "|<ms>".
            if not trigger_val:
                return (no_update,) * _N
            try:
                picked = json.loads(trigger_val.split("|")[0])
            except ValueError:
                return (no_update,) * _N
            if not isinstance(picked, list):
                return (no_update,) * _N
        elif ctx.triggered_id == "btn-add-existing-to-event":
            if not n_clicks or not selected_event:
                return (no_update,) * _N
            target = selected_event
        else:
            return (no_update,) * _N

        live = [n.name for n in graph_manager.get_all_nodes() if not n.dormant]
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
        already = {en['node'].name for en in event_manager.get_event_nodes(target)}
        for name in names:
            if name in already or not graph_manager.get_node(name):
                continue
            event_manager.add_node_to_event(target, name, delay_days,
                                            now_on_trigger=now_on_trigger)
            if not graph_manager.get_node(name).dormant:
                # The node editor's refusal: a woken row keeps the node awake,
                # so the add would silently do nothing.
                raise ValueError(f"'{name}' was already woken by another event, "
                                 "so it can't go back to sleep.")

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
        Output("move-dormant-note", "children", allow_duplicate=True),
        Input("move-dormant-target-event", "value"),
        State("move-dormant-node-store", "data"),
        prevent_initial_call=True,
    )
    def warn_about_a_merge(target_event, node_name):
        """The PK is (event, node), and a node may already sit in the target."""
        if not target_event or not node_name:
            return no_update
        already = node_name in {en['node'].name
                                for en in event_manager.get_event_nodes(target_event)}
        if not already:
            return no_update
        return (f'"{node_name}" is already in "{target_event}". Moving will '
                "fold the two together and keep that event's delay.")

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
        others = [e for e in event_manager.get_events_for_node(node_name)
                  if e != selected_event]
        return (True, dormant_delete_confirmation_body(node_name, others),
                node_name)

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

    # --- App-load Announcement Modal ---
    @app.callback(
        Output("modal-event-announcements", "is_open", allow_duplicate=True),
        Output("event-announcements-body", "children"),
        Input("app-load-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def show_event_announcements_on_load(n_intervals):
        if not n_intervals:
            return no_update, no_update
        entries = ConfigManager.get_pending_event_notifications()
        if entries:
            return True, _render_announcements(entries)
        return False, no_update

    @app.callback(
        Output("modal-event-announcements", "is_open", allow_duplicate=True),
        Input("btn-event-announcements-dismiss", "n_clicks"),
        prevent_initial_call=True,
    )
    def dismiss_event_announcements(n_clicks):
        if not n_clicks:
            return no_update
        ConfigManager.clear_pending_announcements_only()
        return False

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
        styles = canvas_node_styles(event_manager)

        elements = []
        for name in all_names:
            node = graph_manager.get_node(name)
            if not node:
                continue
            # "Dormant" on this canvas means attached to the selected event,
            # whatever the node's own flag says. The context menu routes Edit
            # on those nodes to the dormant-node editor.
            elements.append(build_node_element(
                node, styles, dormant=name in dormant_names))

        for e in all_edges:
            if e['source'] in all_names and e['target'] in all_names:
                elements.append(build_edge_element(e))

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
        Output('events-graph-settings-animate', 'value', allow_duplicate=True),
        Output('events-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('events-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('events-graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('events-graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-events-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_events_graph_settings(n_clicks):
        if not n_clicks:
            return no_update, no_update, no_update, no_update, no_update
        gl = ConfigManager.get_events_graph_layout_defaults()
        return (
            True,
            gl.get('edge_length', 50),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )

    # --- Events Graph Layout: layout requests ---
    # Registered with every canvas's in callbacks.py; built by
    # assets/layout_requests.js.

    # --- Events Sidebar Toggle + Tab-Arrival Default + Tab-Inner Shift (CLIENTSIDE) ---
    # Prior server-side implementations of this toggle exhibited a persistent
    # "sidebar won't reopen after close" bug that resisted multiple fixes. Moving
    # the logic to clientside JS in assets/events_sidebar.js eliminates server-
    # state sync as a failure mode. The handlers also BASE-merge the style dict
    # so a corrupted/partial state can't strand the sidebar off-screen.
    app.clientside_callback(
        ClientsideFunction(namespace='events', function_name='toggle_sidebar'),
        Output("events-sidebar-container", "style"),
        Output("events-tab-inner", "style", allow_duplicate=True),
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Output("details-goal-sidebar", "style", allow_duplicate=True),
        Input("btn-events-sidebar-toggle", "n_clicks"),
        Input("btn-events-sidebar-close", "n_clicks"),
        Input("main-tabs", "active_tab"),
        State("events-sidebar-container", "style"),
        State("sidebar-editor-container", "style"),
        State("details-goal-sidebar", "style"),
        State("events-ui-refresh-trigger", "data"),
        State("selected-event-store", "data"),
        State("event-detail-empty", "style"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        ClientsideFunction(namespace='events', function_name='adjust_tab_inner'),
        Output("events-tab-inner", "style"),
        Input("events-sidebar-container", "style"),
    )
