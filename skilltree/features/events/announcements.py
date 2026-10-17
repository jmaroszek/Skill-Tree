"""The Events Triggered announcement: which events fired since it was last
shown, on whichever tab is open."""
from dash import Input, Output, State, html, no_update

from skilltree.store import settings


def register_announcement_callbacks(app, services):
    # --- Events Triggered announcement ---
    # Shown at launch, and whenever an event fires or a delayed node wakes
    # while the app is open: the clock, a save that completes a trigger node,
    # or the Trigger button. Each of those changes the graph or bumps the
    # events refresh. It used to be checked once, at launch only.
    @app.callback(
        Output("modal-event-announcements", "is_open", allow_duplicate=True),
        Output("event-announcements-body", "children"),
        Output("event-announcements-shown", "data", allow_duplicate=True),
        Input("app-load-interval", "n_intervals"),
        Input("events-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        State("event-announcements-shown", "data"),
        prevent_initial_call=True,
    )
    def show_event_announcements(_loaded, _refresh, _version, shown):
        entries = settings.PENDING_EVENT_NOTIFICATIONS.get()
        if not entries or entries == shown:
            return no_update, no_update, no_update
        return True, render_announcements(entries), entries

    @app.callback(
        Output("modal-event-announcements", "is_open", allow_duplicate=True),
        Input("btn-event-announcements-dismiss", "n_clicks"),
        prevent_initial_call=True,
    )
    def dismiss_event_announcements(n_clicks):
        return False if n_clicks else no_update

    # However the announcement closes (Dismiss, the X, a click outside), the
    # notifications it showed are done with. Only those: one queued while it
    # was open is still unread, and opens the next announcement.
    @app.callback(
        Output("event-announcements-shown", "data", allow_duplicate=True),
        Input("modal-event-announcements", "is_open"),
        State("event-announcements-shown", "data"),
        prevent_initial_call=True,
    )
    def forget_shown_announcements(is_open, shown):
        if is_open or not shown:
            return no_update
        settings.remove_event_notifications(shown)
        return None


def render_announcements(entries):
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
            if entry.get("already_met"):
                # Saved or narrowed to trigger nodes that were already Done.
                if len(trig_set) > 1 and entry.get("trigger_mode") == "all":
                    summary = html.Strong(
                        f"{event_name} — triggered: all {len(trig_set)} trigger "
                        f"nodes were already complete ({when})")
                else:
                    summary = html.Strong(
                        f"{event_name} — triggered: {trig} was already complete ({when})")
            elif len(trig_set) > 1 and entry.get("trigger_mode") == "all":
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
    # A node that was already awake when its event fired. Counting it as
    # activated here would claim a wake that did not happen.
    if already_awake:
        parts.append(f"{len(already_awake)} already awake: {', '.join(already_awake)}")
    if now_pinned:
        parts.append(f"added to Now: {', '.join(now_pinned)}")
    # A skip is the Now cap doing its job, but the user still needs telling —
    # they asked for these on the list and they aren't there.
    if now_skipped:
        parts.append(f"Now is full, so these stayed off it: {', '.join(now_skipped)}")
    return " — ".join(parts) if parts else "No nodes"
