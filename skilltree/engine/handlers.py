"""What the core engine does for each action it performs.

The core callback picks one handler by what fired it. A handler changes the
graph and reports what it did in an Outcome. The callback then renders the
canvas and merges the two. A handler that has to answer without a render,
for a refused save or a confirmation to ask for, puts the whole response in
its Outcome instead.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from dash import html, no_update

from skilltree.domain.models import STATUS_DONE, STATUS_OPEN
from skilltree.domain.names import format_name
from skilltree.engine.response import CoreResponse
from skilltree.features.editor.save import save_editor_form
from skilltree.store import database
from skilltree.store.commands import (
    ReopensDoneNodes, add_to_now, conflicting_node_name, handle_delete, handle_group_delete,
    handle_toggle_done,
)
from skilltree.store import settings
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.components.confirm import reopen_body
from skilltree.ui.styles import SIDEBAR_TRANSLATE_CLOSED

logger = logging.getLogger(__name__)

# The editor's own saves: each commits the whole form, so the form is what
# the database holds afterwards.
SAVE_TRIGGERS = ('btn-save', 'btn-unsaved-save')


@dataclass(frozen=True)
class Request:
    """What a handler reads: the managers, what fired, and its inputs."""
    graph: object
    events: object
    trigger: str
    form: dict
    original_name: Optional[str]
    pristine_snapshot: object
    bridge_pending: object
    # The user agreed to a save that reopens Done nodes.
    reopen_confirmed: bool
    # The editor's Now switch is on.
    now_switch: bool
    tapped_node: object
    toggle_done_trigger_data: object
    pending_undo_done: object
    group_delete_data: object
    # The editor, Goals and Events sidebar styles a response carries.
    sidebars: tuple


@dataclass
class Outcome:
    """What a handler did, for the render that follows."""
    message: str = ""
    # The node an explicit single completion just marked Done: the
    # time-calibration modal asks how long it took.
    completed: Optional[str] = None
    # Names whose un-marking waits on the undo-Done modal, and the Done nodes
    # after them it would re-block.
    undo_pending: Optional[list] = None
    undo_downstream: list = field(default_factory=list)
    save_result: object = no_update
    # The node a save wrote. The canvas selects it.
    saved_name: Optional[str] = None
    # A whole response, sent without rendering the canvas.
    response: Optional[CoreResponse] = None


def unexpected_error_message(action):
    """Log the exception being handled, and describe it for the user.

    Call this from an ``except`` block. The traceback goes to the log file,
    where a bug report can pick it up, and the user sees what failed rather
    than the exception's text.
    """
    logger.exception("%s failed", action)
    return (f"Error: {action} failed unexpectedly. The details are in the log, "
            "which a bug report should include.")


def undo_done_body(target_names, downstream_done):
    """The undo-Done modal's warning: which Done dependents flip Blocked
    when the listed targets are un-marked."""
    target_label = (
        f"'{target_names[0]}'" if len(target_names) == 1
        else f"{len(target_names)} selected nodes"
    )
    items = [html.Li(name) for name in downstream_done[:25]]
    overflow = (
        html.Div(f"...and {len(downstream_done) - 25} more.",
                 className="text-muted small mt-1")
        if len(downstream_done) > 25 else None
    )
    children = [
        html.P([
            "Un-marking ", html.Strong(target_label), " will flip "
            f"{len(downstream_done)} downstream Done node(s) to Blocked, "
            "because their hard prerequisite is no longer complete:"
        ]),
        html.Ul(items, className="mb-0"),
    ]
    if overflow is not None:
        children.append(overflow)
    return children


def _editor_kept_open(ed_style):
    """The editor style for a refused save: open, so the form stays on screen.

    The unsaved-changes dialog's Save computes a closed style before the save
    runs. A save that is then refused must not slide the form away with the
    user's input in it.
    """
    if not isinstance(ed_style, dict):
        return ed_style
    return {**ed_style, 'transform': "translateX(0px)"}


def _refused(message, request, *, editor_style=None):
    """A save that didn't go through: its message and the sidebar styles,
    and nothing that would touch the graph, the filters or a modal."""
    ed_style, goal_style, events_style = request.sidebars
    return Outcome(response=CoreResponse(
        message=message,
        editor_style=ed_style if editor_style is None else editor_style,
        goal_style=goal_style, events_style=events_style))


def save(request):
    """The editor's Save, and the unsaved-changes dialog's."""
    form = request.form
    ed_style = request.sidebars[0]
    name = form.get('name')
    if name and name.strip():
        name = format_name(name.strip(), settings.NAME_FORMATTING.get())
    if not name or not name.strip():
        # Only show the error if the user has filled in something meaningful.
        # A blank form means they changed their mind after New Node: close.
        desc = form.get('desc')
        if any([desc and desc.strip(), form.get('val') not in (None, 5),
                form.get('interest') not in (None, 5), form.get('diff') not in (None, 5)]):
            return _refused("Error: Node name is required.", request)
        return _refused("", request,
                        editor_style={**ed_style, 'transform': SIDEBAR_TRANSLATE_CLOSED})
    if not form.get('n_type'):
        return _refused("Error: Node type is required.", request)
    # A new node, or a rename, may not take another node's name: the save
    # would update that node in place and wipe its relationships.
    clash = conflicting_node_name(request.graph, name, request.original_name)
    if clash:
        return _refused(f"Error: A node named '{clash}' already exists. Choose a "
                        f"different name, or search for '{clash}' to edit it.",
                        request, editor_style=_editor_kept_open(ed_style))
    try:
        saved = save_editor_form(
            request.graph, request.events, form, name,
            original_name=request.original_name,
            pristine_snapshot=request.pristine_snapshot,
            bridge_pending=request.bridge_pending,
            reopen_confirmed=request.reopen_confirmed, via=request.trigger,
            now=request.now_switch)
    except ReopensDoneNodes as e:
        _, goal_style, events_style = request.sidebars
        return Outcome(response=CoreResponse(
            editor_style=_editor_kept_open(ed_style),
            goal_style=goal_style, events_style=events_style,
            reopen_open=True, reopen_body=reopen_body(e.names),
            reopen_pending={'via': request.trigger}))
    except (ValueError, TypeError) as e:
        return _refused(f"Error: {e}", request, editor_style=_editor_kept_open(ed_style))
    except Exception:
        return _refused(unexpected_error_message("Saving the node"), request,
                        editor_style=_editor_kept_open(ed_style))
    return Outcome(message=saved.message, completed=saved.completed,
                   undo_pending=saved.undo_pending,
                   undo_downstream=saved.undo_downstream,
                   save_result=saved.result, saved_name=name)


def delete_loaded(request):
    """Delete the node the editor loaded, never whatever the Name field says
    now: a half-typed rename, or another node's name typed over it, must not
    choose what gets deleted. A form that never loaded a node has nothing
    stored to delete, and the editor just closes."""
    name = (request.original_name or '').strip()
    if not name:
        return Outcome()
    try:
        return Outcome(message=handle_delete(request.graph, name))
    except ValueError as e:
        return Outcome(message=f"Error: {e}")
    except Exception:
        return Outcome(message=unexpected_error_message("Deleting the node"))


def toggle_tapped(request):
    """The node menu's Mark Done or Reopen on the tapped node."""
    tapped = request.tapped_node
    if not tapped:
        return Outcome()
    graph = request.graph
    completed = None
    try:
        node_id = tapped.get('id')
        node = graph.get_node(node_id)
        # Done → Open with downstream Done dependents needs the user's say:
        # re-blocking work that was Done is destructive enough to ask.
        if node and node.status == STATUS_DONE:
            downstream = graph.get_downstream_done_dependents(node_id)
            if downstream:
                return Outcome(response=CoreResponse(
                    undo_open=True, undo_body=undo_done_body([node_id], downstream),
                    undo_pending=[node_id]))
        if node and node.status != STATUS_DONE:
            completed = node_id
        return Outcome(message=handle_toggle_done(graph, tapped), completed=completed)
    except ValueError as e:
        return Outcome(message=f"Error: {e}", completed=completed)
    except Exception:
        return Outcome(message=unexpected_error_message("Changing the node's status"),
                       completed=completed)


