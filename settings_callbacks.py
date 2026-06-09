"""
Callback definitions for the Settings tab.
"""

import logging
import dash
from dash import html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from config import ConfigManager, sort_subcontexts, sort_contexts
from models import STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from typing import Tuple, Any
from callback_helpers import get_trigger_id, build_context_weight_rows, detect_context_renames

logger = logging.getLogger(__name__)

manager = GraphManager()


def _display_types_from_config():
    display_types = ConfigManager.get_node_types().copy()
    if "Goal" not in display_types:
        display_types.append("Goal")
    return display_types


def _display_types_from_text(types_text):
    types = [c.strip() for c in (types_text or "").split(",") if c.strip()]
    if not types:
        return _display_types_from_config()
    if "Goal" not in types:
        types.append("Goal")
    return types


def _shape_options():
    return [
        {"label": s.title(), "value": s}
        for s in [
            "ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
            "diamond", "octagon", "round-rectangle", "vee",
        ]
    ]


def _build_shape_rows(display_types, shapes):
    return [
        html.Div([
            html.Div(dbc.Label(t, className="mb-0"),
                     className="d-flex align-items-center",
                     style={"width": "92px", "flex": "0 0 auto"}),
            dbc.Select(
                id={"type": "setting-shape", "index": t},
                options=_shape_options(),
                value=shapes.get(t, "ellipse"),
                style={"width": "156px"},
            ),
        ], className="d-flex align-items-center gap-2 mb-2")
        for t in display_types
    ]


def _build_color_row(label, key, colors):
    color_val = colors.get(key, "#6c757d")
    return html.Div([
        html.Div(dbc.Label(label, className="mb-0"),
                 className="d-flex align-items-center",
                 style={"width": "92px", "flex": "0 0 auto"}),
        dbc.Input(
            id={"type": "setting-color", "index": key},
            type="color",
            value=color_val,
            style={"height": "38px", "width": "52px", "padding": "2px"},
        ),
        html.Small(
            color_val,
            className="text-muted",
            style={"fontSize": "0.8rem"},
        ),
    ], className="d-flex align-items-center gap-2 mb-2")


def _build_status_color_rows(colors):
    return [
        _build_color_row(STATUS_DONE, STATUS_DONE, colors),
        _build_color_row(STATUS_BLOCKED, STATUS_BLOCKED, colors),
        _build_color_row("Override", "Override", colors),
        _build_color_row("Now", "Now", colors),
    ]


def _build_type_color_rows(display_types, colors):
    rows = []
    for t in display_types:
        color_val = colors.get(t, "#6c757d")
        rows.append(html.Div([
            dbc.Input(
                id={"type": "setting-color", "index": t},
                type="color",
                value=color_val,
                style={"height": "38px", "width": "52px", "padding": "2px"},
            ),
            html.Small(
                color_val,
                className="text-muted",
                style={"fontSize": "0.8rem"},
            ),
        ], className="d-flex align-items-center gap-2 mb-2"))
    return rows


def _clamp(val, lo, hi, default):
    """Clamp a numeric value to [lo, hi], falling back to default if None."""
    try:
        v = float(val) if val is not None else default
    except (ValueError, TypeError):
        return default
    return max(lo, min(hi, v))


def _migrate_context_weights(old_weights: dict, pending_weights: dict,
                             new_contexts: list, rename_map: dict) -> dict:
    """Resolve context weights after a save that renamed/merged/removed contexts.

    Rules:
      1. Context present in new_contexts  → keep its weight from pending_weights.
      2. Context renamed (old → new) via the migration dialog:
         - If the target's current weight in `final_weights` is the default
           (1.0) and the source's old weight is non-default, carry the source's
           weight to the target (the "I renamed Health → Body" case).
         - Otherwise the target's weight wins (the "I'm folding Health into
           an existing weighted Body context" case).
      3. Context removed with no rename target: weight dropped.

    Args:
        old_weights: weights as persisted in the DB before this save.
        pending_weights: weights from the current UI form state.
        new_contexts: the post-save context list.
        rename_map: {old_name: new_name} from the user's migration dropdown
            selections. Empty for skip / no-migration flows.

    Returns: the dict to persist via set_context_weights.
    """
    final_weights = {
        c: pending_weights[c] for c in new_contexts if c in pending_weights
    }
    for old_name, new_name in rename_map.items():
        if new_name not in new_contexts:
            continue
        target_w = final_weights.get(new_name, 1.0)
        source_w = old_weights.get(old_name, 1.0)
        if abs(target_w - 1.0) < 1e-9 and abs(source_w - 1.0) >= 1e-9:
            final_weights[new_name] = source_w
    return final_weights


def _build_rename_map_from_per_node_choices(ctx_nodes: list, cgc_node_values: list) -> dict:
    """Build {old_ctx: new_ctx} from per-node ctx selections in the migration modal.

    With per-node migration, nodes from the same old group can target different
    new contexts. The most-chosen new context per old group wins. Ties (no
    clear majority) drop the old weight — consult the caller (`_migrate_context_weights`).
    `__keep__` and `__clear__` selections don't count toward any majority.
    """
    from collections import Counter
    by_old: dict = {}
    for i, entry in enumerate(ctx_nodes):
        old_name = entry.get('old_value')
        new_name = cgc_node_values[i] if i < len(cgc_node_values) else None
        if old_name and new_name and new_name not in ('__keep__', '__clear__'):
            by_old.setdefault(old_name, []).append(new_name)
    rename_map: dict = {}
    for old_name, choices in by_old.items():
        counts = Counter(choices)
        top_name, top_count = counts.most_common(1)[0]
        if list(counts.values()).count(top_count) == 1:
            rename_map[old_name] = top_name
    return rename_map


def _apply_per_node_migrations(manager, entries: list, ctx_vals: list, sub_vals: list,
                                new_subcontexts: dict) -> None:
    """Apply per-node ctx/sub remaps via `manager.apply_node_migration`.

    Each `entries[i]` carries a 'node_name' field; ctx_vals[i] and sub_vals[i]
    are the chosen new values from the modal's per-node dropdowns.
    `__keep__` is a no-op; `__clear__` clears the field (handled inside
    `apply_node_migration` via the sentinel).
    """
    for i, entry in enumerate(entries):
        ctx_val = ctx_vals[i] if i < len(ctx_vals) else None
        sub_val = sub_vals[i] if i < len(sub_vals) else None
        if ctx_val and ctx_val != '__keep__':
            manager.apply_node_migration(entry['node_name'], 'context',
                                         ctx_val, new_subcontexts)
        if sub_val and sub_val != '__keep__':
            manager.apply_node_migration(entry['node_name'], 'subcontext',
                                         sub_val, new_subcontexts)


