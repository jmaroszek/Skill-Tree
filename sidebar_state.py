"""Sidebar visibility and draft-preservation decisions shared by core paths."""
import dash
from config import SIDEBAR_WIDTH_PX, SIDEBAR_TRANSLATE_CLOSED
from callback_helpers import (should_open_editor, left_sidebar_is_open,
                              is_form_dirty_vs_snapshot, editor_form_values)
import style_tokens as tokens

_DEFAULT_EDITOR_SIDEBAR_STYLE = {
    "position": "absolute", "top": "0", "left": "0", "width": SIDEBAR_WIDTH_PX,
    "minWidth": SIDEBAR_WIDTH_PX, "height": "100%", "zIndex": 1000,
    "overflowX": "hidden", "overflowY": "auto",
    "borderRight": f"1px solid {tokens.BORDER_PANEL}", "transition": "transform 0.3s ease",
    "transform": SIDEBAR_TRANSLATE_CLOSED, "willChange": "transform",
    "backgroundColor": tokens.BG_PANEL,
}


def _compute_sidebar_styles(trigger_id, all_triggered_ids, search_val,
                             ed_style, goal_sidebar_style, events_sidebar_style,
                             pending_nav_store,
                             form_state):
    """Determine next sidebar styles based on the triggering Input.

    Returns (next_ed_style, next_goal_style, next_events_sidebar_style). The
    editor-sidebar logic and the goal/events sidebar mutex both live here so
    the short-circuit path and the full core_engine path share one
    implementation.

    `form_state` is a dict carrying the editor-form state used only when
    trigger_id == 'btn-close-editor' (the unsaved-changes check). For triggers
    that don't need it, pass an empty dict.
    """
    next_ed_style = ed_style or dict(_DEFAULT_EDITOR_SIDEBAR_STYLE)
    currently_open = bool(ed_style) and ed_style.get('transform', '') == 'translateX(0px)'
    if trigger_id == 'btn-add' and not currently_open:
        # Toolbar toggle, opening from closed: reveal the editor and preserve the
        # loaded node (mirrors the Goals/Events toggles). The close half falls
        # through to the btn-close-editor branch below.
        next_ed_style['transform'] = "translateX(0px)"
    elif trigger_id in ('btn-new-node', 'btn-editor-new'):
        next_ed_style['transform'] = "translateX(0px)"
    elif trigger_id == 'search-node' and not search_val:
        # Search bar was cleared (e.g. by populate_editor resetting after btn-add) — don't
        # touch the editor state. Without this guard, a race condition causes core_engine to
        # read a stale "closed" ed_style and immediately close an editor that btn-add just opened.
        next_ed_style = dash.no_update
    elif should_open_editor(all_triggered_ids, trigger_id, search_val):
        next_ed_style['transform'] = "translateX(0px)"
    elif trigger_id == 'btn-goals-toggle':
        next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
    elif trigger_id == 'btn-save':
        # Save only — keep editor open, don't change transform
        next_ed_style['transform'] = "translateX(0px)"
    elif trigger_id in ('btn-save-close', 'btn-node-delete-confirm', 'btn-close-editor', 'btn-unsaved-discard', 'btn-unsaved-save', 'btn-add'):
        # btn-save-close and unsaved-save close it after saving.
        # btn-unsaved-discard closes without saving.
        # btn-close-editor / btn-add (toggle-close) only silently close if the
        # form is clean; otherwise toggle_unsaved_modal pops the save/discard modal.
        if trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard') and pending_nav_store == '__background__':
            # User dismissed via canvas click — close the editor after save/discard.
            next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
        elif trigger_id in ('btn-unsaved-save', 'btn-unsaved-discard') and pending_nav_store:
            pass  # Keep editor open — pending navigation will load the next node
        elif trigger_id in ('btn-save-close', 'btn-unsaved-save') and (not form_state.get('name') or not form_state.get('n_type')):
            pass  # Keep sidebar open — validation error shown below
        elif trigger_id in ('btn-close-editor', 'btn-add'):
            form_has_content = is_form_dirty_vs_snapshot(
                form_state.get('pristine_snapshot'),
                editor_form_values(
                    name=form_state.get('name'), n_type=form_state.get('n_type'),
                    desc=form_state.get('desc'),
                    context=form_state.get('context'), subctx=form_state.get('subctx'),
                    status_done=form_state.get('status_done'),
                    val=form_state.get('val'), interest=form_state.get('interest'),
                    diff=form_state.get('diff'),
                    time_o=form_state.get('time_o'), time_m=form_state.get('time_m'),
                    time_p=form_state.get('time_p'), time_unit=form_state.get('time_unit'),
                    e_needs_h=form_state.get('e_needs_h'), e_needs_s=form_state.get('e_needs_s'),
                    e_supp_h=form_state.get('e_supp_h'), e_supp_s=form_state.get('e_supp_s'),
                    e_helps=form_state.get('e_helps'),
                    obs_links=form_state.get('obs_link_values'),
                    drive_links=form_state.get('drive_link_values'),
                    website_links=form_state.get('website_link_values'),
                    time_mode=form_state.get('time_mode_val'),
                    time_habit_mode=form_state.get('time_habit_mode_val'),
                    habit_duration=form_state.get('habit_duration'),
                    habit_duration_unit=form_state.get('habit_duration_unit'),
                    habit_intensity_o=form_state.get('habit_int_o'),
                    habit_intensity_m=form_state.get('habit_int_m'),
                    habit_intensity_p=form_state.get('habit_int_p'),
                    habit_intensity_unit=form_state.get('habit_int_unit'),
                    habit_days=form_state.get('habit_days'),
                    value_mode=form_state.get('value_mode_val'),
                    priority_rank=form_state.get('priority_rank_val'),
                    aliases=form_state.get('alias_values'),
                ),
            )
            if not form_has_content:
                next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
        else:
            next_ed_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
    else:
        # Race-prevention guard: if the trigger has nothing to do with the
        # editor (tab switches, refresh triggers, filter changes, etc.),
        # don't echo ed_style back to the DOM. Otherwise, a late response
        # from a slow non-editor trigger can clobber an in-flight
        # edit-trigger response that had opened the sidebar — causing the
        # intermittent "Edit menu clicked but editor doesn't open" symptom
        # (especially right after tab switching to Nodes tab).
        next_ed_style = dash.no_update

    # Goal / Events Sidebar Mutex: close them when editor opens
    next_goal_style = dash.no_update
    next_events_sidebar_style = dash.no_update
    if isinstance(next_ed_style, dict) and next_ed_style.get('transform', '') == 'translateX(0px)' and trigger_id != 'btn-goals-toggle':
        # Editor is opening — ensure goal sidebar is closed
        if left_sidebar_is_open(goal_sidebar_style):
            next_goal_style = dict(goal_sidebar_style)
            next_goal_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
        if left_sidebar_is_open(events_sidebar_style):
            next_events_sidebar_style = dict(events_sidebar_style)
            next_events_sidebar_style['transform'] = SIDEBAR_TRANSLATE_CLOSED
    return next_ed_style, next_goal_style, next_events_sidebar_style