def toggle_selection(request):
    """Mark Done or Reopen on every selected node, as one change."""
    data = request.toggle_done_trigger_data
    if not data:
        return Outcome()
    graph = request.graph
    message, completed = "", None
    try:
        nodes = [n for n in (graph.get_node(name) for name in bridge_payloads.names(data)) if n]
        # A sleeping node can't be Done, and one in the selection used to
        # refuse the whole action. It sits out instead.
        asleep = [n for n in nodes if n.dormant]
        nodes = [n for n in nodes if not n.dormant]
        if asleep and not nodes:
            message = "Error: a sleeping node can't be marked Done. Wake it first."
        if nodes:
            new_status = (STATUS_DONE if any(n.status != STATUS_DONE for n in nodes)
                          else STATUS_OPEN)
            # Reopening asks first when it would re-block Done nodes after the
            # selection: every one of them is listed.
            if new_status == STATUS_OPEN:
                affected, seen = [], set()
                for node in nodes:
                    if node.status != STATUS_DONE:
                        continue
                    for dependent in graph.get_downstream_done_dependents(node.name):
                        if dependent not in seen:
                            seen.add(dependent)
                            affected.append(dependent)
                if affected:
                    targets = [n.name for n in nodes]
                    return Outcome(response=CoreResponse(
                        undo_open=True, undo_body=undo_done_body(targets, affected),
                        undo_pending=targets))
            # One transaction, so a failure part-way through leaves every
            # selected node as it was. Prerequisites go first, so a chain
            # selected in any order can be completed.
            if new_status == STATUS_DONE:
                order = graph.completion_order([n.name for n in nodes])
                nodes = sorted(nodes, key=lambda n: order.index(n.name))
            flipped = 0
            with database.transaction():
                for node in nodes:
                    if node.status != new_status:
                        node.status = new_status
                        graph.update_node(node)
                        flipped += 1
            if len(nodes) == 1 and new_status == STATUS_DONE and flipped == 1:
                completed = nodes[0].name
            if len(nodes) == 1:
                message = f"Toggled status of '{nodes[0].name}' to {new_status}"
            else:
                message = f"Set {flipped} node(s) to {new_status}"
            if asleep:
                message += f", leaving out {len(asleep)} sleeping"
        return Outcome(message=message, completed=completed)
    except ValueError as e:
        return Outcome(message=f"Error: {e}", completed=completed)
    except Exception:
        return Outcome(message=unexpected_error_message("Changing the nodes' status"),
                       completed=completed)


