"""
Callback definitions for the Settings tab.
"""

import logging
import dash
from dash import html, Input, Output, State, ALL, ctx
import dash_bootstrap_components as dbc
from graph_manager import GraphManager
from config import ConfigManager
from typing import Tuple, Any
from callback_helpers import get_trigger_id

logger = logging.getLogger(__name__)

manager = GraphManager()


def register_settings_callbacks(app):

    # --- Settings: Load when Settings tab activates ---
    @app.callback(
        Output('hp-wv', 'value'),
        Output('hp-wi', 'value'),
        Output('hp-dh', 'value'),
        Output('hp-ds', 'value'),
        Output('hp-dsyn', 'value'),
        Output('hp-we', 'value'),
        Output('hp-wt', 'value'),
        Output('hp-beta', 'value'),
        Output('hp-goal-boost', 'value'),
        Output('setting-node-types', 'value'),
        Output('setting-subcontexts', 'value'),
        Output('setting-hp-profile', 'value'),
        Output('setting-obsidian-path', 'value'),
        Output('setting-gdrive-path', 'value'),
        Output('setting-node-shapes-container', 'children'),
        Output('setting-node-status-colors-container', 'children'),
        Output('setting-node-type-colors-container', 'children'),
        Output('setting-hpw', 'value'),
        Output('setting-hpm', 'value'),
        Output('setting-default-time-unit', 'value'),
        Output('setting-default-time-o', 'value'),
        Output('setting-default-time-m', 'value'),
        Output('setting-default-time-p', 'value'),
        Output('setting-linter-enabled', 'value'),
        Output('setting-linter-exclusions', 'value'),
        Input('main-tabs', 'active_tab'),
        prevent_initial_call=True,
    )
    def load_settings(active_tab: str) -> Tuple[Any, ...]:
        if active_tab != 'tab-settings':
            return (dash.no_update,) * 25

        hp = ConfigManager.get_hyperparams()
        node_types = ConfigManager.get_node_types()
        contexts = ConfigManager.get_contexts()
        subcontexts = ConfigManager.get_subcontexts()
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
        display_types = node_types.copy()
        for ft in ["Goal"]:
            if ft not in display_types:
                display_types.append(ft)

        shape_options = [
            {"label": s.title(), "value": s}
            for s in ["ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                       "diamond", "octagon", "round-rectangle", "vee"]
        ]
        shape_rows = []
        for t in display_types:
            shape_rows.append(dbc.Row([
                dbc.Col(dbc.Label(t, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": "setting-shape", "index": t},
                    options=shape_options,
                    value=shapes.get(t, "ellipse"),
                ), width=8),
            ], className="mb-2"))

        colors = ConfigManager.get_node_colors()

        def _color_row(label, key):
            return dbc.Row([
                dbc.Col(dbc.Label(label, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": key},
                    type="color",
                    value=colors.get(key, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    colors.get(key, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2")

        status_color_rows = [
            _color_row("Open", "Open"),
            _color_row("Blocked", "Blocked"),
            _color_row("Done", "Done"),
        ]
        type_color_rows = [
            _color_row("Goal", "Goal"),
            _color_row("Resource", "Resource"),
        ]

        ts = ConfigManager.get_time_settings()
        from config import DEFAULT_TIME_ESTIMATE_DEFAULTS
        ted = ConfigManager.get_time_estimate_defaults()

        linter = ConfigManager.get_titlecase_linter()
        linter_enabled_val = ["enabled"] if linter.get('enabled', True) else []
        linter_exclusions_val = ', '.join(linter.get('exclusions', []))

        return (
            hp.get('w_v', 1.0), hp.get('w_i', 1.0),
            hp.get('d_H', 0.6), hp.get('d_S', 0.25), hp.get('d_Syn', 0.35),
            hp.get('w_e', 2.5), hp.get('w_t', 1.0), hp.get('beta', 0.85),
            hp.get('goal_boost', 1.5),
            ', '.join(node_types),
            sub_val,
            profile,
            obs_path,
            gdrive_path,
            shape_rows,
            status_color_rows,
            type_color_rows,
            ts.get('hours_per_week', 40),
            ts.get('hours_per_month', 160),
            ted.get('unit', DEFAULT_TIME_ESTIMATE_DEFAULTS['unit']),
            ted.get('optimistic', DEFAULT_TIME_ESTIMATE_DEFAULTS['optimistic']),
            ted.get('expected', DEFAULT_TIME_ESTIMATE_DEFAULTS['expected']),
            ted.get('pessimistic', DEFAULT_TIME_ESTIMATE_DEFAULTS['pessimistic']),
            linter_enabled_val,
            linter_exclusions_val,
        )

    # --- Settings: Apply Hyperparameter Profile ---
    @app.callback(
        Output('hp-wv', 'value', allow_duplicate=True),
        Output('hp-wi', 'value', allow_duplicate=True),
        Output('hp-dh', 'value', allow_duplicate=True),
        Output('hp-ds', 'value', allow_duplicate=True),
        Output('hp-dsyn', 'value', allow_duplicate=True),
        Output('hp-we', 'value', allow_duplicate=True),
        Output('hp-wt', 'value', allow_duplicate=True),
        Output('hp-beta', 'value', allow_duplicate=True),
        Output('hp-goal-boost', 'value', allow_duplicate=True),
        Input('setting-hp-profile', 'value'),
        prevent_initial_call=True,
    )
    def apply_profile(profile_val):
        from config import PROFILES
        if profile_val in PROFILES:
            p = PROFILES[profile_val]
            return (p['w_v'], p['w_i'], p['d_H'], p['d_S'], p['d_Syn'],
                    p['w_e'], p['w_t'], p['beta'], p.get('goal_boost', 1.5))
        return (dash.no_update,) * 9

    # --- Settings: Sync Time Estimates ---
    @app.callback(
        Output('setting-hpw', 'value', allow_duplicate=True),
        Output('setting-hpm', 'value', allow_duplicate=True),
        Input('setting-hpw', 'value'),
        Input('setting-hpm', 'value'),
        prevent_initial_call=True,
    )
    def sync_time_settings(hpw, hpm):
        triggered = ctx.triggered_id
        if not triggered:
            return dash.no_update, dash.no_update
        try:
            if triggered == 'setting-hpw' and hpw is not None:
                return dash.no_update, round(float(hpw) * 4.0, 2)
            elif triggered == 'setting-hpm' and hpm is not None:
                return round(float(hpm) / 4.0, 2), dash.no_update
        except Exception:
            pass
        return dash.no_update, dash.no_update

    # --- Settings: Save ---
    @app.callback(
        Output('settings-save-status', 'children'),
        Output('pending-settings-store', 'data'),
        Output('settings-clear-interval', 'disabled'),
        Output('settings-clear-interval', 'n_intervals'),
        Input('btn-settings-save', 'n_clicks'),
        State('hp-wv', 'value'), State('hp-wi', 'value'),
        State('hp-dh', 'value'), State('hp-ds', 'value'), State('hp-dsyn', 'value'),
        State('hp-we', 'value'), State('hp-wt', 'value'), State('hp-beta', 'value'),
        State('hp-goal-boost', 'value'),
        State('setting-node-types', 'value'),
        State('setting-subcontexts', 'value'),
        State('setting-obsidian-path', 'value'),
        State('setting-gdrive-path', 'value'),
        State({"type": "setting-shape", "index": ALL}, "value"),
        State({"type": "setting-shape", "index": ALL}, "id"),
        State({"type": "setting-color", "index": ALL}, "value"),
        State({"type": "setting-color", "index": ALL}, "id"),
        State('setting-hpw', 'value'), State('setting-hpm', 'value'),
        State('setting-default-time-unit', 'value'),
        State('setting-default-time-o', 'value'),
        State('setting-default-time-m', 'value'),
        State('setting-default-time-p', 'value'),
        State('setting-hp-profile', 'value'),
        State('setting-linter-enabled', 'value'),
        State('setting-linter-exclusions', 'value'),
        prevent_initial_call=True,
    )
    def save_settings(n_clicks, wv, wi, dh, ds, dsyn, we, wt, beta, goal_boost,
                      n_types_val, subcontexts_val, obs_path, gdrive_path,
                      shape_values, shape_ids, color_values, color_ids,
                      hpw, hpm,
                      def_time_unit, def_time_o, def_time_m, def_time_p, hp_profile,
                      linter_enabled_val, linter_exclusions_val):
        if not n_clicks:
            return dash.no_update, dash.no_update, dash.no_update, dash.no_update

        try:
            new_hp = {
                'w_v': float(wv), 'w_i': float(wi),
                'd_H': float(dh), 'd_S': float(ds), 'd_Syn': float(dsyn),
                'w_e': float(we), 'w_t': float(wt), 'beta': float(beta),
                'goal_boost': float(goal_boost) if goal_boost is not None else 1.5,
            }

            new_ts = {
                'hours_per_week': float(hpw) if hpw is not None else 40,
                'hours_per_month': float(hpm) if hpm is not None else 160,
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

            old_sub_flat = [s for subs in old_subcontexts.values() for s in subs]
            new_sub_flat = [s for subs in new_subcontexts.values() for s in subs]

            orphans = {}
            type_orphans = manager.find_orphaned_nodes('type', old_types, new_types)
            if type_orphans:
                orphans['type'] = {k: [n.name for n in v] for k, v in type_orphans.items()}
            ctx_orphans = manager.find_orphaned_nodes('context', old_contexts, new_contexts)
            if ctx_orphans:
                orphans['context'] = {k: [n.name for n in v] for k, v in ctx_orphans.items()}
            sub_orphans = manager.find_orphaned_nodes('subcontext', old_sub_flat, new_sub_flat)
            if sub_orphans:
                orphans['subcontext'] = {k: [n.name for n in v] for k, v in sub_orphans.items()}

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
                pending = {
                    'hp': new_hp,
                    'ts': new_ts,
                    'ted': new_ted,
                    'obs_path': obs_path,
                    'gdrive_path': gdrive_path or "",
                    'types': new_types,
                    'contexts': new_contexts,
                    'subcontexts': new_subcontexts,
                    'shapes': pending_shapes,
                    'colors': pending_colors,
                    'linter': new_linter,
                    'orphans': orphans,
                    'new_values': {
                        'type': new_types,
                        'context': new_contexts,
                        'subcontext': new_sub_flat,
                    }
                }
                return "Migration required \u2014 check the migration dialog.", pending, False, 0

            ConfigManager.set_hp_profile(hp_profile or "Custom")
            ConfigManager.set_hyperparams(new_hp)
            ConfigManager.set_time_settings(new_ts)
            ConfigManager.set_time_estimate_defaults(new_ted)
            ConfigManager.set_obsidian_vault(obs_path)
            ConfigManager.set_gdrive_path(gdrive_path or "")
            if new_types:
                ConfigManager.set_node_types(new_types)
                ConfigManager.sync_shapes_to_types(new_types)
            if new_contexts:
                ConfigManager.set_contexts(new_contexts)
            ConfigManager.set_subcontexts(new_subcontexts)

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

            return "Settings saved.", dash.no_update, False, 0

        except Exception:
            logger.exception("Failed to save settings")
            return "Error saving settings.", dash.no_update, False, 0

    # --- Migration Modal ---
    @app.callback(
        Output('modal-migration', 'is_open'),
        Output('migration-modal-body', 'children'),
        Output('migration-mapping-store', 'data'),
        Input('pending-settings-store', 'data'),
        Input('btn-migration-apply', 'n_clicks'),
        Input('btn-migration-skip', 'n_clicks'),
        State({"type": "migration-dropdown", "index": dash.ALL}, "value"),
        State({"type": "migration-cgc", "index": dash.ALL}, "value"),
        State({"type": "migration-cgs", "index": dash.ALL}, "value"),
        State({"type": "migration-sgc", "index": dash.ALL}, "value"),
        State({"type": "migration-sgs", "index": dash.ALL}, "value"),
        State('migration-mapping-store', 'data'),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True
    )
    def handle_migration(pending_data, apply_clicks, skip_clicks,
                         type_dropdown_values, cgc_values, cgs_values, sgc_values, sgs_values,
                         mapping_data, pending_state):
        from layout import build_migration_content

        trigger_id = get_trigger_id()

        if trigger_id == 'pending-settings-store' and pending_data:
            orphans = pending_data.get('orphans', {})
            new_values = pending_data.get('new_values', {})
            subcontexts_by_context = pending_data.get('subcontexts', {})

            orphans_for_ui = {}
            for field, val_map in orphans.items():
                orphans_for_ui[field] = {}
                for old_val, node_names in val_map.items():
                    orphans_for_ui[field][old_val] = [type('N', (), {'name': n})() for n in node_names]

            children, mapping = build_migration_content(orphans_for_ui, new_values, subcontexts_by_context)
            return True, children, mapping

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
                if new_contexts:
                    ConfigManager.set_contexts(new_contexts)
                ConfigManager.set_subcontexts(pending_state.get('subcontexts', {}))

                pending_shapes = pending_state.get('shapes', {})
                if pending_shapes:
                    ConfigManager.set_node_shapes(pending_shapes)
                pending_colors = pending_state.get('colors', {})
                if pending_colors:
                    ConfigManager.set_node_colors(pending_colors)
                if 'linter' in pending_state:
                    ConfigManager.set_titlecase_linter(pending_state['linter'])
            except Exception:
                logger.exception("Failed to save pending settings")

            if trigger_id == 'btn-migration-apply' and mapping_data:
                new_subcontexts = pending_state.get('subcontexts', {})

                type_entries = mapping_data.get('type', []) if isinstance(mapping_data, dict) else mapping_data
                for i, entry in enumerate(type_entries):
                    if i >= len(type_dropdown_values) or not type_dropdown_values[i]:
                        continue
                    manager.apply_node_migration(entry['node_name'], entry['field'],
                                                 type_dropdown_values[i], new_subcontexts)

                def _apply_group(groups, ctx_vals, sub_vals):
                    for i, group in enumerate(groups):
                        ctx_val = ctx_vals[i] if i < len(ctx_vals) else None
                        sub_val = sub_vals[i] if i < len(sub_vals) else None
                        for node_name in group['node_names']:
                            if ctx_val and ctx_val not in ('__keep__',):
                                manager.apply_node_migration(node_name, 'context', ctx_val, new_subcontexts)
                            if sub_val and sub_val not in ('__keep__',):
                                manager.apply_node_migration(node_name, 'subcontext', sub_val, new_subcontexts)

                ctx_groups = mapping_data.get('ctx_groups', []) if isinstance(mapping_data, dict) else []
                _apply_group(ctx_groups, cgc_values, cgs_values)

                sub_groups = mapping_data.get('sub_groups', []) if isinstance(mapping_data, dict) else []
                _apply_group(sub_groups, sgc_values, sgs_values)

            return False, [], None

        return dash.no_update, dash.no_update, dash.no_update

    def _filtered_sub_options(ctx_val, subcontexts_map):
        if ctx_val and ctx_val not in ('__keep__', '__clear__'):
            subs = subcontexts_map.get(ctx_val, [])
        else:
            subs = [s for ss in subcontexts_map.values() for s in ss]
        opts = [{"label": s, "value": s} for s in subs]
        opts += [{"label": "Keep existing", "value": "__keep__"}, {"label": "Clear (set to none)", "value": "__clear__"}]
        default = subs[0] if subs else "__keep__"
        return opts, default

    # --- Migration: filter subcontext options for context-change groups ---
    @app.callback(
        Output({"type": "migration-cgs", "index": dash.ALL}, "options"),
        Output({"type": "migration-cgs", "index": dash.ALL}, "value"),
        Input({"type": "migration-cgc", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_cgs_options(cgc_values, pending_data):
        if not cgc_values:
            return dash.no_update, dash.no_update
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return [dash.no_update] * len(cgc_values), [dash.no_update] * len(cgc_values)
        triggered_idx = triggered.get('index')
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_opts = [dash.no_update] * len(cgc_values)
        new_vals = [dash.no_update] * len(cgc_values)
        for pos, inp in enumerate(ctx.inputs_list[0]):
            if inp.get('id', {}).get('index') == triggered_idx:
                opts, default = _filtered_sub_options(cgc_values[pos], subcontexts_map)
                new_opts[pos] = opts
                new_vals[pos] = default
                break
        return new_opts, new_vals

    # --- Migration: filter subcontext options for subcontext-change groups ---
    @app.callback(
        Output({"type": "migration-sgs", "index": dash.ALL}, "options"),
        Output({"type": "migration-sgs", "index": dash.ALL}, "value"),
        Input({"type": "migration-sgc", "index": dash.ALL}, "value"),
        State('pending-settings-store', 'data'),
        prevent_initial_call=True,
    )
    def filter_sgs_options(sgc_values, pending_data):
        if not sgc_values:
            return dash.no_update, dash.no_update
        triggered = ctx.triggered_id
        if not isinstance(triggered, dict):
            return [dash.no_update] * len(sgc_values), [dash.no_update] * len(sgc_values)
        triggered_idx = triggered.get('index')
        subcontexts_map = (pending_data or {}).get('subcontexts', {})
        new_opts = [dash.no_update] * len(sgc_values)
        new_vals = [dash.no_update] * len(sgc_values)
        for pos, inp in enumerate(ctx.inputs_list[0]):
            if inp.get('id', {}).get('index') == triggered_idx:
                opts, default = _filtered_sub_options(sgc_values[pos], subcontexts_map)
                new_opts[pos] = opts
                new_vals[pos] = default
                break
        return new_opts, new_vals

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
        node_types = ConfigManager.get_node_types()
        display_types = node_types.copy()
        for ft in ["Goal"]:
            if ft not in display_types:
                display_types.append(ft)

        shape_options = [
            {"label": s.title(), "value": s}
            for s in ["ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                       "diamond", "octagon", "round-rectangle", "vee"]
        ]
        shape_rows = []
        for t in display_types:
            shape_rows.append(dbc.Row([
                dbc.Col(dbc.Label(t, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Select(
                    id={"type": "setting-shape", "index": t},
                    options=shape_options,
                    value=DEFAULT_NODE_SHAPES.get(t, "ellipse"),
                ), width=8),
            ], className="mb-2"))
        return shape_rows

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

        def _color_row(label, key):
            return dbc.Row([
                dbc.Col(dbc.Label(label, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": key},
                    type="color",
                    value=DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2")

        return [
            _color_row("Open", "Open"),
            _color_row("Blocked", "Blocked"),
            _color_row("Done", "Done"),
        ]

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

        def _color_row(label, key):
            return dbc.Row([
                dbc.Col(dbc.Label(label, className="mb-0"), width=4, className="d-flex align-items-center"),
                dbc.Col(dbc.Input(
                    id={"type": "setting-color", "index": key},
                    type="color",
                    value=DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    style={"height": "38px", "padding": "2px"},
                ), width=4),
                dbc.Col(html.Small(
                    DEFAULT_NODE_COLORS.get(key, "#6c757d"),
                    className="text-muted d-flex align-items-center",
                    style={"fontSize": "0.8rem"},
                ), width=4),
            ], className="mb-2")

        return [
            _color_row("Goal", "Goal"),
            _color_row("Resource", "Resource"),
        ]
