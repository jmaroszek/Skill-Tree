"""Callbacks for the Review Hub modal.

Owns open/close wiring, the Pending tab's live count, the Excluded tab's
list + restore controls (moved here from settings_callbacks), and (later)
the Review History DataTable.
"""

from dash import Input, Output, State, ALL, ctx, no_update

from config import ConfigManager
from graph_manager import GraphManager
from callback_helpers import build_calibration_dismissed_view


_manager = GraphManager()


# Sentinel string for missing-actual cells in the History table.
_DASH = "—"

# DataTable column ids — kept here so the populate callback and the
# Phase-6 edit handler agree on the schema. `_edit` is the sentinel column
# the user clicks to open the focused-review modal in edit mode.
HISTORY_COLUMNS = [
    {"name": "Name", "id": "name"},
    {"name": "Done", "id": "done_date"},
    {"name": "Est Time", "id": "est_time", "type": "numeric"},
    {"name": "Actual", "id": "act_time", "type": "numeric"},
    {"name": "Δ Time", "id": "delta_time", "type": "numeric"},
    {"name": "Est V/I/E", "id": "est_vie"},
    {"name": "Act V/I/E", "id": "act_vie"},
    {"name": "Δ V/I/E", "id": "delta_vie"},
    {"name": "", "id": "_edit"},
]


def _fmt_hours(hours):
    """Friendly time for the table — empty string for missing."""
    if hours is None:
        return _DASH
    return ConfigManager.format_time_friendly(hours)


def _fmt_delta_hours(actual, estimate):
    """Signed friendly time delta. Returns DASH if either side is missing."""
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

    # --- History tab: populate the DataTable when the hub opens ---
    # Also re-fires on tab switch so an edit in another tab (Phase 6) is
    # reflected when the user returns. Builds the row-to-name map in
    # `hub-history-store` so the edit-click handler can resolve the clicked
    # row back to a node (DataTable's active_cell carries indices, not
    # row content).
    @app.callback(
        Output('hub-history-table', 'data'),
        Output('hub-history-table', 'columns'),
        Output('hub-history-store', 'data'),
        Input('modal-review-hub', 'is_open'),
        Input('review-hub-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def populate_review_history(is_open, _active_tab):
        if not is_open:
            return no_update, no_update, no_update
        rows = []
        for node in _manager.get_all_nodes(include_dormant=True):
            if not _node_has_actuals(node):
                continue
            est_hours = getattr(node, 'time', 0) or 0
            act_hours = node.actual_time_point
            rows.append({
                "name": node.name,
                "done_date": node.done_date or _DASH,
                "est_time": _fmt_hours(est_hours) if est_hours > 0 else _DASH,
                "act_time": _fmt_hours(act_hours),
                "delta_time": _fmt_delta_hours(act_hours, est_hours),
                "est_vie": _fmt_vie_tuple(node.value, node.interest, node.difficulty),
                "act_vie": _fmt_vie_tuple(node.reflect_value, node.reflect_interest,
                                          node.reflect_difficulty),
                "delta_vie": _fmt_vie_delta(node.reflect_value, node.reflect_interest,
                                            node.reflect_difficulty,
                                            node.value, node.interest, node.difficulty),
                "_edit": "✎",
            })
        # Most-recent-first by done_date; nodes without a done_date go to the
        # bottom (ISO strings sort lexicographically — DASH sentinel sorts
        # before digits, so flip to push it to the tail).
        rows.sort(key=lambda r: (r["done_date"] == _DASH, r["done_date"]),
                  reverse=False)
        # Reverse the date-sorted portion so most recent is first while
        # DASH rows stay at the end. Simpler: pull DASH rows aside, sort the
        # rest desc, append DASH rows.
        dated = [r for r in rows if r["done_date"] != _DASH]
        undated = [r for r in rows if r["done_date"] == _DASH]
        dated.sort(key=lambda r: r["done_date"], reverse=True)
        rows = dated + undated
        store = {str(i): r["name"] for i, r in enumerate(rows)}
        return rows, HISTORY_COLUMNS, store

    # --- History tab: open the focused-review modal in 'edit' mode ---
    # Triggered by clicking the sentinel "✎" cell on any History row. Resolves
    # the row index → node name via `derived_virtual_data` (DataTable's
    # post-sort/filter/page view), then hands off to the focused-review modal
    # with the node's existing reflect_* / actual_time_* values pre-filled —
    # NOT the formula-based defaults, because we're editing what's already
    # recorded.
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
        Input('hub-history-table', 'active_cell'),
        State('hub-history-table', 'derived_virtual_data'),
        prevent_initial_call=True,
    )
    def open_calibration_from_history(active_cell, derived_data):
        if not active_cell or active_cell.get('column_id') != '_edit':
            return (no_update,) * 12
        row_idx = active_cell.get('row')
        if not isinstance(derived_data, list) or row_idx is None:
            return (no_update,) * 12
        if row_idx < 0 or row_idx >= len(derived_data):
            return (no_update,) * 12
        node_name = derived_data[row_idx].get('name')
        node = _manager.get_node(node_name) if node_name else None
        if not node:
            return (no_update,) * 12

        # Modal copy reuses the same helper as the queue / single flows.
        from callbacks import _calibration_modal_text
        title, reference = _calibration_modal_text(node)

        # Convert canonical-hours actuals back into the stored display unit so
        # the user sees what they entered, not the internal representation.
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
