"""The node editor's fields reacting to each other as the user edits: which show
for a type, the Inherit and Habit switches, and time units and subcontexts.
"""
import dash
from dash import ClientsideFunction, Input, Output, State

from skilltree.domain.contexts import sort_subcontexts
from skilltree.features.editor.form import habit_preview_text
from skilltree.features.editor.values import reexpressed_estimate
from skilltree.store import settings
from skilltree.ui.components.duration import work_time_tooltip
from skilltree.ui.prerender import prerendered


def register_field_callbacks(app, services):
    # --- Type-adaptive field visibility ---
    @app.callback(
        [Output('section-done-time', 'style'),
         Output('section-time-estimates', 'style'),
         Output('section-priority-rank', 'style'),
         Output('section-time-habit-toggle', 'style')],
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )
    @prerendered
    def toggle_type_fields(node_type):
        show = {}
        hide = {'display': 'none'}
        # section-priority-rank stays hidden for every type now: rank is the
        # Goals sidebar's job. The Output is kept so the hidden select the
        # other callbacks read as State still has a container.
        if node_type == 'Goal':
            # Habit toggle hidden — containers must inherit.
            return show, show, hide, hide
        if node_type == 'Milestone':
            return show, show, hide, hide
        # Learn, Action, Resource: full set, habit toggle visible.
        return show, show, hide, show

    # --- Toggle O/M/P / Habit / unit-dropdown visibility based on mode ---
    app.clientside_callback(
        """
        function(time_mode_val, habit_mode_val) {
            var hidden_w = {display: 'none', width: '100px'};
            var visible_w = {width: '100px'};
            var inherit_on = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);
            var habit_on = !!(habit_mode_val && habit_mode_val.indexOf('habit') >= 0);
            if (inherit_on) return [{display: 'none'}, {display: 'none'}, hidden_w];
            if (habit_on) return [{display: 'none'}, {}, hidden_w];
            return [{}, {display: 'none'}, visible_w];
        }
        """,
        Output('section-time-omp', 'style'),
        Output('section-time-habit', 'style'),
        Output('node-time-unit', 'style'),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
    )

    # --- Mutual exclusivity: Habit and Inherit cannot both be ON ---
    # Clientside to eliminate the visible flash of the "other" toggle
    # flipping on before the server bounces it off. Same fix pattern as
    # enforce_locked_time_mode above.
    app.clientside_callback(
        """
        function(inherit_val, habit_val) {
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var trig = triggered.length ? triggered[0].prop_id.split('.')[0] : null;
            if (trig === 'node-time-mode' && inherit_val && inherit_val.indexOf('inherited') >= 0) {
                return [inherit_val, []];
            }
            if (trig === 'node-time-habit-mode' && habit_val && habit_val.indexOf('habit') >= 0) {
                return [[], habit_val];
            }
            return [inherit_val, habit_val];
        }
        """,
        Output('node-time-mode', 'value', allow_duplicate=True),
        Output('node-time-habit-mode', 'value', allow_duplicate=True),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
        prevent_initial_call=True,
    )

    # --- Locked Inherit toggle for Goal / Milestone ---
    # Container types must always inherit time from their children. Forces
    # 'inherited' ON whenever the type is Goal or Milestone, and reveals an
    # inline warning if the user attempts to toggle it off. Runs clientside
    # so the bounce-back happens in the same paint cycle as the click — a
    # server round-trip causes the toggle to visibly flip OFF before
    # snapping back ON. The triggered-IDs check distinguishes user toggles
    # from form-populate cycles (where node-type also fires).
    #
    # Changing the type away from Goal or Milestone used to leave the forced
    # Inherit on: an Action or Resource then had no time of its own and scored
    # at no cost. They get their own estimate back. A Learn may be a header
    # over its children, so it keeps Inherit, with a note saying so.
    app.clientside_callback(
        ClientsideFunction(namespace='editor_form', function_name='lock_time_mode'),
        Output('node-time-mode', 'value', allow_duplicate=True),
        Output('time-mode-warning', 'style'),
        Output('time-mode-warning', 'children'),
        Input('node-time-mode', 'value'),
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )

    # --- Work-time tooltips: habit wording, and live hour rates ---
    # The layout builds these once per page load. The editor heading's text
    # depends on the Habit switch, and both tooltips quote the hour rates, which
    # Settings can change. Settings saves close the modal, so its is_open covers
    # both the open and the close.
    @app.callback(
        Output('node-time-heading-tooltip', 'children'),
        Output('time-calibration-heading-tooltip', 'children'),
        Output('editor-time-settings', 'data'),
        Input('node-time-habit-mode', 'value'),
        Input('settings-modal', 'is_open'),
        prevent_initial_call=True,
    )
    def refresh_work_time_tooltips(habit_mode_val, _settings_open):
        habit = bool(habit_mode_val and 'habit' in habit_mode_val)
        return (work_time_tooltip("habit" if habit else "estimate"),
                work_time_tooltip("actual"), settings.TIME_SETTINGS.get())

    # Display conversions locally while typing; the store uses saved Settings.
    app.clientside_callback(
        ClientsideFunction(namespace='time_hour_hints', function_name='render'),
        [Output(f'node-time-{field}-hours', 'children') for field in ('o', 'm', 'p')],
        [Output(f'node-time-{field}-hours', 'style') for field in ('o', 'm', 'p')],
        Output('node-time-bracket-row', 'className'),
        Input('node-time-o', 'value'),
        Input('node-time-m', 'value'),
        Input('node-time-p', 'value'),
        Input('node-time-unit', 'value'),
        Input('editor-time-settings', 'data'),
    )

    # --- Live total-hours preview for habit mode ---
    @app.callback(
        Output('node-habit-total-preview', 'children'),
        Input('node-habit-duration', 'value'),
        Input('node-habit-duration-unit', 'value'),
        Input('node-habit-intensity-o', 'value'),
        Input('node-habit-intensity-m', 'value'),
        Input('node-habit-intensity-p', 'value'),
        Input('node-habit-days', 'value'),
        prevent_initial_call=True,
    )
    @prerendered
    def update_habit_total_preview(duration, dur_unit, int_o, int_m, int_p, days):
        return habit_preview_text(duration, dur_unit, int_o, int_m, int_p, days)

    # --- Toggle Value/Interest sliders based on value_mode ---
    app.clientside_callback(
        """
        function(value_mode_val) {
            if (value_mode_val && value_mode_val.indexOf('inherited') >= 0) {
                return {display: 'none'};
            }
            return {};
        }
        """,
        Output('section-ratings', 'style'),
        Input('node-value-mode', 'value'),
    )

    # --- Locked Inherit-value toggle for Milestones ---
    # Milestones are transparent checkpoints: their own value/interest/effort
    # must never enter scoring. Force value_mode='inherited' ON whenever the
    # type is Milestone, and show an inline warning if the user tries to clear
    # it. Mirrors the Goal/Milestone time-mode lock above. Goals are NOT locked
    # here — a Goal legitimately carries its own value (see docs/modeling.md).
    # Clientside so the bounce-back happens in the same paint cycle as the
    # click. The triggered-IDs check distinguishes user toggles from form-
    # populate cycles (where node-type also fires).
    app.clientside_callback(
        ClientsideFunction(namespace='editor_form', function_name='lock_value_mode'),
        Output('node-value-mode', 'value', allow_duplicate=True),
        Output('value-mode-warning', 'style'),
        Output('value-mode-warning', 'children'),
        Input('node-value-mode', 'value'),
        Input('node-type', 'value'),
        prevent_initial_call=True,
    )

    # --- Hide Effort slider when the node has no work of its own ---
    # Effort describes a node's own hours, so scoring ignores it when time is
    # inherited (Node.has_no_own_work). A Goal's Effort is decorative too:
    # rank_goals counts only the effort of the tasks beneath it. The caption
    # tells the user why the input is absent so the UI stops asking for a
    # value the system ignores. Inheriting ratings alone keeps the slider.
    app.clientside_callback(
        """
        function(node_type, time_mode_val) {
            var no_own_work = !!(time_mode_val && time_mode_val.indexOf('inherited') >= 0);
            if (node_type === 'Goal' || no_own_work) return [{display: 'none'}, {}];
            return [{}, {display: 'none'}];
        }
        """,
        Output('node-effort-row', 'style'),
        Output('node-effort-caption', 'style'),
        Input('node-type', 'value'),
        Input('node-time-mode', 'value'),
    )

    # --- Auto-convert time estimates when unit dropdown changes ---
    @app.callback(
        Output('node-time-o', 'value', allow_duplicate=True),
        Output('node-time-m', 'value', allow_duplicate=True),
        Output('node-time-p', 'value', allow_duplicate=True),
        Output('node-time-unit-prev', 'data'),
        Input('node-time-unit', 'value'),
        State('node-time-o', 'value'),
        State('node-time-m', 'value'),
        State('node-time-p', 'value'),
        State('node-time-unit-prev', 'data'),
        prevent_initial_call=True,
    )
    def convert_time_unit(new_unit, val_o, val_m, val_p, prev_unit):
        """Re-express time values when the unit selector changes."""
        old_unit = prev_unit or 'hours'
        no_change = dash.no_update, dash.no_update, dash.no_update, new_unit
        if not new_unit or new_unit == old_unit:
            return no_change
        old_mult = settings.time_multiplier(old_unit)
        new_mult = settings.time_multiplier(new_unit)
        if new_mult == 0:
            return no_change
        def _reexpress(v):
            if v is None:
                return v
            return reexpressed_estimate(float(v) * old_mult / new_mult)
        return _reexpress(val_o), _reexpress(val_m), _reexpress(val_p), new_unit

    @app.callback(
        Output('node-subcontext', 'options'),
        Input('node-context', 'value'),
        prevent_initial_call=True,
    )
    @prerendered
    def update_node_subcontexts(ctx):
        base = [{"label": "None", "value": ""}]
        if not ctx:
            return base
        subs = sort_subcontexts(settings.SUBCONTEXTS.get().get(ctx, []),
                                settings.SUBCONTEXT_SORT_MODE.get())
        return base + [{"label": s, "value": s} for s in subs]

    # Clear node-subcontext value when the new context doesn't include it.
    # populate_editor sets a valid pair on edit-load, so this no-ops then;
    # only a user-driven context change to an incompatible context clears.
    app.clientside_callback(
        """
        function(ctx, currentSub, options) {
            if (!currentSub) return window.dash_clientside.no_update;
            const opts = options || [];
            for (let i = 0; i < opts.length; i++) {
                if (opts[i] && opts[i].value === currentSub) {
                    return window.dash_clientside.no_update;
                }
            }
            return '';
        }
        """,
        Output('node-subcontext', 'value', allow_duplicate=True),
        Input('node-subcontext', 'options'),
        State('node-subcontext', 'value'),
        State('node-subcontext', 'options'),
        prevent_initial_call=True,
    )
