"""
Callback definitions for the Settings tab.
"""

import logging
import dash
from dash import html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from config import (
    CONTEXT_SORT_ALPHABETICAL,
    CONTEXT_SORT_DEFINITION,
    ConfigManager,
    DEFAULT_NODE_COLORS,
    NAME_FORMAT_MODES,
    NAME_FORMAT_NONE,
    NAME_FORMAT_TITLE,
    PROFILES,
    SUBCONTEXT_SORT_ALPHABETICAL,
    SUBCONTEXT_SORT_DEFINITION,
    SUPPORTED_NODE_TYPES,
    sort_contexts,
    sort_subcontexts)
from models import STATUS_BLOCKED, STATUS_DONE
from typing import Tuple, Any
from callback_helpers import get_trigger_id, build_context_weight_rows, sync_time_fields
from context_rules import detect_context_renames

logger = logging.getLogger(__name__)

manager = GraphManager()


def _display_types():
    return list(SUPPORTED_NODE_TYPES)


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
    color_val = colors.get(key, DEFAULT_NODE_COLORS.get(key, "#6c757d"))  # literal: colour-input value
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
    ], className="d-flex align-items-center gap-2 mb-2")


def _build_status_color_rows(colors):
    return [
        _build_color_row(STATUS_DONE, STATUS_DONE, colors),
        _build_color_row(STATUS_BLOCKED, STATUS_BLOCKED, colors),
        _build_color_row("Now", "Now", colors),
    ]


