"""The time-calibration and reflection modal.

It opens three ways, each named by the 'mode' in time-calibration-pending-store:
after one completion (core_engine opens it), as a review of completed nodes
(the Review Hub's Start review), or to edit an earlier answer (the Hub's
History tab). Its helpers are in editor_values.
"""
from dash import html, Input, Output, State, no_update

import style_tokens as tokens
from callback_helpers import get_trigger_id
from config import ConfigManager
from editor_values import (_calibration_modal_text, _calibration_prepop,
                           _calibration_review_queue, _calibration_unit_for)
from graph_manager import GraphManager
from prerender import prerendered

graph_manager = GraphManager()


def register_calibration_callbacks(app, services=None):
    """Register the calibration modal's callbacks: answer, review, and chrome."""
    manager = services.graph if services is not None else graph_manager

    # --- Time-Calibration Modal: Submit / Skip / Don't ask again ---
    # The modal serves three flows, distinguished by the 'mode' in
    # time-calibration-pending-store:
    #   'single' — opened by core_engine after one explicit completion.
    #   'review' — opened by the review-launch callback; cycles a queue of
    #              completed nodes, advancing on each Submit/Skip/Dismiss.
    #   'edit'   — opened by review_hub_callbacks.open_calibration_from_history
    #              for editing an already-rated node. Same write semantics as
    #              'single'; on close, re-opens the hub on the History tab.
    # Submit writes actual_time_* (canonical hours) AND reflect_value/
    # interest/difficulty; Skip leaves all four dimensions NULL; "Don't ask
    # again" sets calibration_dismissed without touching the rating columns.
    # Inputs reset between nodes; pre_populate_calibration_inputs (driven by
    # the store) replaces the reset with node-specific defaults.
    @app.callback(
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('save-output', 'children', allow_duplicate=True),
        Output('time-calibration-lower', 'value'),
        Output('time-calibration-point', 'value'),
        Output('time-calibration-upper', 'value'),
        Output('time-calibration-unit', 'value'),
        Output('calibration-value', 'value'),
        Output('calibration-interest', 'value'),
        Output('calibration-difficulty', 'value'),
        Output('calibration-notes', 'value'),
        Output('time-calibration-reference', 'children', allow_duplicate=True),
        Output('calibration-review-progress', 'value', allow_duplicate=True),
        Output('calibration-review-progress', 'label', allow_duplicate=True),
        Output('time-calibration-complete', 'children', allow_duplicate=True),
        Output('time-calibration-title', 'children', allow_duplicate=True),
        Output('modal-review-hub', 'is_open', allow_duplicate=True),
        Output('review-hub-tabs', 'active_tab', allow_duplicate=True),
        Input('btn-time-calibration-submit', 'n_clicks'),
        Input('btn-time-calibration-skip', 'n_clicks'),
        Input('btn-time-calibration-dismiss', 'n_clicks'),
        State('time-calibration-lower', 'value'),
        State('time-calibration-point', 'value'),
        State('time-calibration-upper', 'value'),
        State('time-calibration-unit', 'value'),
        State('calibration-value', 'value'),
        State('calibration-interest', 'value'),
        State('calibration-difficulty', 'value'),
        State('calibration-notes', 'value'),
        State('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def handle_time_calibration(_submit, _skip, _dismiss, lower, point, upper,
                                unit, val, interest, diff, notes, pending):
        # cleared inputs for the next node: 4 time slots + 3 V/I/E sliders + notes
        reset = (None, None, None, 'hours', 5, 5, 5, '')
        trig = get_trigger_id()
        pending = pending if isinstance(pending, dict) else {}
        mode = pending.get('mode')

        if mode == 'review':
            queue = pending.get('queue', [])
            idx = pending.get('index', 0)
            node_name = queue[idx] if 0 <= idx < len(queue) else None
        elif mode in ('single', 'edit'):
            queue, idx = [], 0
            node_name = pending.get('node')
        else:
            # Stale / no pending node — just close.
            return (False, None, no_update, *reset,
                    no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update)

        node = manager.get_node(node_name) if node_name else None

        # Apply the chosen action to the current node.
        if node is not None:
            if trig == 'btn-time-calibration-submit':
                mult = ConfigManager.get_time_multiplier(unit or 'hours')

                def _to_hours(v):
                    return float(v) * mult if v not in (None, '') else None

                node.actual_time_lower = _to_hours(lower)
                node.actual_time_point = _to_hours(point)
                node.actual_time_upper = _to_hours(upper)
                node.actual_time_unit = unit or 'hours'
                node.reflect_value = int(val) if val is not None else None
                node.reflect_interest = int(interest) if interest is not None else None
                node.reflect_difficulty = int(diff) if diff is not None else None
                node.reflect_notes = (notes or '').strip() or None
                manager.update_node(node)
            elif trig == 'btn-time-calibration-dismiss':
                node.calibration_dismissed = 1
                manager.update_node(node)
            # Skip / Cancel: no write.

        if mode == 'single':
            msg = (f"Logged actuals for '{node.name}'."
                   if (trig == 'btn-time-calibration-submit' and node) else no_update)
            return (False, None, msg, *reset,
                    no_update, no_update, no_update, no_update, no_update,
                    no_update, no_update)

        if mode == 'edit':
            # Submit or Cancel both close the modal and bounce the user back
            # to the History tab. Submit emits a save-output toast so the
            # change is visible even after the hub re-opens.
            msg = (f"Updated actuals for '{node.name}'."
                   if (trig == 'btn-time-calibration-submit' and node) else no_update)
            return (False, None, msg, *reset,
                    no_update, no_update, no_update, no_update, no_update,
                    True, 'tab-review-history')

        # Review mode — advance to the next node, or finish.
        n = len(queue)
        next_idx = idx + 1
        if next_idx < n:
            nxt = manager.get_node(queue[next_idx])
            if nxt is not None:
                next_title, ref = _calibration_modal_text(nxt)
            else:
                next_title, ref = "", ""
            new_store = {'mode': 'review', 'queue': queue, 'index': next_idx}
            human = next_idx + 1  # 1-based node number now showing
            pct = round(human / n * 100)
            next_unit = _calibration_unit_for(nxt.time) if nxt else 'hours'
            return (True, new_store, no_update,
                    None, None, None, next_unit, 5, 5, 5, '',
                    ref, pct, f"{human} / {n}", no_update, next_title,
                    no_update, no_update)
        # Last node done — switch to the completion screen (stays open).
        complete_msg = html.Div([
            html.I(className="bi bi-check-circle text-success",
                   style={"fontSize": tokens.FS_DISPLAY, "lineHeight": "1"},
                   **{"aria-hidden": "true"}),
            html.H5("All caught up", className="mt-2 mb-1"),
            html.P(f"You reflected on {n} completed node(s).",
                   className="text-muted small mb-0"),
        ])
        return (True, {'mode': 'complete'},
                f"Reflection complete — {n} node(s).",
                *reset, no_update, 100, f"{n} / {n}", complete_msg,
                "Reflection complete", no_update, no_update)

    # --- Calibration Review: launch the cycle ---
    # Fired by the "Start review" button inside the Review Hub modal.
    # The toolbar's clock-history icon opens the hub (see
    # review_hub_callbacks.toggle_review_hub); from the hub, this button kicks
    # off the focused-review queue. Output('modal-review-hub', 'is_open') is
    # additionally driven to False so the hub closes as the queue opens — the
    # two modals shouldn't be visible at once.
    @app.callback(
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('time-calibration-reference', 'children', allow_duplicate=True),
        Output('calibration-review-progress', 'value', allow_duplicate=True),
        Output('calibration-review-progress', 'label', allow_duplicate=True),
        Output('calibration-review-toast', 'is_open'),
        Output('calibration-review-toast', 'children'),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('time-calibration-title', 'children', allow_duplicate=True),
        Output('modal-review-hub', 'is_open', allow_duplicate=True),
        Input('btn-hub-pending-launch', 'n_clicks'),
        prevent_initial_call=True,
    )
    def launch_calibration_review(_n):
        queue = _calibration_review_queue(manager)
        if not queue:
            # Leave the hub open so the user sees the toast without losing
            # their place in the hub.
            return (no_update, no_update, no_update, no_update, no_update,
                    True, "All completed nodes are already reflected on or excluded.",
                    no_update, no_update, no_update)
        first = manager.get_node(queue[0])
        title, ref = _calibration_modal_text(first) if first else ("", "")
        store = {'mode': 'review', 'queue': queue, 'index': 0}
        n = len(queue)
        unit = _calibration_unit_for(first.time) if first else 'hours'
        return (True, store, ref, round(1 / n * 100), f"1 / {n}", False,
                no_update, unit, title, False)

    # --- Calibration Review: close the completion screen ---
    @app.callback(
        Output('modal-time-calibration', 'is_open', allow_duplicate=True),
        Input('btn-time-calibration-done', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_calibration_review(_n):
        return False

    # --- Calibration modal chrome: mode-dependent buttons / progress / panels ---
    @app.callback(
        Output('btn-time-calibration-dismiss', 'style'),
        Output('btn-time-calibration-skip', 'style'),
        Output('btn-time-calibration-submit', 'style'),
        Output('btn-time-calibration-done', 'style'),
        Output('calibration-review-progress-wrap', 'style'),
        Output('time-calibration-active', 'style'),
        Output('time-calibration-complete', 'style'),
        Output('btn-time-calibration-skip', 'children'),
        Input('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def _calibration_modal_chrome(pending):
        mode = pending.get('mode') if isinstance(pending, dict) else None
        hide = {"display": "none"}
        if mode == 'complete':
            # Completion screen: only "Done", progress + completion panel.
            return (hide, hide, hide, {}, {}, hide, {}, "Skip")
        if mode == 'review':
            return ({}, {}, {}, hide, {}, {}, hide, "Skip for now")
        if mode == 'edit':
            # Dismiss makes no sense for an already-rated node; Skip is
            # relabeled "Cancel" so the no-write semantic reads as intended.
            return (hide, {}, {}, hide, hide, {}, hide, "Cancel")
        # single (or cleared) — completion-modal layout.
        return (hide, {}, {}, hide, hide, {}, hide, "Skip")

    # --- Calibration modal cleanup: clear state when the modal closes ---
    # Covers the corner-X abort (which closes the modal without firing any
    # footer button) so a half-finished review queue isn't left in the store.
    @app.callback(
        Output('time-calibration-pending-store', 'data', allow_duplicate=True),
        Output('time-calibration-lower', 'value', allow_duplicate=True),
        Output('time-calibration-point', 'value', allow_duplicate=True),
        Output('time-calibration-upper', 'value', allow_duplicate=True),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('calibration-value', 'value', allow_duplicate=True),
        Output('calibration-interest', 'value', allow_duplicate=True),
        Output('calibration-difficulty', 'value', allow_duplicate=True),
        Output('calibration-notes', 'value', allow_duplicate=True),
        Input('modal-time-calibration', 'is_open'),
        State('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def _calibration_modal_closed(is_open, pending):
        if is_open or pending is None:
            return (no_update,) * 9
        return None, None, None, None, 'hours', 5, 5, 5, ''

    # --- Calibration modal pre-population: fill inputs when the store changes
    # to point at a new node ---
    # Single source of truth for "what values does the user see when the
    # modal opens / advances / re-opens for editing". Triggered by every
    # store-mode transition that names a node (single, review, edit). Fires
    # after the store-setting callback (core_engine / launch /
    # handle_time_calibration / Phase-6 edit hand-off) so its outputs win on
    # the same flush cycle.
    @app.callback(
        Output('time-calibration-lower', 'value', allow_duplicate=True),
        Output('time-calibration-point', 'value', allow_duplicate=True),
        Output('time-calibration-upper', 'value', allow_duplicate=True),
        Output('time-calibration-unit', 'value', allow_duplicate=True),
        Output('calibration-value', 'value', allow_duplicate=True),
        Output('calibration-interest', 'value', allow_duplicate=True),
        Output('calibration-difficulty', 'value', allow_duplicate=True),
        Output('calibration-notes', 'value', allow_duplicate=True),
        Input('time-calibration-pending-store', 'data'),
        prevent_initial_call=True,
    )
    def pre_populate_calibration_inputs(pending):
        if not isinstance(pending, dict):
            return (no_update,) * 8
        mode = pending.get('mode')
        if mode == 'single':
            node_name = pending.get('node')
        elif mode == 'review':
            queue = pending.get('queue', [])
            idx = pending.get('index', 0)
            node_name = queue[idx] if 0 <= idx < len(queue) else None
        else:
            # 'complete' or unrecognized — don't touch the inputs.
            return (no_update,) * 8
        node = manager.get_node(node_name) if node_name else None
        if not node:
            return (no_update,) * 8
        return _calibration_prepop(node)

    # --- Calibration review button: hidden when the feature is off ---
    # Evaluated as the layout is built and on every tab switch — a tab switch
    # is the natural action after toggling the setting in Settings, and it
    # happens after the save has committed, so there's no read-before-write
    # race.
    @app.callback(
        Output('btn-calibration-review', 'style'),
        Input('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    @prerendered
    def _calibration_review_button_visibility(_active_tab):
        if ConfigManager.get_time_calibration_enabled():
            return {"display": "inline-block"}
        return {"display": "none"}

    # --- Calibration: editor read-only "excluded" badge ---
    # Keyed off node-original-name (set when a node loads into the editor) so
    # it stays decoupled from the large populate_editor callback.
    @app.callback(
        Output('node-calibration-dismissed-badge', 'children'),
        Output('node-calibration-dismissed-badge', 'style'),
        Input('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def _calibration_editor_badge(original_name):
        node = manager.get_node(original_name) if original_name else None
        if node is not None and node.calibration_dismissed:
            return ("Excluded from calibration review — restore in Settings.",
                    {"display": "block"})
        return "", {"display": "none"}
