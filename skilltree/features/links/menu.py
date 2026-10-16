"""The link menu: right-click a link on any canvas to change it in place.

context_menu.js writes ``link-action-input`` with the action and the link as a
JSON list (``[action, source, target, type]``). Insert Node Here is not an
action here: it opens the bridge dialog (bridge_callbacks).

A Done node stays Done only while all of its Hard prerequisites are, so a
change can reopen Done nodes (making a link Hard, or reversing one). That
change waits for the user to confirm it, as un-marking a Done node does.
"""
import time

from dash import Input, Output, State, no_update

from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.callback_helpers import get_trigger_id, reopen_body
from skilltree.store.graph.manager import GraphManager
from skilltree.store.commands import change_link, link_change_reopens

graph_manager = GraphManager()

def register_link_menu_callbacks(app, services=None):
    graph_manager = services.graph if services is not None else globals()['graph_manager']

    def _apply(parts):
        """``(refresh, message)`` for a change made now."""
        try:
            change_link(graph_manager, *parts[1:], parts[0])
        except ValueError as e:
            return no_update, f"Error: {e}"
        return f"link-{int(time.time() * 1000)}", no_update

    # A change redraws every canvas through the core engine, as linking an
    # existing node on Details does. It says nothing on success: the canvas
    # shows it. A refusal goes to save-output, whose "Error:" opens the error
    # dialog. A change that would reopen Done nodes asks first.
    @app.callback(
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Output("save-output", "children", allow_duplicate=True),
        Output("modal-link-reopen-confirm", "is_open", allow_duplicate=True),
        Output("link-reopen-confirm-body", "children"),
        Output("link-action-pending-store", "data"),
        Input("link-action-input", "value"),
        prevent_initial_call=True,
    )
    def apply_link_action(request):
        parts = bridge_payloads.names(request)
        if len(parts) != 4:
            return (no_update,) * 5
        action, source, target, edge_type = parts
        try:
            reopened = link_change_reopens(graph_manager, source, target, edge_type, action)
        except ValueError as e:
            return no_update, f"Error: {e}", no_update, no_update, no_update
        if reopened:
            return no_update, no_update, True, reopen_body(reopened), parts
        return (*_apply(parts), no_update, no_update, None)

    @app.callback(
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Output("save-output", "children", allow_duplicate=True),
        Output("modal-link-reopen-confirm", "is_open", allow_duplicate=True),
        Output("link-action-pending-store", "data", allow_duplicate=True),
        Input("btn-link-reopen-confirm", "n_clicks"),
        Input("btn-link-reopen-cancel", "n_clicks"),
        State("link-action-pending-store", "data"),
        prevent_initial_call=True,
    )
    def answer_link_reopen(confirm, cancel, pending):
        if get_trigger_id() == "btn-link-reopen-confirm" and confirm and pending:
            return (*_apply(pending), False, None)
        if cancel or confirm:
            return no_update, no_update, False, None
        return (no_update,) * 4