def _build_type_color_rows(display_types, colors):
    rows = []
    for t in display_types:
        color_val = colors.get(t, DEFAULT_NODE_COLORS.get(t, "#6c757d"))  # literal: colour-input value
        rows.append(html.Div([
            dbc.Input(
                id={"type": "setting-color", "index": t},
                type="color",
                value=color_val,
                style={"height": "38px", "width": "52px", "padding": "2px"},
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


def register_settings_callbacks(app, services=None):
    manager = services.graph if services is not None else globals()['manager']

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

    # --- Settings: Toggle the Scoring Profile info popover ---
    @app.callback(
        Output("popover-hp-profile-info", "is_open"),
        Input("btn-hp-profile-info", "n_clicks"),
        State("popover-hp-profile-info", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_hp_profile_info_popover(_n_clicks, is_open):
        return not is_open

    # --- Settings: Show Title Case options only when they apply ---
    @app.callback(
        Output("setting-titlecase-options", "is_open"),
        Input("setting-name-format-mode", "value"),
    )
    def toggle_titlecase_options(format_mode):
        return format_mode == NAME_FORMAT_TITLE

    # --- Settings: Load when Settings tab activates ---
    @app.callback(
        Output('setting-subcontexts', 'value'),
        Output('setting-hp-profile', 'value'),
        Output('setting-obsidian-path', 'value'),
        Output('setting-gdrive-path', 'value'),
        Output('setting-node-shapes-container', 'children'),
        Output('setting-node-status-colors-container', 'children'),
        Output('setting-node-type-colors-container', 'children'),
        Output('setting-context-weights-container', 'children'),
        Output('setting-hpd', 'value'),
        Output('setting-hpw', 'value'),
        Output('setting-hpm', 'value'),
        Output('setting-hpy', 'value'),
        Output('setting-default-time-unit', 'value'),
        Output('setting-default-time-o', 'value'),
        Output('setting-default-time-m', 'value'),
        Output('setting-default-time-p', 'value'),
        Output('setting-name-format-mode', 'value'),
        Output('setting-linter-exclusions', 'value'),
        Output('setting-show-scoring-perf', 'value'),
        Output('setting-subcontext-sort-mode', 'value'),
        Output('setting-context-sort-mode', 'value'),
        Output('setting-time-calibration-enabled', 'value'),
        Output('setting-now-node-cap', 'value'),
        Input('settings-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def load_settings(is_open: bool) -> Tuple[Any, ...]:
        if not is_open:
            return (dash.no_update,) * 23

        contexts = ConfigManager.get_contexts()
        subcontexts = ConfigManager.get_subcontexts()
        ctx_weights = ConfigManager.get_context_weights()
        obs_path = ConfigManager.get_obsidian_vault()
        gdrive_path = ConfigManager.get_gdrive_path()
        profile = ConfigManager.get_hp_profile()
        if profile not in PROFILES:
            profile = "Sage"

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
        display_types = _display_types()
        shape_rows = _build_shape_rows(display_types, shapes)
        colors = ConfigManager.get_node_colors()
        status_color_rows = _build_status_color_rows(colors)
        type_color_rows = _build_type_color_rows(display_types, colors)

        weight_rows = build_context_weight_rows(sort_contexts(contexts), ctx_weights)

        ts = ConfigManager.get_time_settings()
        from config import DEFAULT_TIME_ESTIMATE_DEFAULTS
        ted = ConfigManager.get_time_estimate_defaults()

        name_formatting = ConfigManager.get_name_formatting()
        name_format_mode = name_formatting.get('mode', NAME_FORMAT_TITLE)
        if name_format_mode not in NAME_FORMAT_MODES:
            name_format_mode = (NAME_FORMAT_TITLE if name_formatting.get('enabled', True)
                                else NAME_FORMAT_NONE)
        linter_exclusions_val = ', '.join(name_formatting.get('exclusions', []))

        # Length sorting remains readable for legacy/programmatic settings, but
        # is no longer a user-facing choice. Present legacy values as the
        # defined order so the two-option radio group always has a selection.
        subcontext_sort_mode = ConfigManager.get_subcontext_sort_mode()
        if subcontext_sort_mode not in (
                SUBCONTEXT_SORT_DEFINITION, SUBCONTEXT_SORT_ALPHABETICAL):
            subcontext_sort_mode = SUBCONTEXT_SORT_DEFINITION
        context_sort_mode = ConfigManager.get_context_sort_mode()
        if context_sort_mode not in (
                CONTEXT_SORT_DEFINITION, CONTEXT_SORT_ALPHABETICAL):
            context_sort_mode = CONTEXT_SORT_DEFINITION

        return (
            sub_val,
            profile,
            obs_path,
            gdrive_path,
            shape_rows,
            status_color_rows,
            type_color_rows,
            weight_rows,
            round(ConfigManager.get_hours_per_day(), 2),
            ts.get('hours_per_week', 40),
            ts.get('hours_per_month', 160),
            ConfigManager.get_hours_per_year(),
            ted.get('unit', DEFAULT_TIME_ESTIMATE_DEFAULTS['unit']),
            ted.get('optimistic', DEFAULT_TIME_ESTIMATE_DEFAULTS['optimistic']),
            ted.get('expected', DEFAULT_TIME_ESTIMATE_DEFAULTS['expected']),
            ted.get('pessimistic', DEFAULT_TIME_ESTIMATE_DEFAULTS['pessimistic']),
            name_format_mode,
            linter_exclusions_val,
            ["enabled"] if ConfigManager.get_show_scoring_perf() else [],
            subcontext_sort_mode,
            context_sort_mode,
            ["enabled"] if ConfigManager.get_time_calibration_enabled() else [],
            ConfigManager.get_now_node_cap(),
        )

    # --- Settings: Sync Time Estimates ---
    # 1 week = 7 days; 1 month = 4 weeks; 1 year = 13 months = 52 weeks (see ConfigManager.HOURS_PER_YEAR_MULT).
    @app.callback(
        Output('setting-hpd', 'value', allow_duplicate=True),
        Output('setting-hpw', 'value', allow_duplicate=True),
        Output('setting-hpm', 'value', allow_duplicate=True),
        Output('setting-hpy', 'value', allow_duplicate=True),
        Input('setting-hpd', 'value'),
        Input('setting-hpw', 'value'),
        Input('setting-hpm', 'value'),
        Input('setting-hpy', 'value'),
        prevent_initial_call=True,
    )
    def sync_time_settings(hpd, hpw, hpm, hpy):
        triggered = ctx.triggered_id
        if not triggered:
            return (dash.no_update,) * 4
        return tuple(dash.no_update if v is None else v
                     for v in sync_time_fields(triggered, hpd, hpw, hpm, hpy))

    # --- Settings: Save ---
    @app.callback(
        Output('settings-save-status', 'children'),
        Output('pending-settings-store', 'data'),
        Output('settings-clear-interval', 'disabled'),
        Output('settings-clear-interval', 'n_intervals'),
        Output('setting-context-weights-container', 'children', allow_duplicate=True),
        Input('btn-settings-save', 'n_clicks'),
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
        State('setting-name-format-mode', 'value'),
        State('setting-linter-exclusions', 'value'),
        State('setting-show-scoring-perf', 'value'),
        State('setting-subcontext-sort-mode', 'value'),
        State('setting-context-sort-mode', 'value'),
        State('setting-time-calibration-enabled', 'value'),
        State('setting-now-node-cap', 'value'),
        prevent_initial_call=True,
    )
    def save_settings(n_clicks, subcontexts_val, obs_path, gdrive_path,
                      shape_values, shape_ids, color_values, color_ids,
                      ctx_weight_values, ctx_weight_ids,
                      hpw, hpm,
                      def_time_unit, def_time_o, def_time_m, def_time_p, hp_profile,
                      name_format_mode, linter_exclusions_val,
                      show_scoring_perf_val, subcontext_sort_mode_val,
                      context_sort_mode_val, time_calibration_val,
                      now_node_cap_val):
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
            profile_name = hp_profile if hp_profile in PROFILES else "Sage"
            new_hp = dict(PROFILES[profile_name])

            new_ctx_weights: dict = {}
            if ctx_weight_ids and ctx_weight_values:
                for wid, wval in zip(ctx_weight_ids, ctx_weight_values):
                    name = wid.get("index")
                    if not name:
                        continue
                    new_ctx_weights[name] = _clamp(wval, 0.0, 10.0, 1.0)

            # Keep simulation policy values that are no longer exposed in the
            # modal while updating the two user-supplied capacity values.
            new_ts = dict(ConfigManager.get_time_settings())
            new_ts.update({
                'hours_per_week': float(hpw) if hpw is not None else 40,
                'hours_per_month': float(hpm) if hpm is not None else 160,
            })

            from config import DEFAULT_TIME_ESTIMATE_DEFAULTS
            new_ted = {
                'optimistic': float(def_time_o) if def_time_o is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['optimistic'],
                'expected': float(def_time_m) if def_time_m is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['expected'],
                'pessimistic': float(def_time_p) if def_time_p is not None else DEFAULT_TIME_ESTIMATE_DEFAULTS['pessimistic'],
                'unit': def_time_unit or DEFAULT_TIME_ESTIMATE_DEFAULTS['unit'],
            }

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

                new_name_formatting = {
                    'mode': (name_format_mode if name_format_mode in NAME_FORMAT_MODES
                             else NAME_FORMAT_TITLE),
                    'exclusions': [w.strip() for w in (linter_exclusions_val or '').split(',') if w.strip()],
                }
                pending = {
                    'hp': new_hp,
                    'hp_profile': profile_name,
                    'ts': new_ts,
                    'ted': new_ted,
                    'obs_path': obs_path,
                    'gdrive_path': gdrive_path or "",
                    'contexts': new_contexts,
                    'subcontexts': new_subcontexts,
                    'context_weights': new_ctx_weights,
                    'shapes': pending_shapes,
                    'colors': pending_colors,
                    'name_formatting': new_name_formatting,
                    'orphans': orphans,
                    'new_values': {
                        'context': new_contexts,
                        'subcontext': new_sub_flat,
                    },
                    'rename_map': detect_context_renames(
                        old_contexts, new_contexts,
                        old_subcontexts, new_subcontexts,
                    ),
                }
                return "Migration required \u2014 check the migration dialog.", pending, False, 0, dash.no_update

            ConfigManager.set_hp_profile(profile_name)
            ConfigManager.set_hyperparams(new_hp)
            ConfigManager.set_time_settings(new_ts)
            ConfigManager.set_time_estimate_defaults(new_ted)
            ConfigManager.set_obsidian_vault(obs_path)
            ConfigManager.set_gdrive_path(gdrive_path or "")
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

            new_name_formatting = {
                'mode': (name_format_mode if name_format_mode in NAME_FORMAT_MODES
                         else NAME_FORMAT_TITLE),
                'exclusions': [w.strip() for w in (linter_exclusions_val or '').split(',') if w.strip()],
            }
            ConfigManager.set_name_formatting(new_name_formatting)

            saved_contexts = new_contexts if new_contexts else ConfigManager.get_contexts()
            refreshed_weight_rows = build_context_weight_rows(
                sort_contexts(saved_contexts), ConfigManager.get_context_weights()
            )
            return "Settings saved", dash.no_update, False, 0, refreshed_weight_rows

        except Exception:
            logger.exception("Failed to save settings")
            return "Error saving settings.", dash.no_update, False, 0, dash.no_update

    # --- Migration Modal ---
    @app.callback(
        Output('modal-migration', 'is_open'),
        Output('migration-modal-body', 'children'),
        Output('migration-mapping-store', 'data'),
        Output('setting-subcontexts', 'value', allow_duplicate=True),
        Input('pending-settings-store', 'data'),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        Input('btn-migration-cancel', 'n_clicks'),
        State({"type": "migration-cgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-cgs-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgc-node", "index": dash.ALL}, "value"),
        State({"type": "migration-sgs-node", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True
    )
    def handle_migration(pending_data, apply_clicks, skip_clicks, cancel_clicks,
                         cgc_node_values, cgs_node_values,
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
            return True, children, mapping, dash.no_update

        if trigger_id == 'btn-migration-cancel':
            # Restore the context field from the database.
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
            return False, [], None, restored_sub_val

        if trigger_id in ('btn-migration-apply', 'btn-migration-skip') and pending_state:
            try:
                ConfigManager.set_hp_profile(
                    pending_state.get('hp_profile', 'Sage'))
                ConfigManager.set_hyperparams(pending_state['hp'])
                if 'ts' in pending_state:
                    ConfigManager.set_time_settings(pending_state['ts'])
                if 'ted' in pending_state:
                    ConfigManager.set_time_estimate_defaults(pending_state['ted'])
                ConfigManager.set_obsidian_vault(pending_state['obs_path'])
                ConfigManager.set_gdrive_path(pending_state.get('gdrive_path', ''))
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
                if 'name_formatting' in pending_state:
                    ConfigManager.set_name_formatting(pending_state['name_formatting'])
            except Exception:
                logger.exception("Failed to save pending settings")

            if trigger_id == 'btn-migration-apply' and mapping_data:
                new_subcontexts = pending_state.get('subcontexts', {})

                ctx_nodes = mapping_data.get('ctx_nodes', []) if isinstance(mapping_data, dict) else []
                _apply_per_node_migrations(manager, ctx_nodes, cgc_node_values,
                                            cgs_node_values, new_subcontexts)

                sub_nodes = mapping_data.get('sub_nodes', []) if isinstance(mapping_data, dict) else []
                _apply_per_node_migrations(manager, sub_nodes, sgc_node_values,
                                            sgs_node_values, new_subcontexts)

            return False, [], None, dash.no_update

        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

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

    # --- Settings: Restore Default Shapes ---
    @app.callback(
        Output('setting-node-shapes-container', 'children', allow_duplicate=True),
        Input('btn-restore-shapes', 'n_clicks'),
        prevent_initial_call=True,
    )
    def restore_default_shapes(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_SHAPES
        return _build_shape_rows(_display_types(), DEFAULT_NODE_SHAPES)

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
        prevent_initial_call=True,
    )
    def restore_default_type_colors(n_clicks):
        if not n_clicks:
            return dash.no_update
        from config import DEFAULT_NODE_COLORS
        return _build_type_color_rows(_display_types(), DEFAULT_NODE_COLORS)

