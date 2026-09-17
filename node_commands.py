"""Editor node operations sharing the existing atomic manager transactions."""
import json
import database
from config import ConfigManager
from models import STATUS_DONE, STATUS_OPEN

@database.atomic
def handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                status_done, context, subctx, obs_path, drive_path, website_path,
                e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                time_mode='manual', value_mode='manual',
                habit_duration=0.0, habit_duration_unit='weeks',
                habit_intensity_o=0.0, habit_intensity_m=0.0, habit_intensity_p=0.0,
                habit_intensity_unit='min_per_day', habit_days=None):
    """Create or update a node and sync its edges. Returns a status message.

    Caller is responsible for converting habit-mode inputs to time_o/m/p
    before calling — this function just persists what it's given. The
    habit_* fields are stored alongside time_o/m/p so the editor can
    repopulate the habit form on re-open.
    """
    from models import Node

    target_status = STATUS_DONE if (status_done and STATUS_DONE in status_done) else STATUS_OPEN

    ctx = context or None
    sub = (subctx or '').strip() or None
    if ctx is None:
        sub = None
    elif sub is not None and sub not in ConfigManager.get_subcontexts().get(ctx, []):
        sub = None

    node = Node(
        name=name, type=n_type, description=desc or "",
        value=val, time_o=time_o or 0, time_m=time_m or 0, time_p=time_p or 0,
        interest=interest, difficulty=diff,
        status=target_status, context=ctx, subcontext=sub,
        obsidian_path=(obs_path or '').strip() or None,
        google_drive_path=(drive_path or '').strip() or None,
        website=(website_path or '').strip() or None,
        time_mode=time_mode,
        value_mode=value_mode,
        habit_duration=habit_duration or 0,
        habit_duration_unit=habit_duration_unit or 'weeks',
        habit_intensity_o=habit_intensity_o or 0,
        habit_intensity_m=habit_intensity_m or 0,
        habit_intensity_p=habit_intensity_p or 0,
        habit_intensity_unit=habit_intensity_unit or 'min_per_day',
        **({'habit_days': habit_days} if habit_days is not None else {}),
    )
    existing = manager.get_node(name)
    if existing:
        # Preserve fields that aren't represented in the editor form, otherwise
        # update_node would overwrite them with the Node dataclass defaults.
        node.dormant = existing.dormant
        node.actual_time_lower = existing.actual_time_lower
        node.actual_time_upper = existing.actual_time_upper
        node.actual_time_point = existing.actual_time_point
        node.actual_time_unit = existing.actual_time_unit
        node.calibration_dismissed = existing.calibration_dismissed
        # The Now flag is mutated by dispatch_now_toggle (a direct DB
        # write outside this form), so preserve the latest DB value. Same
        # for the lifecycle dates and reflection columns — set elsewhere or
        # not yet wired into the editor.
        node.now = existing.now
        node.start_date = existing.start_date
        node.done_date = existing.done_date
        node.reflect_value = existing.reflect_value
        node.reflect_interest = existing.reflect_interest
        node.reflect_difficulty = existing.reflect_difficulty
        manager.update_node(node)
        msg = f"Updated node '{name}'"
    else:
        manager.add_node(node)
        msg = f"Added node '{name}'"
    manager.sync_edges(name, e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps)
    return msg


def prior_node_for_completion(manager, name, original_name):
    """The DB row a save is about to overwrite, for Done-transition detection.

    During a rename the node still lives in the DB under its pre-save name
    (core_engine renames after this check), so fall back to original_name —
    otherwise a re-saved Done node that was just renamed is misread as a
    brand-new completion and spuriously re-opens the time-calibration modal.
    """
    node = manager.get_node(name)
    if node is None and original_name and original_name.strip():
        node = manager.get_node(original_name.strip())
    return node


def handle_delete(manager, name):
    """Delete a single node by name. Returns a status message."""
    manager.delete_node(name)
    return f"Deleted node '{name}'"


def handle_toggle_done(manager, tapped_node):
    """Toggle a node's status between Done and Open. Returns a status message."""
    node = manager.get_node(tapped_node.get('id'))
    if node:
        node.status = STATUS_OPEN if node.status == STATUS_DONE else STATUS_DONE
        manager.update_node(node)
        return f"Toggled status of '{node.name}' to {node.status}"
    return ""


def handle_group_delete(manager, group_delete_data):
    """Delete multiple nodes from a JSON-encoded list. Returns a status message."""
    # JS sends '["name1","name2"]|timestamp' — strip the timestamp suffix
    raw = group_delete_data.split('|')[0] if isinstance(group_delete_data, str) else ''
    names = json.loads(raw) if raw else []
    for node_name in names:
        manager.delete_node(node_name)
    return f"Deleted {len(names)} node(s)" if names else ""