def confirm_undo_done(request):
    """The undo-Done modal's Confirm: reopen every node it asked about. The
    cascade re-blocks the Done nodes after them."""
    pending = request.pending_undo_done
    if not pending:
        return Outcome()
    try:
        targets = list(pending) if isinstance(pending, list) else [pending]
        flipped = 0
        with database.transaction():
            for name in targets:
                node = request.graph.get_node(name)
                if node and node.status == STATUS_DONE:
                    node.status = STATUS_OPEN
                    request.graph.update_node(node)
                    flipped += 1
            # An editor save that un-marked its node asked here first. The
            # Now switch it held waits for the node to reopen.
            editing = (request.original_name or '').strip()
            if request.now_switch and targets == [editing]:
                add_to_now(request.graph, editing)
        if flipped == 1:
            return Outcome(message=f"Un-marked '{targets[0]}' (Done → Open)")
        return Outcome(message=f"Un-marked {flipped} node(s) (Done → Open)")
    except ValueError as e:
        return Outcome(message=f"Error: {e}")
    except Exception:
        return Outcome(message=unexpected_error_message("Reopening the nodes"))


def group_delete(request):
    """Delete every selected node, as one change."""
    data = request.group_delete_data
    if not data:
        return Outcome()
    try:
        # JS sends '["name1","name2"]|timestamp'. Names may contain "|".
        return Outcome(message=handle_group_delete(request.graph, bridge_payloads.names(data)))
    except ValueError as e:
        return Outcome(message=f"Error: {e}")
    except Exception:
        return Outcome(message=unexpected_error_message("Deleting the nodes"))


HANDLERS = {
    'btn-save': save,
    'btn-unsaved-save': save,
    'btn-node-delete-confirm': delete_loaded,
    'btn-toggle-done-node': toggle_tapped,
    'toggle-done-trigger-input': toggle_selection,
    'btn-undo-done-confirm': confirm_undo_done,
    'group-delete-input': group_delete,
}


def handle(request):
    """Run the handler for what fired. Anything else changes nothing."""
    handler = HANDLERS.get(request.trigger)
    return handler(request) if handler else Outcome()
