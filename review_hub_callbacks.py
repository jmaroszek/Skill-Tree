"""Callbacks for the Reflection Hub modal.

Owns open/close wiring, the Pending tab's live count, the Excluded tab's
list + restore controls (moved here from settings_callbacks), and the
Review History table + filters + edit hand-off.
"""

from dash import Input, Output, State, ALL, ctx, no_update, html
import dash_bootstrap_components as dbc

from config import ConfigManager, sort_subcontexts
from graph_manager import GraphManager
from callback_helpers import build_calibration_dismissed_view
from models import STATUS_DONE


_manager = GraphManager()


# Sentinel string for missing-actual cells in the History table.
_DASH = "—"


def _fmt_hours(hours):
    """Friendly time; DASH for missing."""
    if hours is None:
        return _DASH
    return ConfigManager.format_time_friendly(hours)


def _fmt_delta_hours(actual, estimate):
    """Signed friendly time delta. DASH if either side is missing."""
    if actual is None or estimate is None or estimate <= 0:
        return _DASH
    diff = actual - estimate
    sign = "+" if diff >= 0 else "−"
    return f"{sign}{ConfigManager.format_time_friendly(abs(diff))}"


def _fmt_vie_tuple(v, i, d):
    """Compact 'V/I/E' string; DASH if any dimension is missing."""
    if v is None or i is None or d is None:
        return _DASH
    return f"{int(v)}/{int(i)}/{int(d)}"


def _fmt_vie_delta(av, ai, ad, ev, ei, ed):
    """Signed per-dimension Δ V/I/E. DASH if any actual missing."""
    if av is None or ai is None or ad is None:
        return _DASH

    def _signed(actual, est):
        diff = int(actual) - int(est)
        if diff == 0:
            return "0"
        return f"+{diff}" if diff > 0 else f"−{abs(diff)}"

    return f"{_signed(av, ev)}/{_signed(ai, ei)}/{_signed(ad, ed)}"


def _node_has_actuals(node):
    """True when the node carries any captured-actual datapoint —
    qualifies it for the History tab regardless of dismissed flag."""
    return (node.actual_time_lower is not None
            or node.actual_time_point is not None
            or node.actual_time_upper is not None
            or node.reflect_value is not None
            or node.reflect_interest is not None
            or node.reflect_difficulty is not None)


# Cell styles reused across rows. Muted-grey is the Subtasks-table convention
# for non-name secondary text; full-light is for the Name column.
_CELL_PRIMARY = {"verticalAlign": "middle"}
_CELL_MUTED = {"verticalAlign": "middle", "color": "#6c757d"}


def _build_history_table(nodes):
    """Render the Review History as a `dbc.Table` matching the Details tab's
    Subtasks-table style. Edit ✎ buttons carry pattern-matched ids so the
    edit-handoff callback can resolve which row was clicked directly from
    `ctx.triggered_id`."""
    if not nodes:
        return html.Div(
            html.P("No matching reflections.",
                   className="text-muted mb-0"),
            className="text-center py-3",
        )

    rows = []
    for node in nodes:
        est_hours = getattr(node, 'time', 0) or 0
        act_hours = node.actual_time_point
        edit_id = {'type': 'hub-history-edit', 'index': node.name}
        rows.append(html.Tr([
            html.Td(node.name, style=_CELL_PRIMARY),
            html.Td(_fmt_hours(est_hours) if est_hours > 0 else _DASH,
                    style=_CELL_MUTED),
            html.Td(_fmt_hours(act_hours), style=_CELL_MUTED),
            html.Td(_fmt_delta_hours(act_hours, est_hours), style=_CELL_MUTED),
            html.Td(_fmt_vie_tuple(node.value, node.interest, node.difficulty),
                    style=_CELL_MUTED),
            html.Td(_fmt_vie_tuple(node.reflect_value, node.reflect_interest,
                                   node.reflect_difficulty),
                    style=_CELL_MUTED),
            html.Td(_fmt_vie_delta(node.reflect_value, node.reflect_interest,
                                   node.reflect_difficulty,
                                   node.value, node.interest, node.difficulty),
                    style=_CELL_MUTED),
            html.Td(
                dbc.Button("✎", id=edit_id, color="link", size="sm",
                           className="p-0 text-decoration-none text-muted",
                           style={"fontSize": "1.1rem", "lineHeight": "1"}),
                style={"verticalAlign": "middle", "width": "32px"},
            ),
        ]))

    # `--bs-table-bg: transparent` removes the dark grey row tint that
    # Bootstrap's Darkly theme paints on every <td>. Subtasks table reads
    # cleaner because its background falls through to the modal/canvas
    # surface; matching that here.
    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Name"),
                html.Th("Est Time"),
                html.Th("Actual"),
                html.Th("Δ Time"),
                html.Th("Est V/I/E"),
                html.Th("Act V/I/E"),
                html.Th("Δ V/I/E"),
                html.Th(""),
            ])),
            html.Tbody(rows),
        ],
        bordered=False, hover=True, responsive=True, size="sm",
        className="text-light",
        style={"fontSize": "0.82rem", "--bs-table-bg": "transparent"},
    )