def register_settings_callbacks(app):

    # --- Settings: Auto-resize the Definitions textarea to fit its line count ---
    # Bounds [3, 10] rows. Fires on every keystroke; runs in the browser so
    # no server round-trip. Mirrors the manual-resize disable in the layout's
    # textarea style.
    app.clientside_callback(
        """
        function(value) {
            var n = (value || '').split('\\n').length;
            return Math.max(3, Math.min(10, n));
        }
        """,
        Output('setting-subcontexts', 'rows'),
        Input('setting-subcontexts', 'value'),
    )

    # --- Settings: Open the Settings modal from the toolbar gear button ---
    @app.callback(
        Output("settings-modal", "is_open"),
        Input("btn-settings-toggle", "n_clicks"),
        State("settings-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_settings_modal(_n_clicks, is_open):
        return not is_open

    # --- Settings: Toggle the Algorithm Profile info popover ---
    @app.callback(
        Output("popover-hp-profile-info", "is_open"),
        Input("btn-hp-profile-info", "n_clicks"),
        State("popover-hp-profile-info", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_hp_profile_info_popover(_n_clicks, is_open):
        return not is_open

    # --- Settings: Load when Settings tab activates ---
    @app.callback(
        Output('hp-wv', 'value'),
        Output('hp-wi', 'value'),
        Output('hp-dh', 'value'),
        Output('hp-ds', 'value'),
        Output('hp-dsyn-pair', 'value'),
        Output('hp-dsyn-mul', 'value'),
        Output('hp-cross-context-mult', 'value'),
        Output('hp-we', 'value'),
        Output('hp-wt', 'value'),
        Output('hp-beta', 'value'),
        Output('hp-goal-boost', 'value'),
        Output('hp-alpha', 'value'),
        Output('setting-node-types', 'value'),
        Output('setting-subcontexts', 'value'),
        Output('setting-hp-profile', 'value'),
        Output('setting-obsidian-path', 'value'),
        Output('setting-gdrive-path', 'value'),
        Output('setting-node-shapes-container', 'children'),
        Output('setting-node-status-colors-container', 'children'),
        Output('setting-node-type-colors-container', 'children'),
        Output('setting-context-weights-container', 'children'),
        Output('setting-hpw', 'value'),
        Output('setting-hpm', 'value'),
        Output('setting-hpy', 'value'),
        Output('setting-default-time-unit', 'value'),
        Output('setting-default-time-o', 'value'),
        Output('setting-default-time-m', 'value'),
        Output('setting-default-time-p', 'value'),
        Output('setting-linter-enabled', 'value'),
        Output('setting-linter-exclusions', 'value'),
        Output('setting-next-table-rows', 'value'),
        Output('setting-graph-edge-length', 'value'),
        Output('setting-graph-gravity', 'value'),
        Output('setting-graph-repulsion', 'value'),
        Output('setting-details-graph-edge-length', 'value'),
        Output('setting-details-graph-gravity', 'value'),
        Output('setting-details-graph-repulsion', 'value'),
        Output('setting-events-graph-edge-length', 'value'),
        Output('setting-events-graph-gravity', 'value'),
        Output('setting-events-graph-repulsion', 'value'),
        Output('setting-show-scoring-perf', 'value'),
        Output('setting-subcontext-sort-mode', 'value'),
        Output('setting-context-sort-mode', 'value'),
        Output('setting-time-calibration-enabled', 'value'),
        Output('setting-monte-carlo-trials', 'value'),
        Output('setting-now-node-cap', 'value'),
        Input('settings-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def load_settings(is_open: bool) -> Tuple[Any, ...]:
        if not is_open:
            return (dash.no_update,) * 46

        hp = ConfigManager.get_hyperparams()
        node_types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        subcontexts = ConfigManager.get_subcontexts()
        ctx_weights = ConfigManager.get_context_weights()
        obs_path = ConfigManager.get_obsidian_vault()
        gdrive_path = ConfigManager.get_gdrive_path()
        profile = ConfigManager.get_hp_profile()

        sub_lines = []
        for ctx_name in contexts:
            subs = subcontexts.get(ctx_name, [])
            if subs:
                sub_lines.append(f"{ctx_name}: {', '.join(subs)}")
            else:
                sub_lines.append(ctx_name)
        # Include any subcontext-only entries not in contexts list
        for ctx_name, subs in subcontexts.items():
            if ctx_name not in contexts:
                sub_lines.append(f"{ctx_name}: {', '.join(subs)}")
        sub_val = '\n'.join(sub_lines)

        shapes = ConfigManager.get_node_shapes()
        display_types = _display_types_from_config()
        shape_rows = _build_shape_rows(display_types, shapes)
        colors = ConfigManager.get_node_colors()
        status_color_rows = _build_status_color_rows(colors)
        type_color_rows = _build_type_color_rows(display_types, colors)

        weight_rows = build_context_weight_rows(sort_contexts(contexts), ctx_weights)

        ts = ConfigManager.get_time_settings()
        from config import DEFAULT_TIME_ESTIMATE_DEFAULTS
        ted = ConfigManager.get_time_estimate_defaults()

        linter = ConfigManager.get_titlecase_linter()
        linter_enabled_val = ["enabled"] if linter.get('enabled', True) else []
        linter_exclusions_val = ', '.join(linter.get('exclusions', []))

        from config import DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT, DEFAULT_EVENTS_GRAPH_LAYOUT
        gl = ConfigManager.get_graph_layout_defaults()
        dgl = ConfigManager.get_details_graph_layout_defaults()
        egl = ConfigManager.get_events_graph_layout_defaults()

        return (
            hp.get('w_v', 1.0), hp.get('w_i', 1.0),
            hp.get('d_H', 0.6), hp.get('d_S', 0.40),
            hp.get('d_Syn_pair', 0.10), hp.get('d_Syn_mul', 0.40),
            hp.get('cross_context_mult', 1.0),
            hp.get('w_e', 2.5), hp.get('w_t', 1.0), hp.get('beta', 0.85),
            hp.get('goal_boost', 1.5),
            hp.get('alpha', 0.3),
            ', '.join(node_types),
            sub_val,
            profile,
            obs_path,
            gdrive_path,
            shape_rows,
            status_color_rows,
            type_color_rows,
            weight_rows,
            ts.get('hours_per_week', 40),
            ts.get('hours_per_month', 160),
            ConfigManager.get_hours_per_year(),
            ted.get('unit', DEFAULT_TIME_ESTIMATE_DEFAULTS['unit']),
            ted.get('optimistic', DEFAULT_TIME_ESTIMATE_DEFAULTS['optimistic']),
            ted.get('expected', DEFAULT_TIME_ESTIMATE_DEFAULTS['expected']),
            ted.get('pessimistic', DEFAULT_TIME_ESTIMATE_DEFAULTS['pessimistic']),
            linter_enabled_val,
            linter_exclusions_val,
            ConfigManager.get_next_table_rows(),
            gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
            gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
            gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
            dgl.get('edge_length', DEFAULT_DETAILS_GRAPH_LAYOUT['edge_length']),
            dgl.get('gravity', DEFAULT_DETAILS_GRAPH_LAYOUT['gravity']),
            dgl.get('repulsion', DEFAULT_DETAILS_GRAPH_LAYOUT['repulsion']),
            egl.get('edge_length', DEFAULT_EVENTS_GRAPH_LAYOUT['edge_length']),
            egl.get('gravity', DEFAULT_EVENTS_GRAPH_LAYOUT['gravity']),
            egl.get('repulsion', DEFAULT_EVENTS_GRAPH_LAYOUT['repulsion']),
            ["enabled"] if ConfigManager.get_show_scoring_perf() else [],
            ConfigManager.get_subcontext_sort_mode(),
            ConfigManager.get_context_sort_mode(),
            ["enabled"] if ConfigManager.get_time_calibration_enabled() else [],
            ConfigManager.get_monte_carlo_trials(),
            ConfigManager.get_now_node_cap(),
        )

    # --- Settings: Apply Hyperparameter Profile ---
    @app.callback(
        Output('hp-wv', 'value', allow_duplicate=True),
        Output('hp-wi', 'value', allow_duplicate=True),
        Output('hp-dh', 'value', allow_duplicate=True),
        Output('hp-ds', 'value', allow_duplicate=True),
        Output('hp-dsyn-pair', 'value', allow_duplicate=True),
        Output('hp-dsyn-mul', 'value', allow_duplicate=True),
        Output('hp-cross-context-mult', 'value', allow_duplicate=True),
        Output('hp-we', 'value', allow_duplicate=True),
        Output('hp-wt', 'value', allow_duplicate=True),
        Output('hp-beta', 'value', allow_duplicate=True),
        Output('hp-goal-boost', 'value', allow_duplicate=True),
        Output('hp-alpha', 'value', allow_duplicate=True),
        Input('setting-hp-profile', 'value'),
        prevent_initial_call=True,
    )
    def apply_profile(profile_val):
        from config import PROFILES
        if profile_val in PROFILES:
            p = PROFILES[profile_val]
            return (p['w_v'], p['w_i'], p['d_H'], p['d_S'],
                    p['d_Syn_pair'], p['d_Syn_mul'],
                    p.get('cross_context_mult', 1.0),
                    p['w_e'], p['w_t'], p['beta'], p.get('goal_boost', 1.5),
                    p.get('alpha', 0.3))
        return (dash.no_update,) * 12

    # --- Settings: Sync Time Estimates ---
    # 1 month = 4 weeks; 1 year = 13 months = 52 weeks (see ConfigManager.HOURS_PER_YEAR_MULT).
    @app.callback(
        Output('setting-hpw', 'value', allow_duplicate=True),
        Output('setting-hpm', 'value', allow_duplicate=True),
        Output('setting-hpy', 'value', allow_duplicate=True),
        Input('setting-hpw', 'value'),
        Input('setting-hpm', 'value'),
        Input('setting-hpy', 'value'),
        prevent_initial_call=True,
    )
    def sync_time_settings(hpw, hpm, hpy):
        triggered = ctx.triggered_id
        if not triggered:
            return dash.no_update, dash.no_update, dash.no_update
        try:
            if triggered == 'setting-hpw' and hpw is not None:
                w = float(hpw)
                return dash.no_update, round(w * 4.0, 2), round(w * 52.0, 2)
            elif triggered == 'setting-hpm' and hpm is not None:
                m = float(hpm)
                return round(m / 4.0, 2), dash.no_update, round(m * 13.0, 2)
            elif triggered == 'setting-hpy' and hpy is not None:
                y = float(hpy)
                return round(y / 52.0, 2), round(y / 13.0, 2), dash.no_update
        except Exception:
            pass
        return dash.no_update, dash.no_update, dash.no_update

    @app.callback(
        Output('hp-goal-boost-description', 'children'),
        Input('hp-goal-boost', 'value'),
    )
    def update_goal_boost_description(boost):
        try:
            b = float(boost) if boost is not None else 1.5
        except (ValueError, TypeError):
            b = 1.5
        rank2 = 1 + (b - 1) * 0.66
        rank3 = 1 + (b - 1) * 0.33
        return (
            "Multiplier applied to nodes in a priority goal's subtree. "
            f"Rank #1 gets the full boost, #2 gets {rank2:.2f} (66%), "
            f"#3 gets {rank3:.2f} (33%)."
        )

    # --- Settings: Save ---
    @app.callback(
        Output('settings-save-status', 'children'),
        Output('pending-settings-store', 'data'),
        Output('settings-clear-interval', 'disabled'),
        Output('settings-clear-interval', 'n_intervals'),
        Output('setting-context-weights-container', 'children', allow_duplicate=True),
        Input('btn-settings-save', 'n_clicks'),
        State('hp-wv', 'value'), State('hp-wi', 'value'),
        State('hp-dh', 'value'), State('hp-ds', 'value'),
        State('hp-dsyn-pair', 'value'), State('hp-dsyn-mul', 'value'),
        State('hp-cross-context-mult', 'value'),
        State('hp-we', 'value'), State('hp-wt', 'value'), State('hp-beta', 'value'),
        State('hp-goal-boost', 'value'),
        State('hp-alpha', 'value'),
        State('setting-node-types', 'value'),
        State('setting-subcontexts', 'value'),
        State('setting-obsidian-path', 'value'),
        State('setting-gdrive-path', 'value'),
        State({"type": "setting-shape", "index": ALL}, "value"),
        State({"type": "setting-shape", "index": ALL}, "id"),
        State({"type": "setting-color", "index": ALL}, "value"),
        State({"type": "setting-color", "index": ALL}, "id"),
        State({"type": "setting-context-weight", "index": ALL}, "value"),
        State({"type": "setting-context-weight", "index": ALL}, "id"),
        State('setting-hpw', 'value'), State('setting-hpm', 'value'),
        State('setting-default-time-unit', 'value'),
        State('setting-default-time-o', 'value'),
        State('setting-default-time-m', 'value'),
        State('setting-default-time-p', 'value'),
        State('setting-hp-profile', 'value'),
        State('setting-linter-enabled', 'value'),
        State('setting-linter-exclusions', 'value'),
        State('setting-next-table-rows', 'value'),
        State('setting-graph-edge-length', 'value'),
        State('setting-graph-gravity', 'value'),
        State('setting-graph-repulsion', 'value'),
        State('setting-details-graph-edge-length', 'value'),
        State('setting-details-graph-gravity', 'value'),
        State('setting-details-graph-repulsion', 'value'),
        State('setting-events-graph-edge-length', 'value'),
        State('setting-events-graph-gravity', 'value'),
        State('setting-events-graph-repulsion', 'value'),
        State('setting-show-scoring-perf', 'value'),
        State('setting-subcontext-sort-mode', 'value'),
        State('setting-context-sort-mode', 'value'),
        State('setting-time-calibration-enabled', 'value'),
        State('setting-monte-carlo-trials', 'value'),
        State('setting-now-node-cap', 'value'),
        prevent_initial_call=True,
    )
    def save_settings(n_clicks, wv, wi, dh, ds, dsyn_pair, dsyn_mul,
                      cross_context_mult,
                      we, wt, beta, goal_boost,
                      alpha,
                      n_types_val, subcontexts_val, obs_path, gdrive_path,
                      shape_values, shape_ids, color_values, color_ids,
                      ctx_weight_values, ctx_weight_ids,
                      hpw, hpm,
                      def_time_unit, def_time_o, def_time_m, def_time_p, hp_profile,
                      linter_enabled_val, linter_exclusions_val, next_table_rows_val,
                      gl_edge_length, gl_gravity, gl_repulsion,
                      dgl_edge_length, dgl_gravity, dgl_repulsion,
                      egl_edge_length, egl_gravity, egl_repulsion,
                      show_scoring_perf_val, subcontext_sort_mode_val,
                      context_sort_mode_val, time_calibration_val,
                      monte_carlo_trials_val, now_node_cap_val):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            # Perf-toggle is independent of any migrated setting — persist
            # it immediately so the user's choice survives regardless of
            # whether a type/context migration is pending.
            ConfigManager.set_show_scoring_perf(
                bool(show_scoring_perf_val and "enabled" in show_scoring_perf_val)
            )
            ConfigManager.set_time_calibration_enabled(
                bool(time_calibration_val and "enabled" in time_calibration_val)
            )
            if now_node_cap_val is not None:
                ConfigManager.set_now_node_cap(max(1, min(50, int(now_node_cap_val))))
            if subcontext_sort_mode_val:
                ConfigManager.set_subcontext_sort_mode(subcontext_sort_mode_val)
            if context_sort_mode_val:
                ConfigManager.set_context_sort_mode(context_sort_mode_val)
            new_hp = {
                'w_v': float(wv), 'w_i': float(wi),
                'd_H': float(dh), 'd_S': float(ds),
                'd_Syn_pair': float(dsyn_pair), 'd_Syn_mul': float(dsyn_mul),
                'cross_context_mult': float(cross_context_mult) if cross_context_mult is not None else 1.0,
                'w_e': float(we), 'w_t': float(wt), 'beta': float(beta),
                'goal_boost': float(goal_boost) if goal_boost is not None else 1.5,
                'alpha': _clamp(alpha, 0.0, 1.5, 0.3),
            }

            new_ctx_weights: dict = {}
            if ctx_weight_ids and ctx_weight_values:
                for wid, wval in zip(ctx_weight_ids, ctx_weight_values):
                    name = wid.get("index")
                    if not name:
                        continue
                    new_ctx_weights[name] = _clamp(wval, 0.0, 10.0, 1.0)

            from config import DEFAULT_MONTE_CARLO_TRIALS
            try:
                mc_trials = int(monte_carlo_trials_val)
            except (TypeError, ValueError):
                mc_trials = DEFAULT_MONTE_CARLO_TRIALS
            new_ts = {
                'hours_per_week': float(hpw) if hpw is not None else 40,
                'hours_per_month': float(hpm) if hpm is not None else 160,
                'monte_carlo_trials': mc_trials if mc_trials > 0 else DEFAULT_MONTE_CARLO_TRIALS,
            }

            from config import DEFAULT_TIME_ESTIMATE_DEFAULTS
            new_ted = {
                'optimistic': float(def_time_o) if def_time_o is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['optimistic'],
                'expected': float(def_time_m) if def_time_m is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['expected'],
                'pessimistic': float(def_time_p) if def_time_p is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['pessimistic'],
                'unit': def_time_unit or DEFAULT_TIME_ESTIMATE_DEFAULTS['unit'],
            }

            new_types = [c.strip() for c in (n_types_val or '').split(',') if c.strip()]
            new_contexts = []
            new_subcontexts = {}
            if subcontexts_val is not None:
                for line in subcontexts_val.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    if ':' in line:
                        ctx_name, subs_str = line.split(':', 1)
                        ctx_name = ctx_name.strip()
                        subs = [s.strip() for s in subs_str.split(',') if s.strip()]
                        if ctx_name:
                            if ctx_name not in new_contexts:
                                new_contexts.append(ctx_name)
                            if subs:
                                if ctx_name in new_subcontexts:
                                    new_subcontexts[ctx_name].extend(subs)
                                else:
                                    new_subcontexts[ctx_name] = subs
                    else:
                        ctx_name = line.strip()
                        if ctx_name and ctx_name not in new_contexts:
                            new_contexts.append(ctx_name)

            old_types = ConfigManager.get_node_types()
            old_contexts = ConfigManager.get_contexts()
            old_subcontexts = ConfigManager.get_subcontexts()

            new_sub_flat = [s for subs in new_subcontexts.values() for s in subs]

            # Annotate dormant orphans with their event names so the migration
            # modal can show "(dormant — in event: X)" — gives the user context
            # for nodes that aren't currently on the canvas but still hold the
            # stale config value.
            from event_manager import EventManager
            _em = EventManager()

            def _annotate(node):
                base = {'name': node.name}
                if node.dormant:
                    base['dormant'] = True
                    base['events'] = _em.get_events_for_node(node.name)
                return base

            orphans = {}
            type_orphans = manager.find_orphaned_nodes('type', old_types, new_types)
            if type_orphans:
                orphans['type'] = {
                    k: [_annotate(n) for n in v]
                    for k, v in type_orphans.items()
                }
            ctx_orphans = manager.find_orphaned_nodes('context', old_contexts, new_contexts)
            if ctx_orphans:
                # Carry each node's current subcontext so the modal can pre-fill
                # per-node defaults that preserve subcontexts during a rename.
                orphans['context'] = {
                    k: [{**_annotate(n), 'subcontext': n.subcontext} for n in v]
                    for k, v in ctx_orphans.items()
                }
            sub_orphans = manager.find_orphaned_subcontext_pairs(
                old_subcontexts, new_subcontexts, new_contexts
            )
            if sub_orphans:
                orphans['subcontext'] = {
                    k: [{**_annotate(n), 'context': n.context} for n in v]
                    for k, v in sub_orphans.items()
                }

            if orphans:
                pending_shapes = {}
                if shape_ids and shape_values:
                    for sid, sval in zip(shape_ids, shape_values):
                        if sval:
                            pending_shapes[sid["index"]] = sval
                pending_colors = {}
                if color_ids and color_values:
                    for cid, cval in zip(color_ids, color_values):
                        if cval:
                            pending_colors[cid["index"]] = cval

                new_linter = {
                    'enabled': bool(linter_enabled_val and "enabled" in linter_enabled_val),
                    'exclusions': [w.strip() for w in (linter_exclusions_val or '').split(',') if w.strip()],
                }
                from config import DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT, DEFAULT_EVENTS_GRAPH_LAYOUT
                new_gl = {
                    'edge_length': _clamp(gl_edge_length, 50, 300, DEFAULT_GRAPH_LAYOUT['edge_length']),
                    'gravity': _clamp(gl_gravity, 0, 5, DEFAULT_GRAPH_LAYOUT['gravity']),
                    'repulsion': _clamp(gl_repulsion, 500, 100000, DEFAULT_GRAPH_LAYOUT['repulsion']),
                }
                new_dgl = {
                    'edge_length': _clamp(dgl_edge_length, 50, 300, DEFAULT_DETAILS_GRAPH_LAYOUT['edge_length']),
                    'gravity': _clamp(dgl_gravity, 0, 5, DEFAULT_DETAILS_GRAPH_LAYOUT['gravity']),
                    'repulsion': _clamp(dgl_repulsion, 500, 100000, DEFAULT_DETAILS_GRAPH_LAYOUT['repulsion']),
                }
                new_egl = {
                    'edge_length': _clamp(egl_edge_length, 50, 300, DEFAULT_EVENTS_GRAPH_LAYOUT['edge_length']),
                    'gravity': _clamp(egl_gravity, 0, 5, DEFAULT_EVENTS_GRAPH_LAYOUT['gravity']),
                    'repulsion': _clamp(egl_repulsion, 500, 100000, DEFAULT_EVENTS_GRAPH_LAYOUT['repulsion']),
                }
                pending = {
                    'hp': new_hp,
                    'ts': new_ts,
                    'ted': new_ted,
                    'gl': new_gl,
                    'dgl': new_dgl,
                    'egl': new_egl,
                    'obs_path': obs_path,
                    'gdrive_path': gdrive_path or "",
                    'types': new_types,
                    'contexts': new_contexts,
                    'subcontexts': new_subcontexts,
                    'context_weights': new_ctx_weights,
                    'shapes': pending_shapes,
                    'colors': pending_colors,
                    'linter': new_linter,
                    'next_table_rows': int(next_table_rows_val) if next_table_rows_val is not None else None,
                    'orphans': orphans,
                    'new_values': {
                        'type': new_types,
                        'context': new_contexts,
                        'subcontext': new_sub_flat,
                    },
                    'rename_map': detect_context_renames(
                        old_contexts, new_contexts,
                        old_subcontexts, new_subcontexts,
                    ),
                }
                return "Migration required \u2014 check the migration dialog.", pending, False, 0, dash.no_update

            from config import DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT, DEFAULT_EVENTS_GRAPH_LAYOUT
            new_gl = {
                'edge_length': float(gl_edge_length) if gl_edge_length is not None else DEFAULT_GRAPH_LAYOUT['edge_length'],
                'gravity': float(gl_gravity) if gl_gravity is not None else DEFAULT_GRAPH_LAYOUT['gravity'],
                'repulsion': float(gl_repulsion) if gl_repulsion is not None else DEFAULT_GRAPH_LAYOUT['repulsion'],
            }
            new_dgl = {
                'edge_length': float(dgl_edge_length) if dgl_edge_length is not None else DEFAULT_DETAILS_GRAPH_LAYOUT['edge_length'],
                'gravity': float(dgl_gravity) if dgl_gravity is not None else DEFAULT_DETAILS_GRAPH_LAYOUT['gravity'],
                'repulsion': float(dgl_repulsion) if dgl_repulsion is not None else DEFAULT_DETAILS_GRAPH_LAYOUT['repulsion'],
            }
            new_egl = {
                'edge_length': float(egl_edge_length) if egl_edge_length is not None else DEFAULT_EVENTS_GRAPH_LAYOUT['edge_length'],
                'gravity': float(egl_gravity) if egl_gravity is not None else DEFAULT_EVENTS_GRAPH_LAYOUT['gravity'],
                'repulsion': float(egl_repulsion) if egl_repulsion is not None else DEFAULT_EVENTS_GRAPH_LAYOUT['repulsion'],
            }

            ConfigManager.set_hp_profile(hp_profile or "Custom")
            ConfigManager.set_hyperparams(new_hp)
            ConfigManager.set_time_settings(new_ts)
            ConfigManager.set_time_estimate_defaults(new_ted)
            ConfigManager.set_graph_layout_defaults(new_gl)
            ConfigManager.set_details_graph_layout_defaults(new_dgl)
            ConfigManager.set_events_graph_layout_defaults(new_egl)
            ConfigManager.set_obsidian_vault(obs_path)
            ConfigManager.set_gdrive_path(gdrive_path or "")
            if new_types:
                ConfigManager.set_node_types(new_types)
                ConfigManager.sync_shapes_to_types(new_types)
            old_weights = ConfigManager.get_context_weights()
            if new_contexts:
                ConfigManager.set_contexts(new_contexts)
            ConfigManager.set_subcontexts(new_subcontexts)
            # No orphans here means no rename dialog was needed — just drop
            # weights for contexts the user removed outright.
            ConfigManager.set_context_weights(_migrate_context_weights(
                old_weights, new_ctx_weights, new_contexts or [], {},
            ))

            if shape_ids and shape_values:
                new_shapes = {}
                for sid, sval in zip(shape_ids, shape_values):
                    if sval:
                        new_shapes[sid["index"]] = sval
                if new_shapes:
                    ConfigManager.set_node_shapes(new_shapes)

            if color_ids and color_values:
                new_colors = {}
                for cid, cval in zip(color_ids, color_values):
                    if cval:
                        new_colors[cid["index"]] = cval
                if new_colors:
                    ConfigManager.set_node_colors(new_colors)

            new_linter = {
                'enabled': bool(linter_enabled_val and "enabled" in linter_enabled_val),
                'exclusions': [w.strip() for w in (linter_exclusions_val or '').split(',') if w.strip()],
            }
            ConfigManager.set_titlecase_linter(new_linter)

            if next_table_rows_val is not None:
                ConfigManager.set_next_table_rows(int(next_table_rows_val))

            saved_contexts = new_contexts if new_contexts else ConfigManager.get_contexts()
            refreshed_weight_rows = build_context_weight_rows(
                sort_contexts(saved_contexts), ConfigManager.get_context_weights()
            )
            return "Settings saved", dash.no_update, False, 0, refreshed_weight_rows

        except Exception:
            logger.exception("Failed to save settings")
            return "Error saving settings.", dash.no_update, False, 0, dash.no_update

    # --- Perf profile: on-demand N-run benchmark (always available) ---
    @app.callback(
        Output('perf-profile-output', 'children'),
        Input('btn-run-perf-profile', 'n_clicks'),
        State('perf-profile-runs', 'value'),
        prevent_initial_call=True,
    )
    def run_perf_profile(n_clicks, n_runs):
        if not n_clicks:
            return dash.no_update
        import statistics
        import math
        from scoring import score_nodes
        N = max(1, int(n_runs or 10))
        hypers = ConfigManager.get_hyperparams()
        hypers['context_weights'] = ConfigManager.get_context_weights()
        priority_goals = ConfigManager.get_priority_goals()
        all_nodes = manager.get_all_nodes()
        edges = manager.get_edges()
        active = [n for n in all_nodes if n.status not in (STATUS_DONE, STATUS_BLOCKED)]
        runs = []
        for _ in range(N):
            _, t = score_nodes(active, all_nodes, edges, hypers,
                               priority_goals=priority_goals,
                               external_memo={}, time_phases=True)
            runs.append(t)

        keys = [("total_ms", "total"), ("adj_ms", "adj"),
                ("goals_ms", "goals"), ("score_ms", "score"), ("rank_ms", "rank")]
        header = html.Tr([html.Th(c) for c in
                          ["phase", "median", "mean", "SD", "95% CI (mean)"]])
        rows = [header]
        for k, label in keys:
            vals = [r[k] for r in runs]
            med = statistics.median(vals)
            mean = statistics.fmean(vals)
            sd = statistics.stdev(vals) if N >= 2 else 0.0
            half = 1.96 * sd / math.sqrt(N) if N >= 2 else 0.0
            rows.append(html.Tr([
                html.Td(label),
                html.Td(f"{med:.2f} ms"),
                html.Td(f"{mean:.2f} ms"),
                html.Td(f"{sd:.2f} ms"),
                html.Td(f"[{mean - half:.2f}, {mean + half:.2f}] ms"),
            ]))
        header_line = html.Div(
            f"Profile: N={N}, {runs[-1]['n_nodes']} nodes, "
            f"{runs[-1]['n_edges']} edges (cold memo per run)",
            className="text-muted mb-1")
        return [header_line,
                html.Table(rows, className="table table-sm table-dark table-borderless")]

    # --- Settings: Repair Graph (manual trigger for recompute_all_statuses) ---
    @app.callback(
        Output('repair-graph-status', 'children'),
        Output('elements-pending-store', 'data', allow_duplicate=True),
        Input('btn-repair-graph', 'n_clicks'),
        prevent_initial_call=True,
    )
    def repair_graph(n_clicks):
        if not n_clicks:
            return dash.no_update, dash.no_update
        try:
            from callbacks import generate_elements
            changed = manager.recompute_all_statuses()
            if changed:
                noun = "node" if changed == 1 else "nodes"
                return f"Repaired {changed} {noun}.", generate_elements()
            return "Graph already consistent.", dash.no_update
        except Exception:
            logger.exception("Failed to repair graph")
            return "Error during repair — see logs.", dash.no_update

    # --- Migration Modal ---
    @app.callback(
        Output('modal-migration', 'is_open'),
        Output('migration-modal-body', 'children'),
        Output('migration-mapping-store', 'data'),
        Output('setting-subcontexts', 'value', allow_duplicate=True),
        Output('setting-node-types', 'value', allow_duplicate=True),
        Input('pending-settings-store', 'data'),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        Input('btn-migration-cancel', 'n_clicks'),
        State({"type": "migration-dropdown", "index": dash.ALL}, "value"),
        State({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True
    )
    def handle_migration(pending_data, apply_clicks, skip_clicks, cancel_clicks,
                         type_dropdown_values, cgc_node_values, cgs_node_values,
                         sgc_node_values, sgs_node_values,
                         mapping_data, pending_state):
        from layout import build_migration_content
        from types import SimpleNamespace

        trigger_id = get_trigger_id()

        if trigger_id == 'pending-settings-store' and pending_data:
            orphans = pending_data.get('orphans', {})
            new_values = pending_data.get('new_values', {})
            subcontexts_by_context = pending_data.get('subcontexts', {})
            rename_map = pending_data.get('rename_map', {})

            orphans_for_ui = {}
            for field, val_map in orphans.items():
                orphans_for_ui[field] = {}
                for old_val, node_dicts in val_map.items():
                    orphans_for_ui[field][old_val] = [SimpleNamespace(**d) for d in node_dicts]

            children, mapping = build_migration_content(
                orphans_for_ui, new_values, subcontexts_by_context,
                rename_map=rename_map,
            )
            return True, children, mapping, dash.no_update, dash.no_update

        if trigger_id == 'btn-migration-cancel':
            # Restore context and type fields from the database
            old_contexts = ConfigManager.get_contexts()
            old_subcontexts = ConfigManager.get_subcontexts()
            sub_lines = []
            for ctx_name in old_contexts:
                subs = old_subcontexts.get(ctx_name, [])
                if subs:
                    sub_lines.append(f"{ctx_name}: {', '.join(subs)}")
                else:
                    sub_lines.append(ctx_name)
            for ctx_name, subs in old_subcontexts.items():
                if ctx_name not in old_contexts:
                    sub_lines.append(f"{ctx_name}: {', '.join(subs)}")
            restored_sub_val = '\n'.join(sub_lines)
            restored_types_val = ', '.join(ConfigManager.get_node_types())
            return False, [], None, restored_sub_val, restored_types_val

        if trigger_id in ('btn-migration-apply', 'btn-migration-skip') and pending_state:
            try:
                ConfigManager.set_hyperparams(pending_state['hp'])
                if 'ts' in pending_state:
                    ConfigManager.set_time_settings(pending_state['ts'])
                if 'ted' in pending_state:
                    ConfigManager.set_time_estimate_defaults(pending_state['ted'])
                ConfigManager.set_obsidian_vault(pending_state['obs_path'])
                ConfigManager.set_gdrive_path(pending_state.get('gdrive_path', ''))
                new_types = pending_state.get('types', [])
                if new_types:
                    ConfigManager.set_node_types(new_types)
                    ConfigManager.sync_shapes_to_types(new_types)
                new_contexts = pending_state.get('contexts', [])
                # Snapshot persisted weights BEFORE set_contexts/set_context_weights
                # so weight migration can consult pre-save state for rule-2 (rename).
                old_weights = ConfigManager.get_context_weights()
                if new_contexts:
                    ConfigManager.set_contexts(new_contexts)
                ConfigManager.set_subcontexts(pending_state.get('subcontexts', {}))
                pending_weights = pending_state.get('context_weights', {}) or {}
                # Only honor the rename map when the user clicked Apply; Skip
                # means "don't migrate", so filter-only (empty rename_map).
                rename_map: dict = {}
                if trigger_id == 'btn-migration-apply' and isinstance(mapping_data, dict):
                    rename_map = _build_rename_map_from_per_node_choices(
                        mapping_data.get('ctx_nodes', []), cgc_node_values,
                    )
                ConfigManager.set_context_weights(_migrate_context_weights(
                    old_weights, pending_weights, new_contexts or [], rename_map,
                ))

                pending_shapes = pending_state.get('shapes', {})
                if pending_shapes:
                    ConfigManager.set_node_shapes(pending_shapes)
                pending_colors = pending_state.get('colors', {})
                if pending_colors:
                    ConfigManager.set_node_colors(pending_colors)
                if 'linter' in pending_state:
                    ConfigManager.set_titlecase_linter(pending_state['linter'])
                if 'gl' in pending_state:
                    ConfigManager.set_graph_layout_defaults(pending_state['gl'])
                if 'dgl' in pending_state:
                    ConfigManager.set_details_graph_layout_defaults(pending_state['dgl'])
                if 'egl' in pending_state:
                    ConfigManager.set_events_graph_layout_defaults(pending_state['egl'])
                if pending_state.get('next_table_rows') is not None:
                    ConfigManager.set_next_table_rows(int(pending_state['next_table_rows']))
            except Exception:
                logger.exception("Failed to save pending settings")

            if trigger_id == 'btn-migration-apply' and mapping_data:
                new_subcontexts = pending_state.get('subcontexts', {})

                type_entries = mapping_data.get('type', []) if isinstance(mapping_data, dict) else []
                for i, entry in enumerate(type_entries):
                    if i >= len(type_dropdown_values) or not type_dropdown_values[i]:
                        continue
                    manager.apply_node_migration(entry['node_name'], entry['field'],
                                                 type_dropdown_values[i], new_subcontexts)

                ctx_nodes = mapping_data.get('ctx_nodes', []) if isinstance(mapping_data, dict) else []
                _apply_per_node_migrations(manager, ctx_nodes, cgc_node_values,
                                            cgs_node_values, new_subcontexts)

                sub_nodes = mapping_data.get('sub_nodes', []) if isinstance(mapping_data, dict) else []
                _apply_per_node_migrations(manager, sub_nodes, sgc_node_values,
                                            sgs_node_values, new_subcontexts)

            return False, [], None, dash.no_update, dash.no_update

        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    def _filtered_sub_options(ctx_val, subcontexts_map):
        if ctx_val and ctx_val not in ('__keep__', '__clear__'):
            subs = sort_subcontexts(subcontexts_map.get(ctx_val, []))
        else:
            subs = sort_subcontexts(
                [s for ss in subcontexts_map.values() for s in ss]
            )
        opts = [{"label": s, "value": s} for s in subs]
        opts += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]
        default = subs[0] if subs else "__keep__"
        return opts, default

    def _per_row_filter(ctx_vals, sub_vals, pending_data):
        """Shared body for per-node ctx→sub cascading callbacks.

        Updates only the triggered row's options. Preserves the row's current
        sub value when it remains valid under the new ctx — this is what
        keeps bulk-apply from being clobbered when its programmatic ctx writes
        re-trigger this callback.
        """
        if not ctx_vals:
            return dash.no_update, dash.no_update
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return [dash.no_update] * len(ctx_vals), [dash.no_update] * len(ctx_vals)
        triggered_idx = triggered.get('index')
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_opts = [dash.no_update] * len(ctx_vals)
        new_vals = [dash.no_update] * len(ctx_vals)
        for pos, inp in enumerate(ctx.inputs_list[0]):
            if inp.get('id', {}).get('index') == triggered_idx:
                opts, default = _filtered_sub_options(ctx_vals[pos], subcontexts_map)
                new_opts[pos] = opts
                current_sub = sub_vals[pos] if pos < len(sub_vals) else None
                valid_subs = {o['value'] for o in opts}
                new_vals[pos] = dash.no_update if current_sub in valid_subs else default
                break
        return new_opts, new_vals

    # --- Migration: per-node cascading filter for context-orphan section ---
    @app.callback(
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "options"),
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        Input({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_cgs_node_options(cgc_vals, cgs_vals, pending_data):
        return _per_row_filter(cgc_vals, cgs_vals, pending_data)

    # --- Migration: per-node cascading filter for subcontext-orphan section ---
    @app.callback(
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "options"),
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        Input({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_sgs_node_options(sgc_vals, sgs_vals, pending_data):
        return _per_row_filter(sgc_vals, sgs_vals, pending_data)

    def _bulk_cascading(bulk_ctx_vals, pending_data):
        """Cascading filter for the per-group bulk-apply ctx → sub dropdown."""
        if not bulk_ctx_vals:
            return dash.no_update, dash.no_update
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return ([dash.no_update] * len(bulk_ctx_vals),
                    [dash.no_update] * len(bulk_ctx_vals))
        triggered_idx = triggered.get('index')
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_opts = [dash.no_update] * len(bulk_ctx_vals)
        new_vals = [dash.no_update] * len(bulk_ctx_vals)
        for pos, inp in enumerate(ctx.inputs_list[0]):
            if inp.get('id', {}).get('index') == triggered_idx:
                opts, default = _filtered_sub_options(bulk_ctx_vals[pos], subcontexts_map)
                new_opts[pos] = opts
                new_vals[pos] = default
                break
        return new_opts, new_vals

    # --- Migration: cascading filter for ctx-orphan bulk row ---
    @app.callback(
        Output({"type": "migration-bulk-cgs", "index": dash.ALL}, "options"),
        Output({"type": "migration-bulk-cgs", "index": dash.ALL}, "value"),
        Input({"type": "migration-bulk-cgc", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_bulk_cgs_options(bulk_ctx_vals, pending_data):
        return _bulk_cascading(bulk_ctx_vals, pending_data)

    # --- Migration: cascading filter for sub-orphan bulk row ---
    @app.callback(
        Output({"type": "migration-bulk-sgs", "index": dash.ALL}, "options"),
        Output({"type": "migration-bulk-sgs", "index": dash.ALL}, "value"),
        Input({"type": "migration-bulk-sgc", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_bulk_sgs_options(bulk_ctx_vals, pending_data):
        return _bulk_cascading(bulk_ctx_vals, pending_data)

    def _bulk_apply(entries_key, ctx_dd_type, sub_dd_type,
                    bulk_ctx_vals, bulk_sub_vals, mapping_data, pending_data,
                    n_ctx_outputs):
        """Push a single (ctx, sub) pair to every per-node row in the
        triggered group. Returns (ctx_values, sub_values, sub_options) lists
        sized to the per-node dropdowns; rows outside the group get no_update.
        """
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict) or n_ctx_outputs == 0:
            return ([dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs)
        group_i = triggered.get('index')
        entries = (mapping_data or {}).get(entries_key, [])
        # Bulk dropdowns are indexed per group; pick the values for THIS group.
        new_ctx = bulk_ctx_vals[group_i] if group_i < len(bulk_ctx_vals) else None
        new_sub = bulk_sub_vals[group_i] if group_i < len(bulk_sub_vals) else None
        if not new_ctx:
            return ([dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs,
                    [dash.no_update] * n_ctx_outputs)
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        sub_opts, _ = _filtered_sub_options(new_ctx, subcontexts_map)
        ctx_out = [dash.no_update] * n_ctx_outputs
        sub_out = [dash.no_update] * n_ctx_outputs
        opts_out = [dash.no_update] * n_ctx_outputs
        for i, entry in enumerate(entries):
            if i >= n_ctx_outputs:
                break
            if entry.get('group_idx') == group_i:
                ctx_out[i] = new_ctx
                sub_out[i] = new_sub
                opts_out[i] = sub_opts
        return ctx_out, sub_out, opts_out

    # --- Migration: bulk apply for ctx-orphan group ---
    @app.callback(
        Output({"type": "migration-cgc-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-cgs-node", "index": dash.ALL}, "options", allow_duplicate=True),
        Input({"type": "migration-bulk-cg-apply", "index": dash.ALL}, "n_clicks"),
        State({"type": "migration-bulk-cgc", "index": dash.ALL}, "value"),
        State({"type": "migration-bulk-cgs", "index": dash.ALL}, "value"),
        State({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def bulk_apply_cg(n_clicks_list, bulk_ctx_vals, bulk_sub_vals,
                      cgc_node_vals, mapping_data, pending_data):
        if not any(n_clicks_list):
            return (dash.no_update, dash.no_update, dash.no_update)
        return _bulk_apply('ctx_nodes', 'migration-cgc-node', 'migration-cgs-node',
                           bulk_ctx_vals, bulk_sub_vals, mapping_data, pending_data,
                           len(cgc_node_vals))

    # --- Migration: bulk apply for sub-orphan group ---
    @app.callback(
        Output({"type": "migration-sgc-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "value", allow_duplicate=True),
        Output({"type": "migration-sgs-node", "index": dash.ALL}, "options", allow_duplicate=True),
        Input({"type": "migration-bulk-sg-apply", "index": dash.ALL}, "n_clicks"),
        State({"type": "migration-bulk-sgc", "index": dash.ALL}, "value"),
        State({"type": "migration-bulk-sgs", "index": dash.ALL}, "value"),
        State({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def bulk_apply_sg(n_clicks_list, bulk_ctx_vals, bulk_sub_vals,
                      sgc_node_vals, mapping_data, pending_data):
        if not any(n_clicks_list):
            return (dash.no_update, dash.no_update, dash.no_update)
        return _bulk_apply('sub_nodes', 'migration-sgc-node', 'migration-sgs-node',
                           bulk_ctx_vals, bulk_sub_vals, mapping_data, pending_data,
                           len(sgc_node_vals))

    # --- Settings: Auto-dismiss status message ---
    @app.callback(
        Output('settings-save-status', 'children', allow_duplicate=True),
        Output('settings-clear-interval', 'disabled', allow_duplicate=True),
        Input('settings-clear-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def clear_settings_message(n):
        if n > 0:
            return "", True
        return dash.no_update, dash.no_update

    # --- Settings: Apply saved Next Table default immediately ---
    @app.callback(
        Output('suggestion-count-store', 'data', allow_duplicate=True),
        Output('suggestion-count-display', 'children', allow_duplicate=True),
        Input('settings-save-status', 'children'),
        State('setting-next-table-rows', 'value'),
        prevent_initial_call=True,
    )
    def apply_next_table_default(status, next_table_rows_val):
        if status != "Settings saved" or next_table_rows_val is None:
            return dash.no_update, dash.no_update
        try:
            count = max(1, min(100, int(next_table_rows_val)))
        except (TypeError, ValueError):
            return dash.no_update, dash.no_update
        return count, str(count)

    @app.callback(
        Output('suggestion-count-store', 'data', allow_duplicate=True),
        Output('suggestion-count-display', 'children', allow_duplicate=True),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def apply_pending_next_table_default(_apply_clicks, _skip_clicks, pending_state):
        if get_trigger_id() not in ('btn-migration-apply', 'btn-migration-skip'):
            return dash.no_update, dash.no_update
        count_val = (pending_state or {}).get('next_table_rows')
        if count_val is None:
            return dash.no_update, dash.no_update
        try:
            count = max(1, min(100, int(count_val)))
        except (TypeError, ValueError):
            return dash.no_update, dash.no_update
        return count, str(count)

    # --- Settings: Restore Default Graph Layout ---
    @app.callback(
        Output('setting-graph-edge-length', 'value', allow_duplicate=True),
        Output('setting-graph-gravity', 'value', allow_duplicate=True),
        Output('setting-graph-repulsion', 'value', allow_duplicate=True),
        Output('setting-details-graph-edge-length', 'value', allow_duplicate=True),
        Output('setting-details-graph-gravity', 'value', allow_duplicate=True),
        Output('setting-details-graph-repulsion', 'value', allow_duplicate=True),
        Output('setting-events-graph-edge-length', 'value', allow_duplicate=True),
        Output('setting-events-graph-gravity', 'value', allow_duplicate=True),
        Output('setting-events-graph-repulsion', 'value', allow_duplicate=True),
        Input('btn-restore-graph-layout', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_graph_layout(n_clicks):
        if not n_clicks:
            return (dash.no_update,) * 9
        from config import DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT, DEFAULT_EVENTS_GRAPH_LAYOUT
        return (
            DEFAULT_GRAPH_LAYOUT['edge_length'],
            DEFAULT_GRAPH_LAYOUT['gravity'],
            DEFAULT_GRAPH_LAYOUT['repulsion'],
            DEFAULT_DETAILS_GRAPH_LAYOUT['edge_length'],
            DEFAULT_DETAILS_GRAPH_LAYOUT['gravity'],
            DEFAULT_DETAILS_GRAPH_LAYOUT['repulsion'],
            DEFAULT_EVENTS_GRAPH_LAYOUT['edge_length'],
            DEFAULT_EVENTS_GRAPH_LAYOUT['gravity'],
            DEFAULT_EVENTS_GRAPH_LAYOUT['repulsion'],
        )

    # --- Settings: Apply graph layout defaults to canvas sliders ---
    @app.callback(
        Output('graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('graph-settings-gravity', 'value', allow_duplicate=True),
        Output('graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('details-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('details-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('details-graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('events-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('events-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('events-graph-settings-repulsion', 'value', allow_duplicate=True),
        Input('btn-settings-save', 'n_clicks'),
        prevent_initial_call=True,
    )
    def apply_graph_defaults_to_sliders(n_clicks):
        if not n_clicks:
            return (dash.no_update,) * 9
        from config import DEFAULT_GRAPH_LAYOUT, DEFAULT_DETAILS_GRAPH_LAYOUT, DEFAULT_EVENTS_GRAPH_LAYOUT
        gl = ConfigManager.get_graph_layout_defaults()
        dgl = ConfigManager.get_details_graph_layout_defaults()
        egl = ConfigManager.get_events_graph_layout_defaults()
        return (
            gl.get('edge_length', DEFAULT_GRAPH_LAYOUT['edge_length']),
            gl.get('gravity', DEFAULT_GRAPH_LAYOUT['gravity']),
            gl.get('repulsion', DEFAULT_GRAPH_LAYOUT['repulsion']),
            dgl.get('edge_length', DEFAULT_DETAILS_GRAPH_LAYOUT['edge_length']),
            dgl.get('gravity', DEFAULT_DETAILS_GRAPH_LAYOUT['gravity']),
            dgl.get('repulsion', DEFAULT_DETAILS_GRAPH_LAYOUT['repulsion']),
            egl.get('edge_length', DEFAULT_EVENTS_GRAPH_LAYOUT['edge_length']),
            egl.get('gravity', DEFAULT_EVENTS_GRAPH_LAYOUT['gravity']),
            egl.get('repulsion', DEFAULT_EVENTS_GRAPH_LAYOUT['repulsion']),
        )

    # --- Settings: Restore Default Shapes ---
    @app.callback(
        Output('setting-node-shapes-container', 'children', allow_duplicate=True),
        Input('btn-restore-shapes', 'n_clicks'),
        State('setting-node-types', 'value'),
        prevent_initial_call=True,
    )
    def restore_default_shapes(n_clicks, types_text):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_SHAPES
        return _build_shape_rows(_display_types_from_text(types_text), DEFAULT_NODE_SHAPES)

    # --- Settings: Restore Default Status Colors ---
    @app.callback(
        Output('setting-node-status-colors-container', 'children', allow_duplicate=True),
        Input('btn-restore-status-colors', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_status_colors(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_COLORS
        return _build_status_color_rows(DEFAULT_NODE_COLORS)

    # --- Settings: Restore Default Type Colors ---
    @app.callback(
        Output('setting-node-type-colors-container', 'children', allow_duplicate=True),
        Input('btn-restore-type-colors', 'n_clicks'),
        State('setting-node-types', 'value'),
        prevent_initial_call=True,
    )
    def restore_default_type_colors(n_clicks, types_text):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_COLORS
        return _build_type_color_rows(_display_types_from_text(types_text), DEFAULT_NODE_COLORS)

