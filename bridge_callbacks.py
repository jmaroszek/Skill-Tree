"""Callbacks for the Create Bridge dialog.

The node menu (two nodes selected) and the edge menu write a request to
``bridge-open-input``. This module opens the dialog, keeps its two ends and
checks what the bridge would do. Create then opens the ordinary node editor
with the relationships filled in, and populate_editor (callbacks.py) does that
part, because every way of filling the editor lives there.
"""
from dash import Input, Output, State, no_update

import bridge_payloads
import style_tokens as tokens
from graph_manager import GraphManager
from models import EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT
from node_commands import plan_bridge

graph_manager = GraphManager()

_KIND_OF_EDGE = {EDGE_NEEDS_HARD: 'hard', EDGE_NEEDS_SOFT: 'soft'}
_KIND_OF_CLICKED_EDGE = {**_KIND_OF_EDGE, EDGE_HELPS: 'synergy'}
_NOTICE_BASE = {"fontSize": tokens.FS_BASE, "minHeight": "1.2em"}


def opening_ends(manager, first, second, edge_type=None):
    """``(start, end, kind)`` the dialog opens with for two nodes.

    An edge names its own order and type. Two selected nodes that already have
    a prerequisite link between them open in that link's order and type, so the
    common case, a step to put in the middle of a link, needs no changes.
    Otherwise the first node is the Start, as a Hard link.
    """
    if edge_type in _KIND_OF_CLICKED_EDGE:
        return first, second, _KIND_OF_CLICKED_EDGE[edge_type]
    for edge in manager.get_edges():
        if (edge['type'] in _KIND_OF_EDGE
                and {edge['source'], edge['target']} == {first, second}):
            return edge['source'], edge['target'], _KIND_OF_EDGE[edge['type']]
    return first, second, 'hard'


def _notice(plan):
    """``(text, is_problem)`` for what the dialog says about the bridge."""
    if plan['problem']:
        return plan['problem'], True
    if plan['replaces']:
        source, target, edge_type = plan['replaces']
        word = 'Hard' if edge_type == EDGE_NEEDS_HARD else 'Soft'
        return (f"The {word} link from '{source}' to '{target}' is replaced by the "
                "bridge when you save the new node."), False
    return "You will make the new node in the editor next.", False


def register_bridge_callbacks(app, services=None):
    graph_manager = services.graph if services is not None else globals()['graph_manager']

    @app.callback(
        Output("modal-bridge", "is_open", allow_duplicate=True),
        Output("bridge-type", "value"),
        Output("bridge-modal-store", "data"),
        Input("bridge-open-input", "value"),
        prevent_initial_call=True,
    )
    def open_bridge_modal(request):
        parsed = bridge_payloads.bridge_request(request)
        if parsed is None:
            return no_update, no_update, no_update
        first, second, edge_type = parsed
        if first == second or any(graph_manager.get_node(n) is None
                                  for n in (first, second)):
            return no_update, no_update, no_update
        start, end, kind = opening_ends(graph_manager, first, second, edge_type)
        return True, kind, {"start": start, "end": end}

    @app.callback(
        Output("bridge-modal-store", "data", allow_duplicate=True),
        Input("btn-bridge-swap", "n_clicks"),
        State("bridge-modal-store", "data"),
        prevent_initial_call=True,
    )
    def swap_bridge_ends(n_clicks, ends):
        if not n_clicks or not ends:
            return no_update
        return {"start": ends["end"], "end": ends["start"]}

    @app.callback(
        Output("modal-bridge", "is_open", allow_duplicate=True),
        Input("btn-bridge-cancel", "n_clicks"),
        Input("btn-bridge-create", "n_clicks"),
        prevent_initial_call=True,
    )
    def close_bridge_modal(cancel, create):
        return False if (cancel or create) else no_update

    @app.callback(
        Output("bridge-start", "children"),
        Output("bridge-end", "children"),
        Output("bridge-start-label", "children"),
        Output("bridge-end-label", "children"),
        Output("bridge-notice", "children"),
        Output("bridge-notice", "style"),
        Output("btn-bridge-create", "disabled"),
        Output("bridge-swap-wrap", "style"),
        Input("bridge-modal-store", "data"),
        Input("bridge-type", "value"),
        prevent_initial_call=True,
    )
    def render_bridge_modal(ends, kind):
        if not ends:
            return (no_update,) * 8
        start, end = ends["start"], ends["end"]
        plan = plan_bridge(graph_manager, start, end, kind)
        text, is_problem = _notice(plan)
        # A synergy has no direction, so there is nothing to swap.
        synergy = kind == 'synergy'
        style = {**_NOTICE_BASE,
                 "color": tokens.DANGER_TEXT if is_problem else tokens.TEXT_SOFT}
        return (start, end,
                "Node" if synergy else "Start", "Node" if synergy else "End",
                text, style, bool(plan['problem']),
                {"display": "none"} if synergy else {})

    # Create opens the editor. The server fills it in (populate_editor); this
    # only slides the sidebar open, as the Details tab's "New node" does.
    app.clientside_callback(
        """
        function(clicks, editorStyle, goalStyle, eventsStyle) {
            var NO = window.dash_clientside.no_update;
            if (!clicks) return [NO, NO, NO];
            return window.dash_clientside.editor.open_on_add(
                clicks, editorStyle, goalStyle, eventsStyle);
        }
        """,
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Output("details-goal-sidebar", "style", allow_duplicate=True),
        Output("events-sidebar-container", "style", allow_duplicate=True),
        Input("btn-bridge-create", "n_clicks"),
        State("sidebar-editor-container", "style"),
        State("details-goal-sidebar", "style"),
        State("events-sidebar-container", "style"),
        prevent_initial_call=True,
    )
