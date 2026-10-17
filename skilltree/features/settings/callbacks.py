"""
Callback definitions for the Settings tab.
"""

import logging
from typing import Any, Tuple

import dash
import dash_bootstrap_components as dbc
from dash import ALL, MATCH, Input, Output, State, ctx, html

from skilltree.domain import contexts as context_rules
from skilltree.domain.contexts import (
    CONTEXT_SORT_ALPHABETICAL,
    CONTEXT_SORT_DEFINITION,
    SUBCONTEXT_SORT_ALPHABETICAL,
    SUBCONTEXT_SORT_DEFINITION,
)
from skilltree.domain.models import STATUS_BLOCKED, STATUS_DONE
from skilltree.domain.names import (
    NAME_FORMAT_MODES,
    NAME_FORMAT_NONE,
    NAME_FORMAT_TITLE,
)
from skilltree.domain.profiles import PROFILES
from skilltree.domain.time import capacity_hours, sync_time_fields
from skilltree.features.settings.contexts import (
    CTX_EDIT_STATES,
    editor_state,
    live_rows,
    register_context_editor_callbacks,
)
from skilltree.features.settings.draft import (
    apply_settings,
    changed_settings,
    normalized_sections,
)
from skilltree.features.settings.migration import register_migration_callbacks
from skilltree.features.settings.resources import (
    SECTION_FORM_STATES,
    register_resource_settings_callbacks,
    section_form_rows,
)
from skilltree.store import database
from skilltree.store.resources import get_sections, validate_sections
from skilltree.store import settings
from skilltree.store.settings import (
    DEFAULT_NODE_COLORS,
    DEFAULT_TITLECASE_LINTER,
    SUPPORTED_NODE_TYPES,
)
from skilltree.store.settings import DEFAULT_NODE_SHAPES
from skilltree.features.settings.data import register_data_callbacks
from skilltree.features.settings.about_callbacks import register_about_callbacks

logger = logging.getLogger(__name__)


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
            html.Span(t, className="settings-swatch-label"),
            dbc.Select(
                id={"type": "setting-shape", "index": t},
                options=_shape_options(),
                value=shapes.get(t, "ellipse"),
                className="settings-shape-select",
            ),
        ], className="settings-swatch-row")
        for t in display_types
    ]


def _color_swatch(key, color_val):
    """A color input and its hex, for matching exact colours or checking contrast."""
    return [
        dbc.Input(
            id={"type": "setting-color", "index": key},
            type="color",
            value=color_val,
            className="settings-swatch",
        ),
        html.Small(
            color_val,
            id={"type": "setting-color-hex", "index": key},
            className="settings-swatch-hex",
        ),
    ]


def _build_color_row(label, key, colors):
    color_val = colors.get(key, DEFAULT_NODE_COLORS.get(key, "#6c757d"))  # literal: colour-input value
    return html.Div([
        html.Span(label, className="settings-swatch-label"),
        *_color_swatch(key, color_val),
    ], className="settings-swatch-row")


def _build_status_color_rows(colors):
    return [
        _build_color_row(STATUS_DONE, STATUS_DONE, colors),
        _build_color_row(STATUS_BLOCKED, STATUS_BLOCKED, colors),
        _build_color_row("Now", "Now", colors),
    ]


def _build_type_color_rows(display_types, colors):
    # No label: these sit beside the shape rows, which name each type.
    return [
        html.Div(_color_swatch(
            t, colors.get(t, DEFAULT_NODE_COLORS.get(t, "#6c757d"))),  # literal: colour-input value
            className="settings-swatch-row")
        for t in display_types
    ]


def _clamp(val, lo, hi, default):
    """Clamp a numeric value to [lo, hi], falling back to default if None."""
    try:
        v = float(val) if val is not None else default
    except (ValueError, TypeError):
        return default
    return max(lo, min(hi, v))


def _save_message(plan) -> str:
    """Confirm a save, naming the context changes it made.

    Worded by the same describe_plan as the live line under the rows, so the
    confirmation repeats what the user was told rather than recounting it —
    a renamed context's subcontexts follow it, and are not changes of their own.
    """
    detail = context_rules.describe_plan(plan)
    return f"Settings saved — {detail}" if detail else "Settings saved"


