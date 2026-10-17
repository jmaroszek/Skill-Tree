"""
Callback definitions for the Events tab.
"""

import time
from datetime import date

import dash
from dash import ALL, ClientsideFunction, Input, Output, State, ctx, html, no_update

from skilltree.domain.models import Event
from skilltree.features.events.announcements import register_announcement_callbacks
from skilltree.features.events.dormant import register_dormant_callbacks
from skilltree.features.events.graph import register_event_graph_callbacks
from skilltree.features.events.layout import (
    event_trigger_type,
    build_dormant_nodes_table,
    build_event_card,
    build_triggered_divider,
    trigger_confirmation_body,
)
from skilltree.store import settings
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui import tokens
from skilltree.ui.components.list_toolbar import merge_manual_order
from skilltree.ui.prerender import prerendered


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


def register_events_callbacks(app, services):
    event_manager = services.events
    graph_manager = services.graph

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
    def render_events_list(refresh_trigger, ui_refresh, _arrived, _order_changed, search_text, show_triggered, sort_mode, selected_event):
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
                    type_order[event_trigger_type(e)],
                    e.trigger_date or "" if event_trigger_type(e) == "date" else "",
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
            # Manual: the saved drag order. It comes from the database, not
            # the store: the store is loaded with the page, while renames and
            # deletes keep the saved order current.
            stored_order = settings.EVENT_ORDER.get()
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
        from dash import html
        events = event_manager.get_all_events()
        return [html.Option(value=e.name) for e in events]

    # --- Event clock ---
    # Date triggers and wake dates come due by the calendar. core_engine checks
    # them whenever it runs, which is on nearly every interaction. This checks
    # them while the app sits open, so a node due overnight is awake before the
    # first click of the morning. A refresh goes out only when something fired.
    @app.callback(
        Output("events-refresh-trigger", "data", allow_duplicate=True),
        Input("event-clock", "n_intervals"),
        prevent_initial_call=True,
    )
    def run_event_clock(_n):
        if not event_manager.run_sweeps():
            return no_update
        return f"event-clock-{int(time.time() * 1000)}"

    # --- Event Reordering (drag-and-drop) ---
    @app.callback(
        Output("event-order-store", "data"),
        Input("event-drag-order-input", "value"),
        prevent_initial_call=True,
    )
    def reorder_event(drag_order_json):
        import json
        try:
            shown = json.loads(drag_order_json) if drag_order_json else None
        except (ValueError, TypeError):
            return no_update
        if not isinstance(shown, list) or not shown:
            return no_update
        # The drag reorders the cards it shows (a search, or hidden finished
        # events, leave some out) within the saved order.
        order = merge_manual_order(settings.EVENT_ORDER.get(), shown)
        settings.EVENT_ORDER.set(order)
        return order

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
        t_type = event_trigger_type(event)

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
        # "name|action|<ms>". The event's name may itself contain "|".
        parts = bridge_payloads.fields(action_value, 2)
        if parts is None:
            return (no_update,) * (_N_DETAIL + 2)
        event_name, action = parts
        event = event_manager.get_event(event_name)
        if not event:
            return (no_update,) * (_N_DETAIL + 2)

        event_nodes = event_manager.get_event_nodes(event_name)
        trigger_style = {"display": "none"} if event.status == "Triggered" else {
            "display": "flex", "alignItems": "center"
        }
        t_type = event_trigger_type(event)

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
        # A Date event saved without one was stored with an empty date, which
        # the sweep read as already due: it fired on the next click and woke
        # every node it held, while its card still said Manual.
        if trigger_type == "date":
            try:
                resolved_date = date.fromisoformat((trigger_date or "").strip()).isoformat()
            except ValueError:
                return (no_update, no_update, "Pick a date.",
                        no_update, no_update, no_update, no_update, no_update)

        before = event_manager.get_event(selected_event) if selected_event else None
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
        fired = event is not None and event.status == "Triggered"
        trigger_style = {"display": "none"} if fired else {
            "display": "flex", "alignItems": "center"
        }
        # An edit can leave the trigger condition met already (it dropped the
        # unfinished nodes, or switched to OR), and the save fires the event.
        message = ("Saved. Its trigger condition was already met, so it fired."
                   if fired and before is not None and before.status == "Pending"
                   else "Saved.")

        return name, f"save-{name}", message, trigger_style, "", "primary", _badge_hidden, False

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
        try:
            result = event_manager.trigger_event_manually(
                selected_event, pin_all_now=bool(now_toggle))
        except ValueError as exc:
            # Fired already (from another window, or on its date) or deleted.
            # Close the dialog and show the event as it now stands.
            event = event_manager.get_event(selected_event)
            if event is None:
                return (no_update, f"trigger-{selected_event}", no_update, no_update,
                        no_update, no_update, str(exc), False, no_update)
            return (
                selected_event,
                f"trigger-{selected_event}",
                "Triggered", "success",
                {"display": "none"},
                build_dormant_nodes_table(event_manager.get_event_nodes(selected_event),
                                          event),
                str(exc),
                False,
                "",
            )

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

    register_dormant_callbacks(app, services)
    register_announcement_callbacks(app, services)
    register_event_graph_callbacks(app, services)
