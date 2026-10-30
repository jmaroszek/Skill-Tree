"""The Details tab's Subtasks table: rendering it once the layout settles, its
filters, navigating from a row, and the + menu that adds or links a subtask."""
import json
import time

from dash import ALL, Input, Output, State, ctx, no_update

from skilltree.domain.models import (
    EDGE_NEEDS_HARD,
    EDGE_NEEDS_SOFT,
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_OPEN,
)
from skilltree.features.details.layout import (
    build_details_subtasks_table,
    build_milestone_tile,
    build_no_selection_subtasks,
    normalize_direction,
    normalize_max_depth,
)
from skilltree.store import database
from skilltree.store.graph.queries import DIRECTION_NEEDS
from skilltree.store.commands import change_link, link_change_reopens
from skilltree.ui.components.confirm import reopen_body
from skilltree.ui.dash_tools import get_trigger_id
from skilltree.ui.filters import FILTER_INPUTS, filters_from


def register_subtask_callbacks(app, services):
    graph_manager = services.graph

    # --- Subtasks table: selection placeholder, then render after layout ---
    # The full table is the largest remaining Details response. Keep it out of
    # the initial animation window: the browser swaps in a placeholder when the
    # selection changes (see the panel callback above), and
    # details_deferred_subtasks.js requests the real rows only after the
    # newest Cytoscape layout has stopped. Filter/refresh changes on an already
    # rendered node remain immediate.
    #
    # The selection is a State. As an Input it made a request on every
    # selection whose answer landed in the opening animation, and the only
    # selection it had to act on is a frozen canvas's, which runs no layout.
    # The callback below sends that canvas's settle signal itself.
    @app.callback(
        Output("details-subtasks-table-container", "children"),
        Input("details-layout-settled-trigger-input", "value"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("details-direction", "value"),
        FILTER_INPUTS,
        Input("details-hide-blocked", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def render_details_subtasks(settled_token, _refresh, _version,
                                include_soft_val, include_synergies_val,
                                max_depth_val, direction_val, sidebar_filters,
                                hide_blocked_val, selected_node):
        # A deleted node has no table. Its refresh can land after the
        # selection clears.
        if not selected_node or not graph_manager.get_node(selected_node):
            return build_no_selection_subtasks()

        trigger = get_trigger_id()
        if trigger == "details-layout-settled-trigger-input":
            try:
                settled_root = json.loads(settled_token or "{}").get("root")
            except (TypeError, ValueError, AttributeError):
                return no_update
            # A superseded layout may finish after the user selected another
            # node. Never let its late signal overwrite the current table.
            if settled_root != selected_node:
                return no_update

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_synergies = bool(
            include_synergies_val and "include" in include_synergies_val)
        max_depth = normalize_max_depth(max_depth_val)
        global_filters = filters_from(sidebar_filters)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters["hide_blocked"] = True

        direction = normalize_direction(direction_val)
        subtask_nodes, edges = collect_details_subtasks(
            graph_manager, selected_node, include_soft, include_synergies, max_depth,
            global_filters, direction)
        non_milestone_subtasks = [
            node for node in subtask_nodes if node.type != "Milestone"]
        return build_details_subtasks_table(
            non_milestone_subtasks, graph_manager=graph_manager, edges=edges,
            parent_name=selected_node, include_soft=include_soft,
            include_synergies=include_synergies,
            milestones_only=bool(subtask_nodes) and not non_milestone_subtasks,
            direction=direction)

    # --- Toggle milestone filters ---
    @app.callback(
        Output("details-milestones-section", "style", allow_duplicate=True),
        Output("details-subtask-toggles-bottom", "style", allow_duplicate=True),
        Output("details-milestones-tiles", "children", allow_duplicate=True),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("details-direction", "value"),
        FILTER_INPUTS,
        Input("details-hide-blocked", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def toggle_details_subtask_filters(include_soft_val, include_synergies_val,
                                       max_depth_val, direction_val, sidebar_filters,
                                       hide_blocked_val, selected_node):
        if not selected_node:
            return no_update, no_update, no_update

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)
        max_depth = normalize_max_depth(max_depth_val)

        global_filters = filters_from(sidebar_filters)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        subtask_nodes, edges = collect_details_subtasks(
            graph_manager, selected_node, include_soft, include_synergies, max_depth,
            global_filters, normalize_direction(direction_val))

        # Milestones roster shares the same filtered, depth-limited view as
        # the table, so both surfaces stay in lockstep.
        ms_section_style, bottom_toggles_style, ms_tiles = build_milestones_section(
            graph_manager, subtask_nodes, selected_node, edges)

        return ms_section_style, bottom_toggles_style, ms_tiles

    # --- Sync "Hide Done" toggle with sidebar filter ---
    @app.callback(
        Output("details-hide-done", "value"),
        Output("filter-done", "value", allow_duplicate=True),
        Input("details-hide-done", "value"),
        Input("filter-done", "value"),
        prevent_initial_call=True,
    )
    def sync_hide_done(details_val, filter_val):
        if (details_val or []) == (filter_val or []):
            return no_update, no_update
        if ctx.triggered_id == "details-hide-done":
            return no_update, details_val
        return filter_val, no_update

    # --- Subtask Name Click → Select that node in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-subtask-name", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def navigate_to_subtask(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Milestone Tile Click → Select that Milestone in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-milestone-tile", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def navigate_to_milestone_tile(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Details > Subtasks: link an existing node ---
    app.clientside_callback(
        """
        function(choice, selectedNode, editorStyle, goalStyle, eventsStyle) {
            var NO = window.dash_clientside.no_update;
            if (!(choice || '').startsWith('new|') || !selectedNode) {
                return [NO, NO, NO];
            }
            return window.dash_clientside.editor.open_on_add(
                choice, editorStyle, goalStyle, eventsStyle);
        }
        """,
        Output("sidebar-editor-container", "style", allow_duplicate=True),
        Output("details-goal-sidebar", "style", allow_duplicate=True),
        Output("events-sidebar-container", "style", allow_duplicate=True),
        Input("details-add-choice-input", "value"),
        State("details-selected-node-store", "data"),
        State("sidebar-editor-container", "style"),
        State("details-goal-sidebar", "style"),
        State("events-sidebar-container", "style"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("modal-details-link-node", "is_open", allow_duplicate=True),
        Output("details-add-existing-dropdown", "options"),
        Output("details-add-existing-dropdown", "value"),
        Output("details-add-link-edge-type", "value"),
        Output("details-add-save-status", "children", allow_duplicate=True),
        Input("details-add-choice-input", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def open_link_node_modal(choice, selected_node):
        if not (choice or "").startswith("existing|") or not selected_node:
            return (no_update,) * 5
        all_nodes = graph_manager.get_all_nodes(include_dormant=True)
        subtree = graph_manager.get_goal_subtree(selected_node)
        excluded = subtree | {selected_node}
        options = [{"label": n.name, "value": n.name}
                   for n in sorted(all_nodes, key=lambda n: n.name)
                   if n.name not in excluded]
        return True, options, None, "hard", ""

    @app.callback(
        Output("modal-details-link-node", "is_open", allow_duplicate=True),
        Input("btn-details-add-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_link_node(n_clicks):
        return False if n_clicks else no_update

    # A link that would reopen Done nodes asks first, in the link menu's
    # confirmation, which makes the link on a yes (link_menu_callbacks).
    @app.callback(
        Output("modal-details-link-node", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Output("details-add-save-status", "children"),
        Output("modal-link-reopen-confirm", "is_open", allow_duplicate=True),
        Output("link-reopen-confirm-body", "children", allow_duplicate=True),
        Output("link-action-pending-store", "data", allow_duplicate=True),
        Input("btn-details-add-save", "n_clicks"),
        State("details-selected-node-store", "data"),
        State("details-add-existing-dropdown", "value"),
        State("details-add-link-edge-type", "value"),
        prevent_initial_call=True,
    )
    def link_existing_node(n_clicks, selected_node, link_node, link_edge_type):
        if not n_clicks or not selected_node:
            return (no_update,) * 6
        if not link_node:
            return no_update, no_update, "Please select a node to link.", no_update, no_update, no_update
        edge_type = EDGE_NEEDS_HARD if link_edge_type == "hard" else EDGE_NEEDS_SOFT
        change = ["add", link_node, selected_node, edge_type]
        try:
            reopened = link_change_reopens(graph_manager, link_node, selected_node,
                                           edge_type, "add")
            if reopened:
                return False, no_update, "", True, reopen_body(reopened), change
            change_link(graph_manager, link_node, selected_node, edge_type, "add")
        except ValueError as e:
            return no_update, no_update, str(e), no_update, no_update, no_update
        return False, f"link-{int(time.time() * 1000)}", "", no_update, no_update, no_update


def build_milestones_section(graph, subtask_nodes, parent_name, edges):
    """Compute the (section_style, bottom_toggles_style, tiles) tuple for
    the milestones strip and the canonical bottom toggle wrapper.

    Mirrors the Subtasks table exactly: it receives the same resolved,
    depth-limited dependency view, then picks out Milestones and renders them
    as tiles.

    The bottom toggle wrapper visibility is the *inverse* of the milestones
    section visibility: when milestones are shown, the toggles live up next
    to the Milestones header (their -top counterparts), so the canonical
    bottom set is hidden to avoid duplication. Otherwise the canonical set
    sits with the Subtasks header as before.

    Returns (section: display:none, bottom_toggles: visible, tiles: []) when
    no Milestone survives filtering.
    """
    milestones = [n for n in subtask_nodes if n.type == "Milestone"]
    # Sort Open first, Blocked next, Done last — within each group alphabetical.
    # Mirrors the existing subtasks-table convention (Done at the bottom) but
    # additionally promotes Open above Blocked since Open milestones are the
    # ones the user can act on right now.
    _STATUS_ORDER = {STATUS_OPEN: 0, STATUS_BLOCKED: 1, STATUS_DONE: 2}
    milestones.sort(key=lambda n: (_STATUS_ORDER.get(n.status, 99), n.name))
    if not milestones:
        # Milestones hidden → canonical bottom toggles visible (default).
        return {"display": "none"}, {}, []
    tiles = [
        build_milestone_tile(
            ms,
            graph.get_goal_completion(ms.name, include_soft=False),
        )
        for ms in milestones
    ]
    # Milestones shown → bottom toggles hidden (top toggles take over).
    return {"display": "block"}, {"display": "none"}, tiles


def collect_details_subtasks(graph, node_name, include_soft, include_synergies,
                             max_depth, global_filters, direction=DIRECTION_NEEDS):
    """Return the filtered, sorted dependency rows shared by Details views.

    ``direction`` is the Direction setting: the nodes leading into
    ``node_name`` (Needs) or the ones it leads to (Supports).
    """
    view = graph.get_dependency_view(
        node_name, include_soft=include_soft,
        include_synergies=include_synergies, max_depth=max_depth,
        filters=global_filters, direction=direction)
    subtree = set(view["node_names"]) - {node_name}
    subtask_nodes = [graph.get_node(name) for name in subtree]
    subtask_nodes = [node for node in subtask_nodes if node is not None]
    subtask_nodes.sort(key=lambda n: (n.status == STATUS_DONE, n.name))
    return subtask_nodes, graph.get_edges()
