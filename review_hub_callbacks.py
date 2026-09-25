"""Callbacks for the Reflection modal.

Owns open/close wiring, the Pending tab's live count, the Excluded tab's
list + restore controls (moved here from settings_callbacks), and the
Review History table + filters + edit hand-off.
"""

from dash import Input, Output, State, ALL, ctx, no_update, html
import dash_bootstrap_components as dbc

from config import ConfigManager
from ui_kit import Tooltip
from graph_manager import GraphManager
from callback_helpers import build_calibration_dismissed_view
import style_tokens as tokens
from models import STATUS_DONE
from review_hub_layout import (
    HISTORY_SORT_CRITERIA,
    HISTORY_SORT_DEFAULT,
    HISTORY_SORT_DEFAULT_DIRECTION,
    HISTORY_SORT_DIRECTION_LABELS,
    history_sort_direction_icon,
    history_sort_key_class,
)


_manager = GraphManager()


# Sentinel string for missing comparisons in the History table.
_DASH = "—"
_HISTORY_BATCH_SIZE = 20
_EXCLUDED_BATCH_SIZE = 20
# Every criterion but "completed" has a column header.
_SORT_COLUMNS = {key: label for key, label in HISTORY_SORT_CRITERIA.items()
                 if key != "completed"}


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
    """Signed per-dimension Δ V/I/E. DASH if either tuple is incomplete."""
    if any(v is None for v in (av, ai, ad, ev, ei, ed)):
        return _DASH

    def _signed(actual, est):
        diff = int(actual) - int(est)
        if diff == 0:
            return "0"
        return f"+{diff}" if diff > 0 else f"−{abs(diff)}"

    return f"{_signed(av, ev)}/{_signed(ai, ei)}/{_signed(ad, ed)}"


def _rating_change_magnitude(node):
    """Total absolute V/I/E change, or None for an incomplete comparison."""
    pairs = (
        (node.reflect_value, node.value),
        (node.reflect_interest, node.interest),
        (node.reflect_difficulty, node.difficulty),
    )
    if any(actual is None or estimated is None for actual, estimated in pairs):
        return None
    return sum(abs(int(actual) - int(estimated)) for actual, estimated in pairs)


def _history_sort_value(node, key):
    estimate = node.time
    if key == "name":
        return node.name.casefold()
    if key == "estimated":
        return estimate if estimate > 0 else None
    if key == "actual":
        return node.actual_time_point
    if key == "delta_time":
        return (node.actual_time_point - estimate
                if node.actual_time_point is not None and estimate > 0 else None)
    if key == "delta_ratings":
        return _rating_change_magnitude(node)
    return None


def _sort_history_nodes(nodes, sort):
    """Keep missing values last for both directions; use name for ties."""
    key = (sort or {}).get("key", "completed")
    direction = (sort or {}).get("direction", "desc")
    if key not in _SORT_COLUMNS:
        dated = [node for node in nodes if node.done_date]
        undated = [node for node in nodes if not node.done_date]
        dated.sort(key=lambda node: node.name.casefold())
        dated.sort(key=lambda node: node.done_date, reverse=direction == "desc")
        undated.sort(key=lambda node: node.name.casefold())
        return dated + undated

    valid = [node for node in nodes if _history_sort_value(node, key) is not None]
    missing = [node for node in nodes if _history_sort_value(node, key) is None]
    valid.sort(key=lambda node: node.name.casefold())
    valid.sort(key=lambda node: _history_sort_value(node, key),
               reverse=direction == "desc")
    missing.sort(key=lambda node: node.name.casefold())
    return valid + missing


def _next_history_sort(trigger, current, *, is_open=True, column_clicks=None,
                       chosen_key=None, direction_clicks=None):
    """The sort after one control fires, or None when nothing changes.

    Choosing a criterion starts it in its default direction. Clicking the
    active column's header, or the direction button, reverses the order.
    """
    current = current or HISTORY_SORT_DEFAULT
    reversed_direction = 'asc' if current.get('direction') == 'desc' else 'desc'
    if trigger == 'modal-review-hub':
        return dict(HISTORY_SORT_DEFAULT) if is_open else None
    if trigger == 'hub-history-sort-direction':
        if not direction_clicks:
            return None
        return {'key': current.get('key', 'completed'), 'direction': reversed_direction}
    if trigger == 'hub-history-sort-key':
        # The echo from our own output lands here too; it changes nothing.
        if chosen_key not in HISTORY_SORT_CRITERIA or chosen_key == current.get('key'):
            return None
        return {'key': chosen_key,
                'direction': HISTORY_SORT_DEFAULT_DIRECTION[chosen_key]}
    if not isinstance(trigger, dict) or not any(column_clicks or []):
        return None
    key = trigger.get('index')
    if key not in _SORT_COLUMNS:
        return None
    if current.get('key') == key:
        return {'key': key, 'direction': reversed_direction}
    return {'key': key, 'direction': HISTORY_SORT_DEFAULT_DIRECTION[key]}