def register_settings_callbacks(app, services):
    manager = services.graph

    # --- Settings: Keep each type colour's hex in step with its picker ---
    app.clientside_callback(
        "function(value) { return value || window.dash_clientside.no_update; }",
        Output({"type": "setting-color-hex", "index": MATCH}, "children"),
        Input({"type": "setting-color", "index": MATCH}, "value"),
        prevent_initial_call=True,
    )


    # --- Settings: Open the Settings modal from the toolbar gear button ---
    @app.callback(
        Output("settings-modal", "is_open"),
        Input("btn-settings-toggle", "n_clicks"),
        State("settings-modal", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_settings_modal(_n_clicks, is_open):
        return dash.no_update if is_open else True

    app.clientside_callback(
        "function(result) { window.SkillTree.settingsClose.finished(result); "
        "return window.dash_clientside.no_update; }",
        Output('settings-close-sink', 'data'),
        Input('settings-close-result', 'data'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """function(message) {
            if (typeof message === 'string' && message.startsWith('Settings saved')) {
                return '';
            }
            return message || '';
        }""",
        Output('settings-save-error', 'children'),
        Input('settings-save-status', 'children'),
    )

    # --- Settings: Show Title Case options only when they apply ---
    @app.callback(
        Output("setting-titlecase-options", "is_open"),
        Input("setting-name-format-mode", "value"),
    )
    def toggle_titlecase_options(format_mode):
        return format_mode == NAME_FORMAT_TITLE


    # --- Settings: Load when Settings tab activates ---
    load_outputs = [
        Output('context-editor-store', 'data'),
        Output('setting-hp-profile', 'value'),
        Output('setting-node-shapes-container', 'children'),
        Output('setting-node-status-colors-container', 'children'),
        Output('setting-node-type-colors-container', 'children'),
        Output('setting-hpd', 'value'),
        Output('setting-hpw', 'value'),
        Output('setting-hpm', 'value'),
        Output('setting-hpy', 'value'),
        Output('setting-name-format-mode', 'value'),
        Output('setting-linter-exclusions', 'value'),
        Output('setting-show-scoring-perf', 'value'),
        Output('setting-subcontext-sort-mode', 'value'),
        Output('setting-context-sort-mode', 'value'),
        Output('setting-time-calibration-enabled', 'value'),
        Output('setting-now-node-cap', 'value'),
        Output('setting-show-hour-equivalents', 'value'),
        Output('settings-save-status', 'children', allow_duplicate=True),
    ]

    @app.callback(*load_outputs, Input('settings-modal', 'is_open'),
                  prevent_initial_call=True)
    def load_settings(is_open: bool) -> Tuple[Any, ...]:
        if not is_open:
            return (dash.no_update,) * len(load_outputs)

        contexts_state = editor_state(manager)
        profile = settings.HP_PROFILE.get()
        if profile not in PROFILES:
            profile = "Sage"

        shapes = settings.NODE_SHAPES.get()
        display_types = _display_types()
        shape_rows = _build_shape_rows(display_types, shapes)
        colors = settings.NODE_COLORS.get()
        status_color_rows = _build_status_color_rows(colors)
        type_color_rows = _build_type_color_rows(display_types, colors)

        ts = settings.TIME_SETTINGS.get()

        name_formatting = settings.NAME_FORMATTING.get()
        name_format_mode = name_formatting['mode']
        linter_exclusions_val = ', '.join(name_formatting.get('exclusions', []))

        # Length sorting remains readable for legacy/programmatic settings, but
        # is no longer a user-facing choice. Present legacy values as the
        # defined order so the two-option radio group always has a selection.
        subcontext_sort_mode = settings.SUBCONTEXT_SORT_MODE.get()
        if subcontext_sort_mode not in (
                SUBCONTEXT_SORT_DEFINITION, SUBCONTEXT_SORT_ALPHABETICAL):
            subcontext_sort_mode = SUBCONTEXT_SORT_DEFINITION
        context_sort_mode = settings.CONTEXT_SORT_MODE.get()
        if context_sort_mode not in (
                CONTEXT_SORT_DEFINITION, CONTEXT_SORT_ALPHABETICAL):
            context_sort_mode = CONTEXT_SORT_DEFINITION

        return (
            contexts_state,
            profile,
            shape_rows,
            status_color_rows,
            type_color_rows,
            round(settings.hours_per_day(), 2),
            ts['hours_per_week'],
            ts['hours_per_month'],
            settings.hours_per_year(),
            name_format_mode,
            linter_exclusions_val,
            ["enabled"] if settings.SHOW_SCORING_PERF.get() else [],
            subcontext_sort_mode,
            context_sort_mode,
            ["enabled"] if settings.TIME_CALIBRATION_ENABLED.get() else [],
            settings.NOW_NODE_CAP.get(),
            ["enabled"] if ts['show_hour_equivalents'] else [],
            '',
        )

    # --- Settings: Sync Time Estimates ---
    # 1 week = 7 days; 1 month = 4 weeks; 1 year = 13 months = 52 weeks (see HOURS_PER_YEAR_MULT).
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

    # --- Settings: Save before closing ---
    @app.callback(
        Output('settings-save-status', 'children'),
        Output('pending-settings-store', 'data'),
        Output('settings-clear-interval', 'disabled'),
        Output('settings-clear-interval', 'n_intervals'),
        Output('context-editor-store', 'data', allow_duplicate=True),
        Output('settings-modal', 'is_open', allow_duplicate=True),
        Output('settings-close-result', 'data'),
        Input('settings-close-request', 'data'),
        State({"type": "setting-shape", "index": ALL}, "value"),
        State({"type": "setting-shape", "index": ALL}, "id"),
        State({"type": "setting-color", "index": ALL}, "value"),
        State({"type": "setting-color", "index": ALL}, "id"),
        State('setting-hpw', 'value'), State('setting-hpm', 'value'),
        State('setting-hp-profile', 'value'),
        State('setting-name-format-mode', 'value'),
        State('setting-linter-exclusions', 'value'),
        State('setting-show-scoring-perf', 'value'),
        State('setting-subcontext-sort-mode', 'value'),
        State('setting-context-sort-mode', 'value'),
        State('setting-time-calibration-enabled', 'value'),
        State('setting-now-node-cap', 'value'),
        *CTX_EDIT_STATES,
        State('resource-section-settings-store', 'data'),
        *SECTION_FORM_STATES,
        State('setting-backup-extra-dir', 'value'),
        State('setting-show-hour-equivalents', 'value'),
        prevent_initial_call=True,
    )
    def save_settings(n_clicks,
                      shape_values, shape_ids, color_values, color_ids,
                      hpw, hpm,
                      hp_profile,
                      name_format_mode, linter_exclusions_val,
                      show_scoring_perf_val, subcontext_sort_mode_val,
                      context_sort_mode_val, time_calibration_val,
                      now_node_cap_val, editor_store,
                      ctx_name_vals, ctx_name_ids, ctx_weight_vals, ctx_weight_ids,
                       ctx_sub_vals, ctx_sub_ids,
                       section_store=None, section_names=None, section_name_ids=None,
                       section_roots=None, section_root_ids=None,
                       section_use_roots=None, section_use_root_ids=None,
                       backup_extra_dir=None, show_hour_equivalents_val=None):
        if not n_clicks:
            return (dash.no_update,) * 7

        def result(message, pending=dash.no_update, editor=dash.no_update, closed=False):
            # Failure messages remain visible until the user fixes the draft.
            return (message, pending, True, 0, editor,
                    False if closed else dash.no_update, n_clicks)

        try:
            # One transaction: a failure anywhere below saves none of it.
            # Every setter and manager call joins it. Early returns below are
            # validation/migration decisions and have written nothing.
            with database.transaction():
                sections = section_form_rows(
                    section_store, section_names, section_name_ids,
                    section_roots, section_root_ids,
                    section_use_roots, section_use_root_ids)
                try:
                    validate_sections(sections)
                except ValueError as exc:
                    return result(html.Span(str(exc), className="text-danger"))
                profile_name = hp_profile if hp_profile in PROFILES else "Sage"

                # Keep simulation policy values that are no longer exposed in the
                # modal while updating the two user-supplied capacity values.
                new_ts = dict(settings.TIME_SETTINGS.get())
                new_ts.update(capacity_hours(hpw, hpm, new_ts))
                if show_hour_equivalents_val is not None:
                    new_ts['show_hour_equivalents'] = 'enabled' in show_hour_equivalents_val

                # The editor rows are the taxonomy. They are diffed against the
                # config as it stands right now, not against the snapshot the
                # store took when the modal opened. With no store at all the
                # editor never loaded — Save beat the modal's first render — so
                # there is no edit to apply. Seeding the rows from the config
                # makes that a no-op rather than an empty taxonomy that would
                # wipe every subcontext and priority.
                if editor_store is None:
                    editor_store = {'rows': context_rules.taxonomy_to_rows(
                        settings.CONTEXTS.get(), settings.SUBCONTEXTS.get(),
                        settings.CONTEXT_WEIGHTS.get())}
                rows = context_rules.normalize_rows(live_rows(
                    editor_store, ctx_name_vals, ctx_name_ids, ctx_weight_vals,
                    ctx_weight_ids, ctx_sub_vals, ctx_sub_ids))
                errors = context_rules.validate_rows(rows)
                if errors:
                    return result("Contexts need a fix — see the note under the rows. "
                                  "Nothing was saved.")

                old_contexts = settings.CONTEXTS.get()
                old_subcontexts = settings.SUBCONTEXTS.get()
                plan = context_rules.plan_taxonomy_change(
                    rows, old_contexts, old_subcontexts)
                new_contexts = plan['contexts']
                new_subcontexts = plan['subcontexts']
                new_ctx_weights = {name: _clamp(w, 0.0, 10.0, 1.0)
                                   for name, w in plan['weights'].items()}
                new_sub_flat = [s for subs in new_subcontexts.values() for s in subs]

                # Annotate dormant orphans with their event names so the migration
                # modal can show "(dormant — in event: X)" — gives the user context
                # for nodes that aren't currently on the canvas but still hold the
                # stale config value.
                _em = services.events

                def _annotate(node):
                    base = {'name': node.name}
                    if node.dormant:
                        base['dormant'] = True
                        event = _em.get_event_for_node(node.name)
                        base['events'] = [event] if event else []
                    return base

                # Only removals can strand a node. Renames and moves are carried
                # onto the nodes below, so they never reach this dialog.
                orphans = {}
                ctx_orphans = manager.find_orphaned_nodes(
                    'context', plan['deleted_contexts'], [])
                if ctx_orphans:
                    # Carry each node's current subcontext so the modal can pre-fill
                    # per-node defaults that preserve subcontexts during a rename.
                    orphans['context'] = {
                        k: [{**_annotate(n), 'subcontext': n.subcontext} for n in v]
                        for k, v in ctx_orphans.items()
                    }
                sub_orphans = manager.find_nodes_by_pairs(plan['deleted_pairs'])
                if sub_orphans:
                    orphans['subcontext'] = {
                        k: [{**_annotate(n), 'context': n.context} for n in v]
                        for k, v in sub_orphans.items()
                    }

                new_name_formatting = {
                    'mode': (name_format_mode if name_format_mode in NAME_FORMAT_MODES
                             else DEFAULT_TITLECASE_LINTER['mode']),
                    'exclusions': [w.strip() for w in (linter_exclusions_val or '').split(',') if w.strip()],
                }
                new_name_formatting['enabled'] = new_name_formatting['mode'] != NAME_FORMAT_NONE

                draft = {
                        'hp_profile': profile_name,
                        'ts': new_ts,
                        'resource_sections': sections,
                        'contexts': new_contexts,
                        'subcontexts': new_subcontexts,
                        'context_weights': new_ctx_weights,
                        'shapes': {**settings.NODE_SHAPES.get(), **{
                            sid['index']: value for sid, value in
                            zip(shape_ids or [], shape_values or []) if value}},
                        'colors': {**settings.NODE_COLORS.get(), **{
                            cid['index']: value for cid, value in
                            zip(color_ids or [], color_values or []) if value}},
                        'name_formatting': new_name_formatting,
                        'show_scoring_perf': bool(show_scoring_perf_val and
                                                  'enabled' in show_scoring_perf_val),
                        'time_calibration_enabled': bool(time_calibration_val and
                                                        'enabled' in time_calibration_val),
                        'now_node_cap': (max(1, min(50, int(now_node_cap_val)))
                                         if now_node_cap_val is not None
                                         else settings.NOW_NODE_CAP.get()),
                        'subcontext_sort_mode': (subcontext_sort_mode_val or
                                                settings.SUBCONTEXT_SORT_MODE.get()),
                        'context_sort_mode': (context_sort_mode_val or
                                             settings.CONTEXT_SORT_MODE.get()),
                        'backup_extra_dir': (str(backup_extra_dir).strip()
                                             if backup_extra_dir is not None
                                             else settings.BACKUP_EXTRA_DIR.get()),
                        'orphans': orphans,
                        'new_values': {
                            'context': new_contexts,
                            'subcontext': new_sub_flat,
                        },
                        # Applied by handle_migration on Apply *and* on Skip:
                        # skipping declines to rehome the orphans, not to make the
                        # rename the user asked for.
                        'ctx_renames': plan['ctx_renames'],
                        'pair_moves': plan['pair_moves'],
                }
                if orphans:
                    return result("Migration required — check the migration dialog.", draft)

                if (not changed_settings(draft)
                        and normalized_sections(sections) == get_sections()
                        and not plan['ctx_renames'] and not plan['pair_moves']):
                    return result(dash.no_update, closed=True)

                manager.apply_taxonomy_migration(plan['ctx_renames'], plan['pair_moves'])
                apply_settings(draft)
                editor = editor_state(manager)
            # Only dismiss after the transaction has committed successfully.
            return result(_save_message(plan), editor=editor, closed=True)

        except Exception:
            logger.exception("Failed to save settings")
            return result("Couldn't save settings. Nothing was changed; the log has the "
                          "details.")


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
        return _build_type_color_rows(_display_types(), DEFAULT_NODE_COLORS)

    register_context_editor_callbacks(app, services)
    register_resource_settings_callbacks(app, services)
    register_migration_callbacks(app, services)
    register_data_callbacks(app, services)
    register_about_callbacks(app, services)

