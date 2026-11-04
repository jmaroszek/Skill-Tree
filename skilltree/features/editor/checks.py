"""What the node editor says before Save does: an estimate it can't save, a name
that may be a duplicate, and a Now switch it couldn't honor.
"""
import time

from dash import Input, Output, State, html, no_update

from skilltree.domain.models import STATUS_DONE
from skilltree.domain.names import normalize_name_for_comparison
from skilltree.domain.time import (
    HABIT_NO_DAYS,
    habit_estimate_problem,
    time_estimate_problem,
)
from skilltree.features.editor.layout import SAVE_HINT
from skilltree.store import settings
from skilltree.store.commands import node_with_alias
from skilltree.ui import tokens
from skilltree.ui.prerender import prerendered


def register_check_callbacks(app, services):
    manager = services.graph

    # --- Time Estimate Validation ---
    # A newly loaded/reverted form starts quiet. Leaving the section reveals
    # the latest validation result (assets/editor/time_validation.js); validity and
    # the save guards below remain independent of the warning's visibility.
    app.clientside_callback(
        "function(_snapshot) { return 'false'; }",
        Output('section-time-estimates', 'data-validation-ready'),
        Input('editor-pristine-snapshot', 'data'),
    )

    @app.callback(
        Output('time-validation-error', 'children'),
        Output('time-validation-error', 'style'),
        Output('habit-validation-error', 'children'),
        Output('habit-validation-error', 'style'),
        Output('btn-save', 'disabled'),
        # The time fields sit below the fold; hovering Save says why it's off.
        Output('editor-save-tooltip', 'children'),
        Input('node-time-o', 'value'),
        Input('node-time-m', 'value'),
        Input('node-time-p', 'value'),
        Input('node-time-mode', 'value'),
        Input('node-time-habit-mode', 'value'),
        Input('node-habit-duration', 'value'),
        Input('node-habit-intensity-o', 'value'),
        Input('node-habit-intensity-m', 'value'),
        Input('node-habit-intensity-p', 'value'),
        Input('node-habit-days', 'value'),
        prevent_initial_call=True,
    )
    @prerendered
    def validate_time_estimates(time_o, time_m, time_p, time_mode_val, habit_mode_val,
                                habit_duration, habit_o, habit_m, habit_p, habit_days):
        """Disable Save while the time estimate can't be saved, and say why.

        A bracket takes one of the supported (l, m, u) patterns, in order
        (mirroring `expected_time_estimate` in models.py):
          - Expected only          {m}
          - Lower + Upper          {o, p}
          - All three              {o, m, p}

        Inherited time has nothing to check. Habit mode checks its own fields:
        the duration, the minutes bracket and the days. A habit with no days
        yet is prompted by the preview line, so its warning stays empty.
        """
        hidden = tokens.ERROR_TEXT_HIDDEN
        visible = tokens.ERROR_TEXT_VISIBLE
        ok = ("", hidden, "", hidden, False, SAVE_HINT)

        if time_mode_val and 'inherited' in time_mode_val:
            return ok
        if habit_mode_val and 'habit' in habit_mode_val:
            msg = habit_estimate_problem(habit_duration, habit_o, habit_m, habit_p,
                                         habit_days)
            if not msg:
                return ok
            shown = "" if msg == HABIT_NO_DAYS else msg
            return "", hidden, shown, visible if shown else hidden, True, msg

        msg = time_estimate_problem(time_o, time_m, time_p)
        if msg:
            return msg, visible, "", hidden, True, msg
        return ok

    # --- Duplicate Node Detection (fires on blur, no auto-fill) ---
    @app.callback(
        Output('node-name-duplicate-warning', 'children'),
        Output('node-name-duplicate-warning', 'style'),
        Input('node-name', 'n_blur'),
        State('node-name', 'value'),
        State('node-original-name', 'data'),
        prevent_initial_call=True,
    )
    def check_duplicate_name(_blur, typed_name, original_name):
        """Check if typed name matches an existing node (exact or fuzzy). Shows a temporary warning."""
        hidden = {"display": "none"}
        if not typed_name or not typed_name.strip():
            return "", hidden
        typed_stripped = typed_name.strip()
        # Skip if editing the same node
        if original_name and typed_stripped == original_name:
            return "", hidden

        all_nodes = manager.get_all_nodes(include_dormant=True)
        typed_normalized = normalize_name_for_comparison(typed_stripped)

        matches = []
        for node in all_nodes:
            if node.name == original_name:
                continue
            if node.name.lower() == typed_stripped.lower():
                matches.append(node.name)
            elif typed_normalized and normalize_name_for_comparison(node.name) == typed_normalized:
                matches.append(node.name)
        owner = node_with_alias(manager, typed_stripped, original_name)
        if owner and owner not in matches:
            matches.append(owner)

        if matches:
            names_str = ", ".join(matches)
            warning = html.Div(f"Possible duplicate: {names_str}",
                               style=tokens.ERROR_TEXT_VISIBLE)
            return warning, {"display": "block"}

        return "", hidden

    # Auto-hide duplicate warning after 3 seconds. Clearing it through Dash lets
    # the next blur show it again: hiding only the element left Dash thinking
    # it was still showing, so the same warning never came back.
    app.clientside_callback(
        """function(children) {
            clearTimeout(window.SkillTree.duplicateWarningTimer);
            if (children && children !== '') {
                window.SkillTree.duplicateWarningTimer = setTimeout(function() {
                    window.dash_clientside.set_props('node-name-duplicate-warning',
                                                     {children: '', style: {display: 'none'}});
                }, 3000);
            }
            return window.dash_clientside.no_update;
        }""",
        Output('node-name-duplicate-warning', 'title'),  # dummy output
        Input('node-name-duplicate-warning', 'children'),
        prevent_initial_call=True,
    )

    # --- Editor Now switch: refuse what Save couldn't do ---
    # The switch waits for Save like the rest of the form, so this writes
    # nothing. It says at once what would otherwise wait for the Save: a full
    # list bounces the switch and the toast explains. Save checks again.
    @app.callback(
        Output("node-now", "value", allow_duplicate=True),
        Output("now-cap-refused-trigger", "value", allow_duplicate=True),
        Input("node-now", "value"),
        State("node-original-name", "data"),
        State("node-status-done", "value"),
        prevent_initial_call=True,
    )
    def refuse_now_switch(toggle_val, node_name, done_switch):
        if "now" not in (toggle_val or []):
            return no_update, no_update
        node = manager.get_node(node_name) if node_name else None
        if node is not None:
            if node.now:
                return no_update, no_update
            # Un-marking Done first is fine: the Save that reopens the node
            # adds it to Now.
            if node.dormant or (node.status == STATUS_DONE
                                and STATUS_DONE in (done_switch or [])):
                return [], no_update
        if len(manager.get_now_nodes()) >= settings.NOW_NODE_CAP.get():
            return [], f"refused|{int(time.time() * 1000)}"
        return no_update, no_update