def _visible_history_count(trigger, current, total):
    """Reveal a fresh first batch after filters, otherwise advance by one."""
    if trigger in ('modal-review-hub', 'hub-history-search',
                   'hub-history-filter-context',
                   'hub-history-filter-subcontext'):
        wanted = _HISTORY_BATCH_SIZE
    elif trigger == 'hub-history-show-more':
        wanted = (current or _HISTORY_BATCH_SIZE) + _HISTORY_BATCH_SIZE
    else:
        wanted = current or _HISTORY_BATCH_SIZE
    return min(wanted, total)


def _visible_excluded_count(trigger, current, total):
    if trigger == 'modal-review-hub':
        wanted = _EXCLUDED_BATCH_SIZE
    elif trigger == 'hub-excluded-show-more':
        wanted = (current or _EXCLUDED_BATCH_SIZE) + _EXCLUDED_BATCH_SIZE
    else:
        wanted = current or _EXCLUDED_BATCH_SIZE
    return min(wanted, total)


def _history_sort_heading(key, sort):
    active = (sort or {}).get("key") == key
    direction = (sort or {}).get("direction", "asc")
    label = _SORT_COLUMNS[key]
    default_direction = HISTORY_SORT_DEFAULT_DIRECTION[key]
    next_direction = ("asc" if direction == "desc" else "desc") if active else default_direction
    aria_sort = ("ascending" if direction == "asc" else "descending") if active else "none"
    children = [label, html.Span(f", sort {next_direction}ending",
                                 className="visually-hidden")]
    if active:
        children.append(html.I(
            className=("bi bi-caret-down-fill" if direction == "desc"
                       else "bi bi-caret-up-fill") + " ms-1",
            **{"aria-hidden": "true"}))
    button = dbc.Button(children,
                        id={"type": "hub-history-sort-column", "index": key},
                        color="link", className="review-history-sort-btn")
    heading = html.Th(button,
                      className=f"review-history-heading review-history-heading-{key}",
                      **{"aria-sort": aria_sort})
    if key == "delta_ratings":
        return html.Th([button, Tooltip(
            "Value / Interest / Effort. Sorted by total absolute change.",
            target={"type": "hub-history-sort-column", "index": key},
            trigger="hover focus",
        )], className="review-history-heading review-history-heading-delta_ratings",
            **{"aria-sort": aria_sort})
    return heading


def _node_has_actuals(node):
    """True when the node carries any captured-actual datapoint —
    qualifies it for the History tab regardless of dismissed flag."""
    return (node.actual_time_lower is not None
            or node.actual_time_point is not None
            or node.actual_time_upper is not None
            or node.reflect_value is not None
            or node.reflect_interest is not None
            or node.reflect_difficulty is not None)


# These were the app's only named cell-style constants, but being
# module-local they could not stop the Details and Events tables from
# re-inlining their own copies. Now shared; see style_tokens.
_CELL_PRIMARY = tokens.CELL_PRIMARY
_CELL_MUTED = tokens.CELL_MUTED