def _filter_history_nodes(nodes, search, ctx_filter, subctx_filter):
    """Apply search + context + subcontext filters (AND across all).

    `subctx_filter` values use the same `ctx\x1fsub` encoding as the main
    filter sidebar so the dropdown options can be reused as-is.
    """
    if search:
        s = search.strip().lower()
        if s:
            nodes = [n for n in nodes if s in n.name.lower()]
    if ctx_filter:
        ctx_set = set(ctx_filter)
        nodes = [n for n in nodes if n.context in ctx_set]
    if subctx_filter:
        pairs = set()
        for v in subctx_filter:
            if isinstance(v, str) and '\x1f' in v:
                c, s = v.split('\x1f', 1)
                pairs.add((c, s or None))
        nodes = [n for n in nodes
                 if (n.context, n.subcontext or None) in pairs]
    return nodes


def register_review_hub_callbacks(app):
    # --- Toggle the hub modal from the toolbar's clock-history icon ---
    # The button used to launch the focused-review queue directly; that
    # behavior now lives behind the hub's "Start review" button. Clicking the
    # toolbar icon just opens the hub.
    @app.callback(
        Output('modal-review-hub', 'is_open'),
        Input('btn-calibration-review', 'n_clicks'),
        State('modal-review-hub', 'is_open'),
        prevent_initial_call=True,
    )
    def toggle_review_hub(n_clicks, is_open):
        if not n_clicks:
            return no_update
        return not is_open

    # --- Refresh the Pending tab's count when the hub opens ---
    # Reuses _calibration_review_queue from callbacks.py (the same function
    # the queue-launch callback uses) so the count is always consistent with
    # what "Start review" would actually iterate through.
    @app.callback(
        Output('hub-pending-count', 'children'),
        Input('modal-review-hub', 'is_open'),
        prevent_initial_call=False,
    )
    def refresh_pending_count(is_open):
        if not is_open:
            return no_update
        from callbacks import _calibration_review_queue
        return str(len(_calibration_review_queue(_manager)))

    # --- Excluded tab: populate when the hub opens ---
    # Lifted from settings_callbacks.load_calibration_dismissed_list with the
    # Settings collapse / toggle-label outputs dropped — the Hub's dbc.Tab
    # provides the collapse equivalent and the count is implicit in the list
    # itself.
    @app.callback(
        Output('hub-excluded-list', 'children'),
        Input('modal-review-hub', 'is_open'),
        prevent_initial_call=True,
    )
    def load_calibration_dismissed_list(is_open):
        if not is_open:
            return no_update
        return build_calibration_dismissed_view(_manager)

    # --- Excluded tab: restore a dismissed node ---
    # Pattern-matched id matches build_calibration_dismissed_view's emitted
    # buttons. Re-renders the list in place so a single click visibly removes
    # the row.
    @app.callback(
        Output('hub-excluded-list', 'children', allow_duplicate=True),
        Input({'type': 'calibration-restore', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_calibration_node(clicks):
        trig = ctx.triggered_id
        if not trig or not any(c for c in clicks if c):
            return no_update
        node = _manager.get_node(trig['index'])
        if node and node.calibration_dismissed:
            node.calibration_dismissed = 0
            _manager.update_node(node)
        return build_calibration_dismissed_view(_manager)

    # --- History tab: subcontext-filter options track the context filter ---
    # Mirrors the main filter sidebar's pattern at sidebars_layout.build_filters_content.
    # Subcontexts are encoded as "ctx\x1fsub" (ASCII unit-separator) because
    # Dash dropdowns mangle "::" — matches the sidebar's encoding so the same
    # _filter_history_nodes parsing works.
    @app.callback(
        Output('hub-history-filter-subcontext', 'options'),
        Output('hub-history-filter-subcontext', 'value'),
        Input('hub-history-filter-context', 'value'),
        State('hub-history-filter-subcontext', 'value'),
    )
    def update_history_subcontext_options(selected_contexts, current_subs):
        if not selected_contexts:
            return [], []
        all_subs = ConfigManager.get_subcontexts()
        multi = len(selected_contexts) > 1
        options = []
        for c in selected_contexts:
            none_label = f"{c} > None" if multi else "None"
            options.append({"label": none_label, "value": f"{c}\x1f"})
            for s in sort_subcontexts(all_subs.get(c, [])):
                label = f"{c} > {s}" if multi else s
                options.append({"label": label, "value": f"{c}\x1f{s}"})
        valid = {o["value"] for o in options}
        new_value = [v for v in (current_subs or []) if v in valid]
        return options, new_value

    # --- History tab: rebuild the table on open, tab switch, or filter change ---
    @app.callback(
        Output('hub-history-table-container', 'children'),
        Input('modal-review-hub', 'is_open'),
        Input('review-hub-tabs', 'active_tab'),
        Input('hub-history-search', 'value'),
        Input('hub-history-filter-context', 'value'),
        Input('hub-history-filter-subcontext', 'value'),
        prevent_initial_call=True,
    )
    def populate_review_history(is_open, _active_tab, search,
                                ctx_filter, subctx_filter):
        if not is_open:
            return no_update
        # Only nodes that are *currently* Done belong in History. The
        # reflect_*/actual_time_* columns persist when a node is un-marked
        # Done (so re-completing restores the reflection), so _node_has_actuals
        # alone would keep stale rows for nodes the user reverted to Open.
        nodes = [n for n in _manager.get_all_nodes(include_dormant=True)
                 if n.status == STATUS_DONE and _node_has_actuals(n)]
        nodes = _filter_history_nodes(nodes, search, ctx_filter, subctx_filter)
        # Most-recent-first by done_date; undated rows go to the bottom in
        # name order so the table stays scannable even before any node has
        # been Now-flipped.
        dated = [n for n in nodes if n.done_date]
        undated = [n for n in nodes if not n.done_date]
        dated.sort(key=lambda n: n.done_date, reverse=True)
        undated.sort(key=lambda n: n.name.lower())
        return _build_history_table(dated + undated)

    # --- History tab: open the focused-review modal in 'edit' mode ---
    # Triggered by clicking any row's ✎ button — pattern-matched id carries
    # the node name in `ctx.triggered_id['index']`. Hands off to the
    # focused-review modal with the node's existing reflect_* /
    # actual_time_* values pre-filled (not the formula-based defaults,
    # because we're editing what's already recorded).
    @app.callback(
        Output('modal-review-hub', 'is_open', allow_duplicate=True),
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('time-calibration-title', 'children', allow_duplicate=True),
        Output('time-calibration-reference', 'children', allow_duplicate=True),
        Output('time-calibration-lower', 'value', allow_duplicate=True),
        Output('time-calibration-point', 'value', allow_duplicate=True),
        Output('time-calibration-upper', 'value', allow_duplicate=True),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('calibration-value', 'value', allow_duplicate=True),
        Output('calibration-interest', 'value', allow_duplicate=True),
        Output('calibration-difficulty', 'value', allow_duplicate=True),
        Input({'type': 'hub-history-edit', 'index': ALL}, 'n_clicks'),
        prevent_initial_call=True,
    )
    def open_calibration_from_history(clicks):
        trig = ctx.triggered_id
        if not trig or not any(c for c in clicks if c):
            return (no_update,) * 12
        node_name = trig.get('index') if isinstance(trig, dict) else None
        node = _manager.get_node(node_name) if node_name else None
        if not node:
            return (no_update,) * 12

        # Modal copy reuses the same helper as the queue / single flows.
        from callbacks import _calibration_modal_text, _calibration_unit_for
        title, reference = _calibration_modal_text(node)

        # Display unit matches the actuals' magnitude (e.g. "2.8w" instead of
        # "56h") so the Best Estimate field reads in the same friendly units
        # as the reference text above it. Falls back to the stored unit only
        # when no actual-time datapoint exists.
        anchor_hours = (node.actual_time_point
                        if node.actual_time_point is not None
                        else node.actual_time_lower
                        if node.actual_time_lower is not None
                        else node.actual_time_upper)
        if anchor_hours is not None:
            unit = _calibration_unit_for(anchor_hours)
        else:
            unit = node.actual_time_unit or 'hours'
        mult = ConfigManager.get_time_multiplier(unit)
        def _from_hours(h):
            if h is None or mult == 0:
                return None
            return round(h / mult, 2)
        time_lower = _from_hours(node.actual_time_lower)
        time_point = _from_hours(node.actual_time_point)
        time_upper = _from_hours(node.actual_time_upper)

        # Sliders fall back to the node's estimate when the reflect column is
        # NULL — covers partially-rated history rows (time-only entries from
        # before V/I/E was wired) without exposing 0/None as a default.
        val = node.reflect_value if node.reflect_value is not None else (node.value or 5)
        interest = node.reflect_interest if node.reflect_interest is not None else (node.interest or 5)
        diff = node.reflect_difficulty if node.reflect_difficulty is not None else (node.difficulty or 5)

        store = {'mode': 'edit', 'node': node_name}
        return (False, True, store, title, reference,
                time_lower, time_point, time_upper, unit,
                int(val), int(interest), int(diff))