def _build_history_table(nodes, sort=None, empty_message="No matching reflections."):
    """Render the Review History as a `dbc.Table` matching the Details tab's
    Subtasks-table style. Edit buttons carry pattern-matched ids so the
    edit-handoff callback can resolve which row was clicked directly from
    `ctx.triggered_id`."""
    if not nodes:
        return html.Div(
            html.P(empty_message,
                   className="text-muted mb-0"),
            className="text-center py-3",
        )

    rows = []
    for node in nodes:
        est_hours = getattr(node, 'time', 0) or 0
        act_hours = node.actual_time_point
        name_id = {'type': 'hub-history-name', 'index': node.name}
        ratings_id = {'type': 'hub-history-ratings', 'index': node.name}
        estimated_ratings = _fmt_vie_tuple(node.value, node.interest, node.difficulty)
        actual_ratings = _fmt_vie_tuple(node.reflect_value, node.reflect_interest,
                                        node.reflect_difficulty)
        edit_id = {'type': 'hub-history-edit', 'index': node.name}
        edit_action = html.Div([
            dbc.Button(
                [
                    html.I(className="bi bi-pencil", **{"aria-hidden": "true"}),
                    html.Span(f"Edit reflection for {node.name}",
                              className="visually-hidden"),
                ],
                id=edit_id,
                color="link",
                className="review-history-edit-btn",
            ),
            Tooltip(
                "Edit reflection",
                target=edit_id,
                placement="left",
            ),
        ], className="review-history-actions")
        rows.append(html.Tr([
            html.Td([
                html.Span(node.name, id=name_id, tabIndex=0,
                          className="review-history-name"),
                Tooltip(node.name, target=name_id, trigger="hover focus"),
            ], className="review-history-name-cell", style=_CELL_PRIMARY),
            html.Td(_fmt_hours(est_hours) if est_hours > 0 else _DASH,
                    style=_CELL_MUTED),
            html.Td(_fmt_hours(act_hours), style=_CELL_MUTED),
            html.Td(_fmt_delta_hours(act_hours, est_hours), style=_CELL_MUTED),
            html.Td([
                html.Span(_fmt_vie_delta(
                    node.reflect_value, node.reflect_interest,
                    node.reflect_difficulty,
                    node.value, node.interest, node.difficulty),
                    id=ratings_id, tabIndex=0, className="review-history-rating"),
                Tooltip(f"Estimated V/I/E: {estimated_ratings} · "
                        f"Actual V/I/E: {actual_ratings}",
                        target=ratings_id, trigger="hover focus"),
            ], style=_CELL_MUTED),
            html.Td(edit_action,
                    style={"verticalAlign": "middle", "width": "32px"}),
        ], className="review-history-row"))

    # `--bs-table-bg: transparent` removes the dark grey row tint that
    # Bootstrap's Darkly theme paints on every <td>. Subtasks table reads
    # cleaner because its background falls through to the modal/canvas
    # surface; matching that here.
    return dbc.Table(
        [
            html.Thead(html.Tr([
                *[_history_sort_heading(key, sort)
                  for key in _SORT_COLUMNS],
                html.Th(""),
            ])),
            html.Tbody(rows),
        ],
        **tokens.TABLE_PROPS,
        className=f"review-history-table {tokens.TABLE_CLASS}",
        style=tokens.TABLE_STYLE,
    )


def _filter_history_nodes(nodes, search, ctx_filter, subctx_filter):
    """Apply search + context + subcontext filters (AND across all).

    `subctx_filter` values use the same `ctx\x1fsub` encoding as the main
    filter sidebar. As there, a selected context with no subcontext picks
    keeps all of its nodes ("all Health, but only STEM › Math").
    """
    if search:
        s = search.strip().lower()
        if s:
            nodes = [n for n in nodes if s in n.name.lower()]
    if ctx_filter:
        ctx_set = set(ctx_filter)
        nodes = [n for n in nodes if n.context in ctx_set]
    if subctx_filter:
        picks = {}
        for v in subctx_filter:
            if isinstance(v, str) and '\x1f' in v:
                c, s = v.split('\x1f', 1)
                picks.setdefault(c, set()).add(s or None)
        nodes = [n for n in nodes
                 if n.context not in picks
                 or (n.subcontext or None) in picks[n.context]]
    return nodes


def register_review_hub_callbacks(app, services=None):
    _manager = services.graph if services is not None else globals()['_manager']
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
    # Reuses _calibration_review_queue from editor_values.py (the same function
    # the queue-launch callback uses) so the count is always consistent with
    # what "Start review" would actually iterate through.
    @app.callback(
        Output('hub-pending-count', 'children'),
        Output('hub-pending-summary', 'style'),
        Output('hub-pending-empty', 'style'),
        Output('btn-hub-pending-launch', 'style'),
        Input('modal-review-hub', 'is_open'),
        Input('hub-excluded-list', 'children'),
        prevent_initial_call=True,
    )
    def refresh_pending_count(is_open, _excluded_list):
        if not is_open:
            return (no_update,) * 4
        from editor_values import _calibration_review_queue
        count = len(_calibration_review_queue(_manager))
        shown = {"display": "block"}
        hidden = {"display": "none"}
        return str(count), (shown if count else hidden), (hidden if count else shown), (shown if count else hidden)

    # --- Excluded tab: load, reveal more, and restore in one callback ---
    @app.callback(
        Output('hub-excluded-list', 'children'),
        Output('hub-excluded-page-status', 'children'),
        Output('hub-excluded-pager', 'style'),
        Output('hub-excluded-more-wrap', 'style'),
        Output('hub-excluded-visible-count', 'data'),
        Input('modal-review-hub', 'is_open'),
        Input('hub-excluded-show-more', 'n_clicks'),
        Input({'type': 'calibration-restore', 'index': ALL}, 'n_clicks'),
        State('hub-excluded-visible-count', 'data'),
        prevent_initial_call=True,
    )
    def populate_excluded_list(is_open, _more_clicks, restore_clicks,
                               visible_count):
        if not is_open:
            return (no_update,) * 5
        trigger = ctx.triggered_id
        if isinstance(trigger, dict) and any(restore_clicks or []):
            node = _manager.get_node(trigger['index'])
            if node and node.calibration_dismissed:
                node.calibration_dismissed = 0
                _manager.update_node(node)
        dismissed = sorted(n.name for n in _manager.get_all_nodes(include_dormant=True)
                           if n.calibration_dismissed)
        total = len(dismissed)
        limit = _visible_excluded_count(trigger, visible_count, total)
        view, _ = build_calibration_dismissed_view(dismissed, limit=limit)
        noun = 'node' if total == 1 else 'nodes'
        return (view, f'Showing {limit} of {total} {noun}' if total else '',
                {'display': 'flex'} if total else {'display': 'none'},
                {'display': 'inline'} if limit < total else {'display': 'none'},
                limit)

    # --- History tab: sortable, progressively revealed results ---
    # The dropdown, the direction button and the column headers all write the
    # one sort store, and this callback also echoes the result back into the
    # dropdown and the button so a header click keeps them in step.
    @app.callback(
        Output('hub-history-sort', 'data'),
        Output('hub-history-sort-key', 'value'),
        Output('hub-history-sort-key', 'className'),
        Output('hub-history-sort-direction-icon', 'className'),
        Output('hub-history-sort-direction-tooltip', 'children'),
        Input('modal-review-hub', 'is_open'),
        Input({'type': 'hub-history-sort-column', 'index': ALL}, 'n_clicks'),
        Input('hub-history-sort-key', 'value'),
        Input('hub-history-sort-direction', 'n_clicks'),
        State('hub-history-sort', 'data'),
        prevent_initial_call=True,
    )
    def update_history_sort(is_open, clicks, chosen_key, direction_clicks,
                            current_sort):
        sort = _next_history_sort(ctx.triggered_id, current_sort, is_open=is_open,
                                  column_clicks=clicks, chosen_key=chosen_key,
                                  direction_clicks=direction_clicks)
        if sort is None:
            return (no_update,) * 5
        return (sort, sort['key'], history_sort_key_class(sort),
                history_sort_direction_icon(sort['direction']),
                HISTORY_SORT_DIRECTION_LABELS[sort['key']][sort['direction']])

    @app.callback(
        Output('hub-history-table-container', 'children'),
        Output('hub-history-page-status', 'children'),
        Output('hub-history-pager', 'style'),
        Output('hub-history-more-wrap', 'style'),
        Output('hub-history-visible-count', 'data'),
        Input('modal-review-hub', 'is_open'),
        Input('review-hub-tabs', 'active_tab'),
        Input('hub-history-search', 'value'),
        Input('hub-history-filter-context', 'value'),
        Input('hub-history-filter-subcontext', 'value'),
        Input('hub-history-sort', 'data'),
        Input('hub-history-show-more', 'n_clicks'),
        State('hub-history-visible-count', 'data'),
        prevent_initial_call=True,
    )
    def populate_review_history(is_open, _active_tab, search,
                                ctx_filter, subctx_filter, sort, _more_clicks,
                                visible_count):
        if not is_open:
            return (no_update,) * 5
        # Only nodes that are *currently* Done belong in History. The
        # reflect_*/actual_time_* columns persist when a node is un-marked
        # Done (so re-completing restores the reflection), so _node_has_actuals
        # alone would keep stale rows for nodes the user reverted to Open.
        history = [n for n in _manager.get_all_nodes(include_dormant=True)
                   if n.status == STATUS_DONE and _node_has_actuals(n)]
        nodes = _filter_history_nodes(history, search, ctx_filter, subctx_filter)
        nodes = _sort_history_nodes(nodes, sort)
        if not nodes:
            message = ('No reflections yet.' if not history
                       else 'No matching reflections.')
            return (_build_history_table([], sort, message), '',
                    {'display': 'none'}, {'display': 'none'},
                    _HISTORY_BATCH_SIZE)

        limit = _visible_history_count(ctx.triggered_id, visible_count,
                                       len(nodes))
        noun = 'reflection' if len(nodes) == 1 else 'reflections'
        status = f'Showing {limit} of {len(nodes)} {noun}'
        more_style = ({'display': 'inline'} if limit < len(nodes)
                      else {'display': 'none'})
        return (_build_history_table(nodes[:limit], sort), status,
                {'display': 'flex'}, more_style, limit)

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
        from editor_values import _calibration_modal_text, _calibration_unit_for
        title, reference = _calibration_modal_text(node)
        estimated_ratings = _fmt_vie_tuple(node.value, node.interest,
                                           node.difficulty)
        if estimated_ratings != _DASH:
            reference = [reference, html.Br(),
                         f"Estimated ratings (V/I/E): {estimated_ratings}"]

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
