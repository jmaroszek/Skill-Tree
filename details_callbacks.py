"""
Callback definitions for the Details tab.
"""

import database
import json
import os
import logging
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction
import dash_bootstrap_components as dbc
import numpy as np
import plotly.graph_objects as go
from graph_manager import GraphManager
from event_manager import EventManager
from config import ConfigManager, badge_style, sort_subcontexts, sort_contexts
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from details_layout import (build_details_subtasks_table,
                             _build_suggestion_row, build_details_suggestions,
                             build_milestone_tile)
from simulation import SimulationCancelled
from simulation_service import simulation_service
from callback_helpers import (render_link_rows, render_alias_rows, strip_gdrive_prefix,
                              spawn_local_file_picker, build_filters,
                              is_filters_active,
                              build_explain_summary, build_explain_chart,
                              format_value_rank,
                              habit_to_hours, compute_habit_time_omp,
                              habit_preview_text,
                              resolve_time_mode, resolve_value_mode, get_trigger_id,
                              build_node_element, build_edge_element,
                              canvas_node_styles)
from scoring import explain_score, shortest_paths_focus_data

graph_manager = GraphManager()
event_manager = EventManager()


def _normalize_max_depth(value):
    """Map the Details slider's ``All`` sentinel to an uncapped traversal."""
    return None if value in (None, 0, 6) else int(value)


def _build_milestones_section(subtask_nodes, parent_name, edges):
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
            graph_manager.get_goal_completion(ms.name, include_soft=False),
        )
        for ms in milestones
    ]
    # Milestones shown → bottom toggles hidden (top toggles take over).
    return {"display": "block"}, {"display": "none"}, tiles


def _collect_details_subtasks(node_name, include_soft, include_synergies,
                              max_depth, global_filters):
    """Return the filtered, sorted dependency rows shared by Details views."""
    view = graph_manager.get_dependency_view(
        node_name, include_soft=include_soft,
        include_synergies=include_synergies, max_depth=max_depth,
        filters=global_filters)
    subtree = set(view["node_names"]) - {node_name}
    subtask_nodes = [graph_manager.get_node(name) for name in subtree]
    subtask_nodes = [node for node in subtask_nodes if node is not None]
    subtask_nodes.sort(key=lambda n: (n.status == STATUS_DONE, n.name))
    return subtask_nodes, graph_manager.get_edges()


def _run_simulation(node_name, include_soft_val, include_synergies_val,
                    global_filters=None, max_depth=None, should_cancel=None):
    """Shared helper: run the Monte Carlo simulation and return (figure, style, style)."""
    include_soft = bool(include_soft_val and "include" in include_soft_val)
    include_helps = bool(include_synergies_val and "include" in include_synergies_val)
    with database.read_snapshot():
        view = graph_manager.get_dependency_view(
            node_name,
            include_soft=include_soft,
            include_synergies=include_helps,
            max_depth=max_depth,
            filters=global_filters,
        )
        allowed = set(view["node_names"])
        nodes_dict = {
            name: graph_manager.get_node(name) for name in allowed
        }
        nodes_dict = {name: node for name, node in nodes_dict.items() if node is not None}
        if node_name not in nodes_dict:
            return no_update, no_update, no_update

        permitted_types = {EDGE_NEEDS_HARD}
        if include_soft:
            permitted_types.add(EDGE_NEEDS_SOFT)
        if include_helps:
            permitted_types.add(EDGE_HELPS)
        sim_edges = [
            edge for edge in graph_manager.get_edges()
            if edge['type'] in permitted_types
            and edge['source'] in allowed and edge['target'] in allowed
        ]

        requested_trials = ConfigManager.get_monte_carlo_trials()
        time_settings = ConfigManager.get_time_settings()

    result = simulation_service.summarize(
        node_name, nodes_dict, sim_edges, include_soft, include_helps,
        requested_trials, should_cancel=should_cancel)
    stats = result['stats']
    counts, centers, width = result['counts'], result['centers'], result['width']

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=centers, y=counts, width=width,
        marker_color='#0d6efd', opacity=0.85,
        hoverinfo='skip',
    ))

    for label, val, color in [
        ('P10', stats['p10'], '#198754'),
        ('P50', stats['p50'], '#ffc107'),
        ('P90', stats['p90'], '#dc3545'),
    ]:
        fig.add_vline(
            x=val, line_dash="dash", line_color=color, line_width=2,
            annotation_text=f"{label}: {ConfigManager.format_time_friendly(val, time_settings=time_settings)}",
            annotation_position="top",
            annotation_font_color=color,
        )

    fig.update_layout(
        meta={"trials": result['trials'], "requested_trials": requested_trials,
              "chain_size": result['chain_size']},
        template="plotly_dark",
        paper_bgcolor='#1a1d21',
        plot_bgcolor='#1a1d21',
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title="Hours",
        yaxis_title="Frequency",
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=False),
        showlegend=False,
        hovermode=False,
        bargap=0,
    )

    return (
        fig,
        {"display": "flex", "flexDirection": "column", "flex": "1", "minHeight": "0"},
        {"display": "none"},
    )


def register_details_callbacks(app):

    # --- Populate node dropdown when its underlying data changes ---
    # All tab contents stay mounted, so the initial call hydrates this once;
    # graph/version refreshes keep it current without resending ~42 KB merely
    # because the user opened Details.
    @app.callback(
        Output("details-node-select", "options"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
    )
    def populate_details_dropdown(_refresh, _version):
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name}
                for n in sorted(nodes, key=lambda n: n.name)]

    # --- Navigation History: push new entries, handle back/forward ---
    @app.callback(
        Output("details-nav-history", "data"),
        Output("details-nav-index", "data"),
        Output("btn-details-nav-back", "disabled"),
        Output("btn-details-nav-forward", "disabled"),
        Input("details-selected-node-store", "data"),
        Input("btn-details-nav-back", "n_clicks"),
        Input("btn-details-nav-forward", "n_clicks"),
        State("details-nav-history", "data"),
        State("details-nav-index", "data"),
        prevent_initial_call=True,
    )
    def manage_nav_history(selected_node, back_clicks, fwd_clicks,
                           history, nav_index):
        trigger = ctx.triggered_id
        history = list(history or [])
        nav_index = int(nav_index) if nav_index is not None else -1

        if trigger == "btn-details-nav-back":
            if nav_index > 0:
                nav_index -= 1
        elif trigger == "btn-details-nav-forward":
            if nav_index < len(history) - 1:
                nav_index += 1
        elif trigger == "details-selected-node-store":
            if selected_node:
                # Only push if it's a new node (not a back/forward replay)
                if nav_index < 0 or (nav_index < len(history) and
                                     history[nav_index] != selected_node):
                    # Truncate forward history and push
                    history = history[:nav_index + 1]
                    history.append(selected_node)
                    nav_index = len(history) - 1
                elif not history:
                    history.append(selected_node)
                    nav_index = 0

        back_disabled = nav_index <= 0
        fwd_disabled = nav_index >= len(history) - 1

        return history, nav_index, back_disabled, fwd_disabled

    # --- Back/Forward button clicks → update dropdown selection ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input("btn-details-nav-back", "n_clicks"),
        Input("btn-details-nav-forward", "n_clicks"),
        State("details-nav-history", "data"),
        State("details-nav-index", "data"),
        prevent_initial_call=True,
    )
    def nav_button_select(back_clicks, fwd_clicks, history, nav_index):
        trigger = ctx.triggered_id
        history = list(history or [])
        nav_index = int(nav_index) if nav_index is not None else -1

        if trigger == "btn-details-nav-back":
            target_idx = nav_index - 1
        elif trigger == "btn-details-nav-forward":
            target_idx = nav_index + 1
        else:
            return no_update

        if 0 <= target_idx < len(history):
            return history[target_idx]
        return no_update

    # --- Node Selection: populate detail view ---
    @app.callback(
        # Visibility
        Output("details-empty", "style"),
        Output("details-content", "style"),
        # Store
        Output("details-selected-node-store", "data"),
        # Node attributes
        Output("details-node-name", "children"),
        Output("details-node-badges", "children"),
        Output("details-node-description", "children"),
        Output("details-attr-type", "children"),
        Output("details-attr-status", "children"),
        Output("details-attr-context", "children"),
        Output("details-attr-time", "children"),
        Output("details-attr-value", "children"),
        Output("details-attr-interest", "children"),
        Output("details-attr-effort", "children"),
        # Progress
        Output("details-progress-section", "style"),
        Output("details-progress-bar", "value"),
        Output("details-progress-text", "children"),
        # Priority
        Output("details-priority-section", "style"),
        Output("details-priority-badge", "children"),
        # Milestones roster (above the subtasks table, filter-aware) +
        # canonical bottom toggle visibility (hidden when milestones show).
        Output("details-milestones-section", "style"),
        Output("details-subtask-toggles-bottom", "style"),
        Output("details-milestones-tiles", "children"),
        # Ratings display: own-ratings group vs. "Inherited" row. Hidden/shown
        # depending on whether the node's ratings are inherited.
        Output("details-attr-ratings-own", "style"),
        Output("details-attr-ratings-inherited-wrap", "style"),
        Output("details-attr-ratings-inherited", "children"),
        # Inputs
        Input("details-node-select", "value"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("override-store", "data"),
        Input("details-max-depth", "value"),
        State("details-include-soft-needs", "value"),
        State("details-include-synergies", "value"),
        State("filter-context", "value"),
        State("filter-subcontext", "value"),
        State("filter-done", "value"),
        State("filter-value", "value"),
        State("filter-interest", "value"),
        State("filter-time", "value"),
        State("filter-difficulty", "value"),
        State("filter-node-type", "value"),
        State("filter-dormant", "value"),
        State("details-hide-blocked", "value"),
        # What the store already holds. Most of this callback's Inputs are
        # refresh signals, not selection changes, so the store slot below is
        # left untouched unless the selection actually moved — see the note
        # on `_selection_output`.
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def select_detail_node(node_name, _refresh, _version, _override_data,
                           max_depth_val, include_soft_val, include_synergies_val,
                           f_context, f_subcontext, f_done,
                           f_value, f_interest, f_time, f_difficulty,
                           f_node_types, f_show_dormant, hide_blocked_val,
                           current_selection):
        # Dash re-fires every dependent callback when an Output is written,
        # even with an unchanged value. Writing the same node name back on a
        # refresh would make render_details_subtasks see a fresh selection and
        # swap the table for its "Loading subtasks…" placeholder — which then
        # waits for a layout settle that a same-root refresh never produces.
        def _selection_output(value):
            return no_update if value == current_selection else value

        if not node_name:
            return (
                {"display": "block"},
                {"display": "none"},
                _selection_output(None),
                "", [], "", "", "", "", "", "", "", "",
                {"display": "none"}, 0, "",
                {"display": "none"}, "",
                {"display": "none"}, {}, [],
                # Ratings display (own group shown, inherited row hidden).
                {}, {"display": "none"}, "",
            )

        node = graph_manager.get_node(node_name)
        if not node:
            return (no_update,) * 24

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)
        max_depth = _normalize_max_depth(max_depth_val)

        # Build badges. Order: Override → Status → Priority → Type → RelPriority.
        # Goal type tile is suppressed when a Priority N tile is shown
        # (the Priority tile already implies "this is a Goal").
        badges = []
        priority_goals = ConfigManager.get_priority_goals()
        is_priority_goal = node_name in priority_goals

        # 1. Override (always first if active)
        override = ConfigManager.get_override()
        if override.get("parent"):
            override_set = ConfigManager.get_override_node_set(graph_manager)
            if node_name in override_set:
                is_parent = (node_name == override["parent"])
                override_label = "Override" if is_parent else "Override (Dependent)"
                badges.append(html.Span(override_label, className="badge",
                                        style=badge_style('Override')))

        # 2. Status (always)
        badges.append(html.Span(node.status, className="badge",
                                style=badge_style(node.status)))

        # 2b. Now (if currently being worked on). Uses the same
        # configurable color as the canvas border encoding.
        if node.now:
            badges.append(html.Span("Now", className="badge",
                                    style=badge_style('Now')))

        # 3. Priority (Priority N for priority Goals)
        if is_priority_goal:
            rank = priority_goals.index(node_name) + 1
            badges.append(html.Span(f"Priority {rank}", className="badge",
                                    style=badge_style('Priority')))

        # 4. Type (skip Goal when Priority N already rendered above)
        if node.type and not is_priority_goal:
            badges.append(html.Span(node.type, className="badge",
                                    style=badge_style(node.type)))

        # 5. Relationship Priority (Hard/Soft N for non-priority nodes in a priority Goal's subtree)
        if not is_priority_goal:
            for rank_idx, goal_name in enumerate(priority_goals[:3]):
                subtree = graph_manager.get_goal_subtree(goal_name)
                if node_name in subtree:
                    hard_subtree = graph_manager.get_goal_subtree(goal_name, edge_types=(EDGE_NEEDS_HARD,))
                    rel_type = "Hard" if node_name in hard_subtree else "Soft"
                    palette_name = "HardRelPri" if rel_type == "Hard" else "SoftRelPri"
                    badges.append(html.Span(f"{rel_type} {rank_idx+1}",
                                            className="badge",
                                            style=badge_style(palette_name)))
                    break

        ctx_str = node.context or "—"
        if node.subcontext:
            ctx_str += f" > {node.subcontext}"

        effective_time = graph_manager.get_effective_time(node_name)
        time_str = ConfigManager.format_time_friendly(effective_time) if effective_time else "—"

        # Ratings display: when a node's ratings are inherited (containers and
        # Milestones), its stored value/interest/effort are scoring-inert, so
        # showing the raw numbers misleads. Hide the own-ratings rows and show
        # a single "Inherited" row instead — matches the canvas hover tooltip.
        ratings_inherited = node.value_mode == 'inherited'
        if ratings_inherited:
            ratings_own_style = {"display": "none"}
            ratings_inherited_style = {}
            ratings_inherited_text = "Inherited"
        else:
            ratings_own_style = {}
            ratings_inherited_style = {"display": "none"}
            ratings_inherited_text = ""

        show_progress = {"display": "none"}
        progress_val = 0
        progress_text = ""
        if node.type == "Goal":
            completion = graph_manager.get_goal_completion(
                node_name, include_soft=False,
                include_transitive=True, max_depth=max_depth)
            if completion["total"] > 0:
                show_progress = {"display": "block", "marginBottom": "8px"}
                progress_val = completion["pct"]
                remaining = ConfigManager.format_time_friendly(
                    completion["remaining_time"])
                # Milestone count: walk the same hard-subtree the completion
                # walked, count Milestones in it. Filter-independent (matches
                # the existing "X/Y hard subtasks" stat which is also total).
                hard_view = graph_manager.get_dependency_view(
                    node_name, include_soft=False, include_synergies=False,
                    max_depth=max_depth)
                hard_subtree = set(hard_view["node_names"]) - {node_name}
                ms_total = 0
                ms_done = 0
                for child_name in hard_subtree:
                    child = graph_manager.get_node(child_name)
                    if child is not None and child.type == "Milestone":
                        ms_total += 1
                        if child.status == STATUS_DONE:
                            ms_done += 1
                ms_label = "milestone" if ms_total == 1 else "milestones"
                parts = []
                if ms_total > 0:
                    parts.append(f"{ms_done}/{ms_total} {ms_label}")
                parts.append(f"{completion['done']}/{completion['total']} hard subtasks")
                parts.append(f"{remaining} remaining")
                #   (nbsp) sits next to the regular space so it doesn't
                # collapse — gives a visibly wider gap on each side of the
                # middle dot than a plain " · " would.
                progress_text = "  ·  ".join(parts)

        show_priority = {"display": "none"}
        priority_badge = ""

        # Subtasks use the same filter-aware dependency view as the graph and
        # simulation, so a hidden bridge cannot leave orphaned descendants.
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        subtask_nodes, edges = _collect_details_subtasks(
            node_name, include_soft, include_synergies, max_depth,
            global_filters)

        # Milestones roster — derived from the same filtered subtask_nodes the
        # Subtasks table uses, so the strip stays in lockstep with the table.
        ms_section_style, bottom_toggles_style, ms_tiles = _build_milestones_section(
            subtask_nodes, node_name, edges)

        return (
            {"display": "none"},
            {"display": "flex", "flexDirection": "column", "flex": "1",
             "padding": "0 18px", "overflowY": "auto"},
            _selection_output(node_name),
            node.name,
            badges,
            node.description or "No description.",
            node.type or "—",
            node.status or "—",
            ctx_str,
            time_str,
            str(node.value),
            str(node.interest),
            str(node.difficulty),
            show_progress, progress_val, progress_text,
            show_priority, priority_badge,
            ms_section_style, bottom_toggles_style, ms_tiles,
            ratings_own_style, ratings_inherited_style, ratings_inherited_text,
        )

    # --- Subtasks table: selection placeholder, then render after layout ---
    # The full table is the largest remaining Details response. Keep it out of
    # the initial animation window: selection clears the stale table cheaply,
    # and details_deferred_subtasks.js requests the real rows only after the
    # newest Cytoscape layout has stopped. Filter/refresh changes on an already
    # rendered node remain immediate.
    @app.callback(
        Output("details-subtasks-table-container", "children"),
        Input("details-selected-node-store", "data"),
        Input("details-layout-settled-trigger-input", "value"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("override-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-done", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-node-type", "value"),
        Input("filter-dormant", "value"),
        Input("details-hide-blocked", "value"),
        State("details-freeze-rerender-store", "data"),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def render_details_subtasks(selected_node, settled_token, _refresh,
                                _version, _override_data,
                                include_soft_val, include_synergies_val,
                                max_depth_val, f_context, f_subcontext,
                                f_done, f_value, f_interest, f_time,
                                f_difficulty, f_node_types, f_show_dormant,
                                hide_blocked_val, freeze_on):
        if not selected_node:
            return html.Div(
                "Select a node to see subtasks.",
                className="text-muted text-center py-3")

        trigger = get_trigger_id()
        if trigger == "details-selected-node-store" and not freeze_on:
            return html.Div(
                "Loading subtasks…",
                className="text-muted text-center py-3",
                role="status")

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
        max_depth = _normalize_max_depth(max_depth_val)
        global_filters = build_filters(
            f_context, f_subcontext, f_done, f_value, f_interest, f_time,
            f_difficulty, f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters["hide_blocked"] = True

        subtask_nodes, edges = _collect_details_subtasks(
            selected_node, include_soft, include_synergies, max_depth,
            global_filters)
        non_milestone_subtasks = [
            node for node in subtask_nodes if node.type != "Milestone"]
        return build_details_subtasks_table(
            non_milestone_subtasks, graph_manager=graph_manager, edges=edges,
            parent_name=selected_node, include_soft=include_soft,
            include_synergies=include_synergies)

    # --- Toggle milestone filters ---
    @app.callback(
        Output("details-milestones-section", "style", allow_duplicate=True),
        Output("details-subtask-toggles-bottom", "style", allow_duplicate=True),
        Output("details-milestones-tiles", "children", allow_duplicate=True),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-done", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-node-type", "value"),
        Input("filter-dormant", "value"),
        Input("details-hide-blocked", "value"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def toggle_details_subtask_filters(include_soft_val, include_synergies_val,
                                       max_depth_val,
                                       f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant,
                                       hide_blocked_val, selected_node):
        if not selected_node:
            return no_update, no_update, no_update

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)
        max_depth = _normalize_max_depth(max_depth_val)

        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        subtask_nodes, edges = _collect_details_subtasks(
            selected_node, include_soft, include_synergies, max_depth,
            global_filters)

        # Milestones roster shares the same filtered, depth-limited view as
        # the table, so both surfaces stay in lockstep.
        ms_section_style, bottom_toggles_style, ms_tiles = _build_milestones_section(
            subtask_nodes, selected_node, edges)

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

    # --- Sync Milestones-row controls with the canonical Subtasks-row controls ---
    # The controls render twice (top: with the Milestones header;
    # bottom: with the Subtasks header). Only one set is visible at a time;
    # the user's interaction with whichever set is showing must propagate to
    # the other so the canonical (no-suffix) IDs always reflect the current
    # value — every existing scoring/filter callback listens to those.
    #
    # Each pair gets its own two-way sync callback that no_updates when the
    # other side already matches, keeping the dispatch from looping.
    def _register_control_sync(canonical_id, default):
        top_id = f"{canonical_id}-top"

        @app.callback(
            Output(canonical_id, "value", allow_duplicate=True),
            Output(top_id, "value", allow_duplicate=True),
            Input(canonical_id, "value"),
            Input(top_id, "value"),
            prevent_initial_call=True,
        )
        def _sync(canonical_val, top_val):
            trig = get_trigger_id()
            canonical_val = default if canonical_val is None else canonical_val
            top_val = default if top_val is None else top_val
            if canonical_val == top_val:
                return no_update, no_update
            if trig == canonical_id:
                return no_update, canonical_val
            return top_val, no_update
        # Give Dash a unique function name per registration so logs/errors
        # are easier to attribute to the right toggle pair.
        _sync.__name__ = f"sync_control_{canonical_id.replace('-', '_')}"
        return _sync

    # Max Depth is absent here: it now lives in the graph-settings panel as a
    # single control, so there is no -top twin to keep in sync.
    for _control_id, _default in (
            ("details-include-soft-needs", ["include"]),
            ("details-include-synergies", []),
            ("details-show-cross-links", ["show"]),
            ("details-hide-done", []),
            ("details-hide-blocked", [])):
        _register_control_sync(_control_id, _default)

    # --- Dependency Graph ---
    # Outputs to details-elements-pending-store; a clientside callback in
    # callbacks.py applies freeze bypass (direct cy mutation during freeze)
    # or forwards to details-mini-graph.elements normally.
    @app.callback(
        Output("details-elements-pending-store", "data"),
        Input("details-selected-node-store", "data"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("details-show-cross-links", "value"),
        Input("filter-node-type", "value"),
        Input("filter-done", "value"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-dormant", "value"),
        Input("details-hide-blocked", "value"),
    )
    @database.snapshot_read
    def update_details_graph(selected_node, _refresh, _version,
                             include_soft_val, include_synergies_val,
                             max_depth_val, show_cross_links_val,
                             f_node_types, f_done, f_context, f_subcontext,
                             f_value, f_interest, f_time, f_difficulty,
                             f_show_dormant, hide_blocked_val):
        if not selected_node:
            return []
        global_filters = build_filters(f_context, f_subcontext, f_done,
                                       f_value, f_interest, f_time, f_difficulty,
                                       f_node_types, f_show_dormant=f_show_dormant)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        return _build_graph_elements(selected_node, include_soft_val,
                                     include_synergies_val, global_filters,
                                     max_depth=_normalize_max_depth(max_depth_val),
                                     show_cross_links=bool(
                                         show_cross_links_val
                                         and "show" in show_cross_links_val))

    # --- Clicking a node in the dep graph → select it ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-mini-graph", "tapNodeData"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def dep_graph_node_click(tap_data, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not tap_data:
            return no_update
        return tap_data.get("id", no_update)

    # Browser-generated sequence numbers let both the worker and the chart
    # discard superseded selections, even if responses arrive out of order.
    # Layout-affecting changes first send a node-less request, which cancels
    # older work without starting another simulation. The selected node is
    # released only after the newest Cytoscape layout settles. Frozen canvases
    # bypass the gate because they intentionally produce no layout events.
    app.clientside_callback(
        ClientsideFunction(namespace="skillTreeSimulation", function_name="request"),
        Output("details-sim-request", "data"),
        Input("details-selected-node-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("filter-context", "value"), Input("filter-subcontext", "value"),
        Input("filter-done", "value"), Input("filter-value", "value"),
        Input("filter-interest", "value"), Input("filter-time", "value"),
        Input("filter-difficulty", "value"), Input("filter-node-type", "value"),
        Input("filter-dormant", "value"), Input("details-hide-blocked", "value"),
        Input("filter-time-unit", "value"), Input("graph-version-store", "data"),
        Input("settings-save-status", "children"),
        Input("details-simulation-settled-trigger-input", "value"),
        Input("main-tabs", "active_tab"),
        State("details-freeze-rerender-store", "data"),
    )

    @app.callback(Output("details-sim-result", "data"),
                  Input("details-sim-request", "data"), prevent_initial_call=True)
    def run_details_simulation(request):
        if not request:
            return no_update
        session, sequence = request['session'], request['sequence']
        if not simulation_service.begin(session, sequence):
            return no_update
        identity = dict(session=session, sequence=sequence)
        if not request.get('node'):
            return no_update  # begin() still cancels work from the previous tab.
        cancelled = lambda: simulation_service.cancelled(session, sequence)
        filters = build_filters(
            request.get('context'), request.get('subcontext'), request.get('done'),
            request.get('value'), request.get('interest'), request.get('time'),
            request.get('difficulty'), request.get('types'),
            f_time_unit=request.get('timeUnit'), f_show_dormant=request.get('dormant'))
        if 'hide_blocked' in (request.get('hideBlocked') or []):
            filters['hide_blocked'] = True
        try:
            fig, results_style, empty_style = _run_simulation(
                request['node'], request.get('soft'), request.get('helps'),
                global_filters=filters, max_depth=_normalize_max_depth(request.get('depth')),
                should_cancel=cancelled)
            if cancelled():
                return no_update
            if fig is no_update:
                return {**identity, 'error': 'This node is no longer available.'}
            return {**identity, 'figure': fig, 'resultsStyle': results_style,
                    'emptyStyle': empty_style, 'caption': ''}
        except SimulationCancelled:
            return no_update
        except Exception:
            logging.getLogger(__name__).exception("Time simulation failed")
            return {**identity, 'error': 'Could not calculate this estimate.'}

    app.clientside_callback(
        ClientsideFunction(namespace="skillTreeSimulation", function_name="render"),
        Output("details-sim-chart", "figure"), Output("details-sim-results", "style"),
        Output("details-sim-empty", "style"), Output("details-sim-status", "children"),
        Input("details-sim-result", "data"), Input("details-sim-request", "data"),
    )

    # --- Run Simulation from context menu trigger ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-simulate-trigger-input", "value"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def context_menu_simulate_trigger(trigger_val, active_tab):
        if not trigger_val:
            return no_update
        # Parse "nodeName|timestamp"
        node_name = trigger_val.split('|')[0].strip()
        if not node_name:
            return no_update
        # Select the node — which will auto-run simulation
        return node_name

    # --- Focus on Canvas ---
    @app.callback(
        Output("focus-goal-store", "data", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input("btn-details-focus", "n_clicks"),
        State("details-selected-node-store", "data"),
        State("details-mini-graph", "elements"),
        prevent_initial_call=True,
    )
    def details_focus_canvas(n_clicks, selected_node, mini_graph_elements):
        if not n_clicks or not selected_node:
            return no_update, no_update
        # Extract node IDs from the mini-graph elements (exclude edges)
        subtree = [el["data"]["id"] for el in (mini_graph_elements or [])
                   if "source" not in el.get("data", {})]
        return {"node": selected_node, "subtree": subtree}, "tab-canvas"

    # --- Edit Node → Open editor overlay (no tab switch) ---
    @app.callback(
        Output("details-edit-trigger-input", "value", allow_duplicate=True),
        Input("btn-details-edit", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def details_edit_node(n_clicks, selected_node):
        if not n_clicks or not selected_node:
            return no_update
        import time
        return f"{selected_node}|{int(time.time())}"


    # --- Context Menu "Details" → Navigate to Details tab with node selected ---
    @app.callback(
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-navigate-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def context_menu_details_navigate(trigger_val):
        if not trigger_val:
            return no_update, no_update
        node_name = trigger_val.split('|')[0].strip()
        if not node_name:
            return no_update, no_update
        return "tab-details", node_name

    # --- Context Menu "Explain" → select node + open modal (stay on current tab) ---
    # The modal renders via React Portal (dbc.Modal uses createPortal), so it is
    # visible from any tab even though it lives inside details-tab-content.
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Output("modal-details-explain", "is_open", allow_duplicate=True),
        Input("details-explain-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def context_menu_explain_open(trigger_val):
        if not trigger_val:
            return no_update, no_update
        node_name = trigger_val.split('|')[0].strip()
        if not node_name:
            return no_update, no_update
        return node_name, True

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

    # --- Empty-state suggestions: override + priority goals + top recs ---
    @app.callback(
        Output("details-suggestions-container", "children"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("override-store", "data"),
    )
    def build_empty_state_suggestions(_refresh, _version, _override_data):
        from next_callbacks import get_container_suggestions

        seen = set()

        override_row = None
        override_name = ConfigManager.get_override().get("parent")
        if override_name:
            override_node = graph_manager.get_node(override_name)
            if override_node and not override_node.dormant:
                override_row = _build_suggestion_row(override_name, "Override", "pink")
                seen.add(override_name)

        goal_rows = []
        for i, goal_name in enumerate(ConfigManager.get_priority_goals()[:3]):
            if goal_name in seen:
                continue
            goal_node = graph_manager.get_node(goal_name)
            if not goal_node or goal_node.dormant:
                continue
            goal_rows.append(_build_suggestion_row(
                goal_name, str(i + 1), "warning"))
            seen.add(goal_name)

        rec_nodes = get_container_suggestions(count=5, exclude_names=seen)
        for n in rec_nodes:
            seen.add(n.name)

        max_tv = max((getattr(n, "total_value", 0) for n in rec_nodes),
                     default=0)
        rec_rows = []
        tooltip_text = ("Normalized total value (0–100) from the priority "
                        "scoring algorithm — cascade-driven score for this "
                        "container.")
        for i, n in enumerate(rec_nodes):
            raw = getattr(n, "total_value", 0)
            normalized = round((raw / max_tv) * 100) if max_tv else 0
            rec_rows.append(_build_suggestion_row(
                n.name, str(normalized),
                badge_style(STATUS_OPEN)["backgroundColor"],
                badge_id=f"details-sugg-rec-badge-{i}",
                tooltip_text=tooltip_text,
            ))

        return build_details_suggestions(override_row, goal_rows, rec_rows)

    # --- Suggestion Click → Select that node in Details ---
    @app.callback(
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-suggestion-item", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def select_suggested_node(n_clicks_list, active_tab):
        if active_tab != "tab-details":
            return no_update
        if not any(n_clicks_list):
            return no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update
        return triggered["index"]

    # --- Add Node Modal: Open ---
    @app.callback(
        Output("modal-details-add-node", "is_open", allow_duplicate=True),
        Output("details-add-type", "options"),
        Output("details-add-context", "options", allow_duplicate=True),
        Output("details-add-subcontext", "options", allow_duplicate=True),
        Output("details-add-existing-dropdown", "options"),
        Output("details-add-existing-dropdown", "value"),
        Output("details-add-name", "value"),
        Output("details-add-desc", "value"),
        Output("details-add-save-status", "children", allow_duplicate=True),
        Output("details-add-time-unit", "value"),
        Output("details-add-value", "value"),
        Output("details-add-interest", "value"),
        Output("details-add-difficulty", "value"),
        Output("details-add-time-o", "value"),
        Output("details-add-time-m", "value"),
        Output("details-add-time-p", "value"),
        Output("details-add-context", "value", allow_duplicate=True),
        Output("details-add-subcontext", "value", allow_duplicate=True),
        Output("details-add-mode", "value"),
        # Relationship dropdowns
        Output("details-add-needs-hard", "options"),
        Output("details-add-needs-soft", "options"),
        Output("details-add-supports-hard", "options"),
        Output("details-add-supports-soft", "options"),
        Output("details-add-helps", "options"),
        Output("details-add-needs-hard", "value"),
        Output("details-add-needs-soft", "value"),
        Output("details-add-supports-hard", "value"),
        Output("details-add-supports-soft", "value"),
        Output("details-add-helps", "value"),
        # Time mode reset
        Output("details-add-time-mode", "value"),
        # External resource stores reset
        Output("details-add-obsidian-store", "data"),
        Output("details-add-drive-store", "data"),
        Output("details-add-website-store", "data"),
        # Override reset
        Output("details-add-override-toggle", "value"),
        # Value mode reset
        Output("details-add-value-mode", "value"),
        # Habit-mode reset (7 new outputs)
        Output("details-add-time-habit-mode", "value"),
        Output("details-add-habit-duration", "value"),
        Output("details-add-habit-duration-unit", "value"),
        Output("details-add-habit-intensity-o", "value"),
        Output("details-add-habit-intensity-m", "value"),
        Output("details-add-habit-intensity-p", "value"),
        Output("details-add-habit-intensity-unit", "value"),
        Output("details-add-habit-days", "value"),
        Input("btn-details-add-node", "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def open_add_node_modal(n_clicks, selected_node):
        if not n_clicks:
            return (no_update,) * 43

        types = ConfigManager.get_node_types()
        contexts = sort_contexts(ConfigManager.get_contexts())
        type_opts = [{"label": t, "value": t} for t in types]
        ctx_opts = [{"label": c, "value": c} for c in contexts]

        all_nodes = graph_manager.get_all_nodes()
        subtree = graph_manager.get_goal_subtree(selected_node) if selected_node else set()
        exclude = subtree | {selected_node} if selected_node else set()
        node_opts = [{"label": n.name, "value": n.name}
                     for n in sorted(all_nodes, key=lambda n: n.name)]
        existing_opts = [opt for opt in node_opts if opt["value"] not in exclude]

        _ted = ConfigManager.get_time_estimate_defaults()

        return (
            True, type_opts, ctx_opts, [{"label": "None", "value": ""}],
            existing_opts, None, "", "", "", _ted.get('unit', 'weeks'),
            5, 5, 5,
            _ted.get('optimistic', 2),
            _ted.get('expected', 4),
            _ted.get('pessimistic', 6),
            "", "",
            "create",
            # Relationship dropdown options + values (cleared)
            node_opts, node_opts, node_opts, node_opts, node_opts,
            [], [], [], [], [],
            # Time mode reset
            [],
            # Reset external resource stores
            [''], [''], [''],
            # Override reset
            [],
            # Value mode reset
            [],
            # Habit reset
            [],            # details-add-time-habit-mode
            0,             # details-add-habit-duration
            'weeks',       # details-add-habit-duration-unit
            0, 0, 0,       # details-add-habit-intensity o/m/p
            'min_per_session',  # details-add-habit-intensity-unit
            [0, 1, 2, 3, 4, 5, 6],  # details-add-habit-days
        )

    # --- Add Node Modal: Toggle mode ---
    app.clientside_callback(
        """
        function(mode) {
            if (mode === 'link') return [{display: 'none'}, {display: 'block'}];
            return [{display: 'block'}, {display: 'none'}];
        }
        """,
        Output("details-add-create-section", "style"),
        Output("details-add-link-section", "style"),
        Input("details-add-mode", "value"),
    )

    # --- Add Node Modal: Update subcontexts ---
    @app.callback(
        Output("details-add-subcontext", "options"),
        Input("details-add-context", "value"),
    )
    def update_add_subcontexts(context):
        base = [{"label": "None", "value": ""}]
        if not context:
            return base
        subs = sort_subcontexts(ConfigManager.get_subcontexts().get(context, []))
        return base + [{"label": s, "value": s} for s in subs]

    # --- Explain modal: the arithmetic is a disclosure, closed by default ---
    @app.callback(
        Output("collapse-details-explain-summary", "is_open"),
        Input("btn-details-explain-summary-toggle", "n_clicks"),
        State("collapse-details-explain-summary", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_details_explain_summary(n, is_open):
        if n:
            return not is_open
        return is_open

    app.clientside_callback(
        "function(isOpen){ return 'editor-chevron on-dark' + (isOpen ? ' open' : ''); }",
        Output("details-explain-summary-chevron", "className"),
        Input("collapse-details-explain-summary", "is_open"),
    )

    # --- Add Node Modal: Aliases (mirrors the main node editor) ---
    @app.callback(
        Output("collapse-details-add-aliases", "is_open"),
        Input("btn-details-add-aliases-toggle", "n_clicks"),
        State("collapse-details-add-aliases", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_details_add_aliases(n, is_open):
        if n:
            return not is_open
        return is_open

    app.clientside_callback(
        "function(isOpen){ return 'editor-chevron' + (isOpen ? ' open' : ''); }",
        Output("details-add-aliases-chevron", "className"),
        Input("collapse-details-add-aliases", "is_open"),
    )

    @app.callback(
        Output("details-add-aliases-container", "children"),
        Input("details-add-aliases-store", "data"),
    )
    def render_details_add_aliases(aliases):
        return render_alias_rows(aliases, 'details-add-alias-input', 'btn-details-add-alias-remove')

    @app.callback(
        [Output("details-add-aliases-store", "data", allow_duplicate=True),
         Output("collapse-details-add-aliases", "is_open", allow_duplicate=True)],
        [Input("btn-details-add-alias-add", "n_clicks"),
         Input({"type": "btn-details-add-alias-remove", "index": ALL}, "n_clicks")],
        [State({"type": "details-add-alias-input", "index": ALL}, "value"),
         State("details-add-aliases-store", "data")],
        prevent_initial_call=True,
    )
    def modify_details_add_aliases(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        aliases = list(current_values) if current_values else list(store_data or [''])
        collapse_update = no_update
        if trigger == "btn-details-add-alias-add":
            aliases.append('')
        elif isinstance(trigger, dict) and trigger.get("type") == "btn-details-add-alias-remove":
            idx = trigger["index"]
            if 0 <= idx < len(aliases):
                aliases.pop(idx)
                if not aliases:
                    collapse_update = False
        return aliases, collapse_update

    # Reset the alias rows to a single blank each time the (create-only) modal
    # opens, so a fresh add never inherits the previous node's aliases.
    @app.callback(
        Output("details-add-aliases-store", "data", allow_duplicate=True),
        Input("modal-details-add-node", "is_open"),
        prevent_initial_call=True,
    )
    def reset_details_add_aliases(is_open):
        return [''] if is_open else no_update

    # --- Add Node Modal: Mode toggles control OMP / Habit visibility ---
    app.clientside_callback(
        """
        function(inherit_val, habit_val) {
            var inherit_on = !!(inherit_val && inherit_val.indexOf('inherited') >= 0);
            var habit_on = !!(habit_val && habit_val.indexOf('habit') >= 0);
            if (inherit_on) return [{display: 'none'}, {display: 'none'}];
            if (habit_on) return [{display: 'none'}, {display: 'block'}];
            return [{display: 'block'}, {display: 'none'}];
        }
        """,
        Output("details-add-time-omp", "style"),
        Output("section-details-add-time-habit", "style"),
        Input("details-add-time-mode", "value"),
        Input("details-add-time-habit-mode", "value"),
        prevent_initial_call=True,
    )

    # --- Add Node Modal: Habit / Inherit mutual exclusivity ---
    # Clientside to avoid the visible flash of the "other" toggle flipping
    # on before the server bounces it off.
    app.clientside_callback(
        """
        function(inherit_val, habit_val) {
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var trig = triggered.length ? triggered[0].prop_id.split('.')[0] : null;
            if (trig === 'details-add-time-mode' && inherit_val && inherit_val.indexOf('inherited') >= 0) {
                return [inherit_val, []];
            }
            if (trig === 'details-add-time-habit-mode' && habit_val && habit_val.indexOf('habit') >= 0) {
                return [[], habit_val];
            }
            return [inherit_val, habit_val];
        }
        """,
        Output("details-add-time-mode", "value", allow_duplicate=True),
        Output("details-add-time-habit-mode", "value", allow_duplicate=True),
        Input("details-add-time-mode", "value"),
        Input("details-add-time-habit-mode", "value"),
        prevent_initial_call=True,
    )

    # --- Add Node Modal: Live total-hours preview for habit ---
    @app.callback(
        Output("details-add-habit-total-preview", "children"),
        Input("details-add-habit-duration", "value"),
        Input("details-add-habit-duration-unit", "value"),
        Input("details-add-habit-intensity-m", "value"),
        Input("details-add-habit-intensity-unit", "value"),
        Input("details-add-habit-days", "value"),
    )
    def update_details_add_habit_preview(duration, dur_unit, intensity_m, int_unit, days):
        return habit_preview_text(duration, dur_unit, intensity_m, int_unit, days)

    # --- Add Node Modal: Inherit-ratings toggle hides/shows V/I/E sliders ---
    app.clientside_callback(
        """
        function(mode_val) {
            if (mode_val && mode_val.indexOf('inherited') >= 0) {
                return {display: 'none'};
            }
            return {display: 'block'};
        }
        """,
        Output("details-add-ratings", "style"),
        Input("details-add-value-mode", "value"),
        prevent_initial_call=True,
    )

    # --- Add Node Modal: Lock Inherit-value ON for Milestones ---
    # Milestones are transparent checkpoints; their own value never enters
    # scoring. Mirrors the main editor's Milestone value lock. Goals exempt.
    app.clientside_callback(
        """
        function(value_mode_val, node_type) {
            var no_update = window.dash_clientside.no_update;
            var hidden = {display: "none"};
            var visible = {display: "block", color: "#dc3545", fontSize: "0.85rem"};
            var ctx = window.dash_clientside.callback_context;
            var triggered = (ctx && ctx.triggered) || [];
            var ids = triggered.map(function(t) { return t.prop_id.split('.')[0]; });
            var only_value_mode = ids.length === 1 && ids[0] === 'details-add-value-mode';

            if (node_type !== 'Milestone') {
                return [no_update, hidden, ""];
            }
            var inherited_on = !!(value_mode_val && value_mode_val.indexOf('inherited') >= 0);
            if (inherited_on) {
                if (only_value_mode) return [no_update, no_update, no_update];
                return [no_update, hidden, ""];
            }
            var msg = "Inherit is required for Milestone nodes — they are " +
                      "checkpoints, so their own ratings don't affect scoring.";
            if (only_value_mode) return [['inherited'], visible, msg];
            return [['inherited'], hidden, ""];
        }
        """,
        Output('details-add-value-mode', 'value', allow_duplicate=True),
        Output('details-add-value-mode-warning', 'style'),
        Output('details-add-value-mode-warning', 'children'),
        Input('details-add-value-mode', 'value'),
        Input('details-add-type', 'value'),
        prevent_initial_call=True,
    )

    # --- Add Node Modal: Hide Effort slider on Goals; show caption instead ---
    app.clientside_callback(
        """
        function(node_type) {
            if (node_type === 'Goal') return [{display: 'none'}, {}];
            return [{}, {display: 'none'}];
        }
        """,
        Output("details-add-effort-row", "style"),
        Output("details-add-effort-caption", "style"),
        Input("details-add-type", "value"),
    )

    # --- Add Node Modal: External Resources Link Renderers ---
    @app.callback(
        Output('details-add-obsidian-container', 'children'),
        Input('details-add-obsidian-store', 'data'),
    )
    def render_details_add_obsidian(links):
        return render_link_rows(links, 'details-add-obsidian-link', has_browse=True)

    @app.callback(
        Output('details-add-drive-container', 'children'),
        Input('details-add-drive-store', 'data'),
    )
    def render_details_add_drive(links):
        return render_link_rows(strip_gdrive_prefix(links), 'details-add-drive-link', has_browse=True)

    @app.callback(
        Output('details-add-website-container', 'children'),
        Input('details-add-website-store', 'data'),
    )
    def render_details_add_website(links):
        return render_link_rows(links, 'details-add-website-link', has_browse=False)

    # --- Add Node Modal: Link Add/Remove/Browse for Obsidian ---
    @app.callback(
        Output('details-add-obsidian-store', 'data', allow_duplicate=True),
        Input('btn-details-add-obsidian-add', 'n_clicks'),
        Input({'type': 'btn-details-add-obsidian-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-details-add-obsidian-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'details-add-obsidian-link', 'index': ALL}, 'value'),
        State('details-add-obsidian-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_details_add_obsidian(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-details-add-obsidian-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-details-add-obsidian-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-details-add-obsidian-browse':
                if not any(browse_clicks):
                    return no_update
                idx = trigger['index']
                vault = ConfigManager.get_obsidian_vault()
                abs_path = spawn_local_file_picker(
                    initial_dir=vault,
                    title="Select Obsidian File",
                    filetypes_list=[("Markdown files", "*.md"), ("All files", "*.*")],
                )
                if abs_path:
                    vault_norm = os.path.normpath(vault)
                    rel = abs_path[len(vault_norm):].lstrip(os.sep) if abs_path.startswith(vault_norm) else abs_path
                    if 0 <= idx < len(links):
                        links[idx] = rel
        return links

    # --- Add Node Modal: Link Add/Remove/Browse for Drive ---
    @app.callback(
        Output('details-add-drive-store', 'data', allow_duplicate=True),
        Input('btn-details-add-drive-add', 'n_clicks'),
        Input({'type': 'btn-details-add-drive-link-remove', 'index': ALL}, 'n_clicks'),
        Input({'type': 'btn-details-add-drive-browse', 'index': ALL}, 'n_clicks'),
        State({'type': 'details-add-drive-link', 'index': ALL}, 'value'),
        State('details-add-drive-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_details_add_drive(add_clicks, remove_clicks, browse_clicks, current_values, store_data):
        from callback_helpers import expand_gdrive_prefix
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-details-add-drive-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-details-add-drive-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
            elif trigger.get('type') == 'btn-details-add-drive-browse':
                if not any(browse_clicks):
                    return no_update
                idx = trigger['index']
                gdrive = ConfigManager.get_gdrive_path() or ''
                abs_path = spawn_local_file_picker(
                    initial_dir=gdrive,
                    title="Select Google Drive File",
                    filetypes_list=[("All files", "*.*")],
                )
                if abs_path:
                    if 0 <= idx < len(links):
                        links[idx] = abs_path
        # Store with full prefix for DB; UI shows stripped
        return [expand_gdrive_prefix(p) if p else p for p in links]

    # --- Add Node Modal: Link Add/Remove for Website ---
    @app.callback(
        Output('details-add-website-store', 'data', allow_duplicate=True),
        Input('btn-details-add-website-add', 'n_clicks'),
        Input({'type': 'btn-details-add-website-link-remove', 'index': ALL}, 'n_clicks'),
        State({'type': 'details-add-website-link', 'index': ALL}, 'value'),
        State('details-add-website-store', 'data'),
        prevent_initial_call=True,
    )
    def modify_details_add_website(add_clicks, remove_clicks, current_values, store_data):
        trigger = ctx.triggered_id
        links = list(current_values) if current_values else list(store_data or [''])
        if trigger == 'btn-details-add-website-add':
            links.append('')
        elif isinstance(trigger, dict):
            if trigger.get('type') == 'btn-details-add-website-link-remove':
                idx = trigger['index']
                if 0 <= idx < len(links) and len(links) > 1:
                    links.pop(idx)
        return links

    # --- Add Node Modal: Cancel ---
    @app.callback(
        Output("modal-details-add-node", "is_open", allow_duplicate=True),
        Input("btn-details-add-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_add_node(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Add Node Modal: Save ---
    @app.callback(
        Output("modal-details-add-node", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Output("details-add-save-status", "children"),
        Input("btn-details-add-save", "n_clicks"),
        State("details-selected-node-store", "data"),
        State("details-add-mode", "value"),
        # Link mode
        State("details-add-existing-dropdown", "value"),
        State("details-add-link-edge-type", "value"),
        # Create mode
        State("details-add-name", "value"),
        State("details-add-type", "value"),
        State("details-add-context", "value"),
        State("details-add-subcontext", "value"),
        State("details-add-desc", "value"),
        State("details-add-value", "value"),
        State("details-add-interest", "value"),
        State("details-add-difficulty", "value"),
        State("details-add-time-o", "value"),
        State("details-add-time-m", "value"),
        State("details-add-time-p", "value"),
        State("details-add-time-unit", "value"),
        State("details-add-time-mode", "value"),
        State("details-add-value-mode", "value"),
        # Habit-mode states
        State("details-add-time-habit-mode", "value"),
        State("details-add-habit-duration", "value"),
        State("details-add-habit-duration-unit", "value"),
        State("details-add-habit-intensity-o", "value"),
        State("details-add-habit-intensity-m", "value"),
        State("details-add-habit-intensity-p", "value"),
        State("details-add-habit-intensity-unit", "value"),
        State("details-add-habit-days", "value"),
        # Relationships
        State("details-add-needs-hard", "value"),
        State("details-add-needs-soft", "value"),
        State("details-add-supports-hard", "value"),
        State("details-add-supports-soft", "value"),
        State("details-add-helps", "value"),
        # External resources
        State({'type': 'details-add-obsidian-link', 'index': ALL}, 'value'),
        State({'type': 'details-add-drive-link', 'index': ALL}, 'value'),
        State({'type': 'details-add-website-link', 'index': ALL}, 'value'),
        # Override
        State("details-add-override-toggle", "value"),
        State("details-add-override-mode", "value"),
        # Aliases
        State({"type": "details-add-alias-input", "index": ALL}, "value"),
        prevent_initial_call=True,
    )
    def save_add_node(n_clicks, selected_node, mode,
                      link_node, link_edge_type,
                      name, node_type, context, subcontext, desc,
                      value, interest, difficulty,
                      time_o, time_m, time_p, time_unit, time_mode_val,
                      value_mode_val,
                      time_habit_mode_val,
                      habit_duration, habit_duration_unit,
                      habit_int_o, habit_int_m, habit_int_p, habit_int_unit,
                      habit_days,
                      needs_hard, needs_soft, supports_hard, supports_soft, helps,
                      obsidian_vals, drive_vals, website_vals,
                      override_toggle, override_mode, alias_values):
        from callback_helpers import serialize_links
        if not n_clicks or not selected_node:
            return no_update, no_update, no_update

        if mode == "link":
            if not link_node:
                return no_update, no_update, "Please select a node to link."
            edge_type = EDGE_NEEDS_HARD if link_edge_type == "hard" else EDGE_NEEDS_SOFT
            try:
                graph_manager.add_edge(link_node, selected_node, edge_type)
            except ValueError as e:
                return no_update, no_update, str(e)
            return False, f"link-{link_node}", ""
        else:
            if not name or not name.strip():
                return no_update, no_update, "Node name is required."
            if not node_type:
                return no_update, no_update, "Node type is required."

            multiplier = ConfigManager.get_time_multiplier(time_unit or "weeks")
            t_o = float(time_o or 0) * multiplier
            t_m = float(time_m or 0) * multiplier
            t_p = float(time_p or 0) * multiplier

            obs_path = serialize_links(obsidian_vals)
            drive_path = serialize_links(drive_vals)
            web_path = serialize_links(website_vals)

            # Resolve time_mode via the shared helper — Goal/Milestone always
            # inherit; otherwise habit > inherited > manual.
            t_mode = resolve_time_mode(node_type, time_mode_val, time_habit_mode_val)
            if t_mode == 'habit':
                t_o, t_m, t_p = compute_habit_time_omp(
                    habit_duration or 0, habit_duration_unit or 'weeks',
                    habit_int_o or 0, habit_int_m or 0, habit_int_p or 0,
                    habit_int_unit or 'min_per_session', habit_days,
                )
            # Mirror time_mode — Milestones always inherit value (transparent
            # checkpoints); Goals keep their own value; otherwise the toggle wins.
            v_mode = resolve_value_mode(node_type, value_mode_val)

            new_node = Node(
                name=name.strip(),
                type=node_type,
                description=(desc or "").strip(),
                value=value or 5,
                time_o=t_o, time_m=t_m, time_p=t_p,
                interest=interest or 5,
                difficulty=difficulty or 5,
                status=STATUS_OPEN,
                context=context or None,
                subcontext=(subcontext or "").strip() or None,
                obsidian_path=obs_path,
                google_drive_path=drive_path,
                website=web_path,
                time_mode=t_mode,
                value_mode=v_mode,
                habit_duration=habit_duration or 0,
                habit_duration_unit=habit_duration_unit or 'weeks',
                habit_intensity_o=habit_int_o or 0,
                habit_intensity_m=habit_int_m or 0,
                habit_intensity_p=habit_int_p or 0,
                habit_intensity_unit=habit_int_unit or 'min_per_session',
                **({'habit_days': habit_days} if habit_days is not None else {}),
            )

            try:
                with database.transaction():
                    graph_manager.add_node(new_node)
                    graph_manager.set_aliases(
                        name.strip(), [a for a in (alias_values or []) if a and a.strip()])
                    graph_manager.sync_edges(
                        name.strip(), needs_hard or [], needs_soft or [],
                        list(dict.fromkeys([selected_node, *(supports_hard or [])])),
                        supports_soft or [], helps or [])
                    if override_toggle and "on" in override_toggle:
                        ConfigManager.set_override({
                            "parent": name.strip(), "mode": override_mode or "hard"})
            except ValueError as e:
                return no_update, no_update, str(e)

            return False, f"add-{name}", ""

    # --- Add Node Modal: Override toggle visibility ---
    app.clientside_callback(
        """
        function(on) {
            return (on && on.indexOf('on') >= 0) ? {display: 'block'} : {display: 'none'};
        }
        """,
        Output("details-add-override-options", "style"),
        Input("details-add-override-toggle", "value"),
        prevent_initial_call=True,
    )

    # --- Subtask Remove: Open Modal ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Output("details-subtask-remove-pending", "data"),
        Output("details-subtask-remove-modal-body", "children"),
        Input({"type": "details-subtask-remove", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def open_subtask_remove_modal(n_clicks_list):
        if not any(n_clicks_list):
            return no_update, no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update, no_update
        node_name = triggered["index"]
        body = html.Div([
            html.P([
                'What would you like to do with node ',
                html.Strong(node_name), '?',
            ]),
            html.Ul([
                html.Li([html.Strong("Remove Edge"),
                         " — removes it from this node's dependency list."]),
                html.Li([html.Strong("Delete Node"),
                         " — permanently deletes the node."]),
            ]),
        ])
        return True, node_name, body

    # --- Subtask Remove: Cancel ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Input("btn-details-subtask-remove-cancel", "n_clicks"),
        prevent_initial_call=True,
    )
    def cancel_subtask_remove(n_clicks):
        if n_clicks:
            return False
        return no_update

    # --- Subtask Remove: Remove Edge ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-details-subtask-remove-edge", "n_clicks"),
        State("details-subtask-remove-pending", "data"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_remove_edge(n_clicks, node_name, selected_node):
        if not n_clicks or not node_name or not selected_node:
            return no_update, no_update
        edges = graph_manager.get_edges()
        for e in edges:
            if (e['source'] == node_name and e['target'] == selected_node and
                    e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT)):
                graph_manager.remove_edge(node_name, selected_node, e['type'])
        return False, f"remove-edge-{node_name}"

    # --- Subtask Remove: Delete Node ---
    @app.callback(
        Output("modal-details-subtask-remove", "is_open", allow_duplicate=True),
        Output("details-refresh-trigger", "data", allow_duplicate=True),
        Input("btn-details-subtask-delete-node", "n_clicks"),
        State("details-subtask-remove-pending", "data"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def confirm_delete_node(n_clicks, node_name, selected_node):
        if not n_clicks or not node_name:
            return no_update, no_update
        graph_manager.delete_node(node_name)
        return False, f"delete-{node_name}"

    # --- Details Graph Layout: Toggle Panel ---
    @app.callback(
        Output('details-graph-settings-panel', 'style'),
        Input('btn-details-graph-settings', 'n_clicks'),
        Input('btn-close-details-graph-settings', 'n_clicks'),
        State('details-graph-settings-panel', 'style'),
        prevent_initial_call=True,
    )
    def toggle_details_graph_settings(_n_open, _n_close, current_style):
        style = dict(current_style) if current_style else {}
        style['display'] = 'none' if style.get('display') != 'none' else 'block'
        return style

    # --- Details Graph Layout: Reset to Stored Defaults ---
    @app.callback(
        Output('details-graph-settings-animate', 'value', allow_duplicate=True),
        Output('details-graph-settings-edge-length', 'value', allow_duplicate=True),
        Output('details-graph-settings-gravity', 'value', allow_duplicate=True),
        Output('details-graph-settings-repulsion', 'value', allow_duplicate=True),
        Output('details-graph-settings-freeze-rerender', 'value', allow_duplicate=True),
        Input('btn-reset-details-graph-settings', 'n_clicks'),
        prevent_initial_call=True,
    )
    def reset_details_graph_settings(n_clicks):
        if not n_clicks:
            return (no_update,) * 5
        gl = ConfigManager.get_details_graph_layout_defaults()
        return (
            True,
            gl.get('edge_length', 50),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )

    # --- Details Tab: Node Count Canvas Overlay ---
    # The Details canvas honors the global Context/Subcontext/Type/Done/
    # ratings/time filters but ignores Goal and Community (those only narrow
    # the main canvas), so the indicator only checks the filters that
    # actually affect the subtree being rendered here.
    @app.callback(
        Output('details-canvas-node-count', 'children'),
        Input('details-mini-graph', 'elements'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-done', 'value'),
        Input('details-max-depth', 'value'),
    )
    def update_details_node_count(elements, f_type, f_ctx, f_sub, f_val,
                                  f_int, f_diff, f_time, f_done, max_depth_val):
        n = sum(1 for el in (elements or []) if 'source' not in el.get('data', {}))
        text = f"{n} node{'s' if n != 1 else ''}"
        if _normalize_max_depth(max_depth_val) is not None or is_filters_active(
                node_type=f_type, context=f_ctx, subcontext=f_sub,
                value=f_val, interest=f_int, difficulty=f_diff,
                time=f_time, done=f_done):
            return f"{text} · filtered"
        return text

    # --- Details Graph Layout: layout requests ---
    # Registered with every canvas's in callbacks.py; built by
    # assets/layout_requests.js.

    # Time Simulation waits for the layout a filter change causes. A change
    # that leaves this subtree's nodes and edges as they were (a context with
    # no nodes here) starts no layout, so that wait would never end. This
    # sends the settle signal itself whenever a payload will not be laid out.
    app.clientside_callback(
        ClientsideFunction(
            namespace="skillTreeLayout", function_name="settleUnchanged"),
        Output('details-simulation-settled-trigger-input', 'value'),
        Input('details-elements-pending-store', 'data'),
        State('details-freeze-rerender-store', 'data'),
        State('details-selected-node-store', 'data'),
        prevent_initial_call=True,
    )

    # --- Explain Score modal ---------------------------------------------
    @app.callback(
        Output("modal-details-explain", "is_open"),
        [Input("btn-details-explain", "n_clicks"),
         Input("btn-details-explain-close", "n_clicks")],
        State("modal-details-explain", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_explain_modal(_open_clicks, _close_clicks, is_open):
        return not is_open

    @app.callback(
        [Output("details-explain-title", "children"),
         Output("details-explain-subtitle", "children"),
         Output("details-explain-summary", "children"),
         Output("details-explain-contrib-store", "data"),
         Output("details-explain-count", "value"),
         Output("details-explain-ready-node", "data")],
        [Input("modal-details-explain", "is_open"),
         Input("details-node-select", "value")],
        prevent_initial_call=True,
    )
    def populate_explain_modal(is_open, node_name):
        if not is_open or not node_name:
            return (no_update, no_update, no_update, no_update, no_update,
                    no_update)
        all_nodes = graph_manager.get_all_nodes()
        priority_goals = ConfigManager.get_priority_goals()
        hypers = ConfigManager.get_hyperparams()
        hypers['context_weights'] = ConfigManager.get_context_weights()
        node = next((n for n in all_nodes if n.name == node_name), None)
        is_goal = node is not None and node.type == 'Goal'

        normalized = None
        if is_goal:
            # Goals are sinks in the prereq DAG: explain_score's forward
            # cascade collapses to ~nothing and would mark them ineligible.
            # explain_goal recomputes the breakdown on the inverted prereq
            # graph and pulls the headline score from _rank_goals, so the
            # modal matches the Goals-sidebar ranking exactly.
            from analyze_callbacks import explain_goal
            result = explain_goal(node_name, all_nodes,
                                  graph_manager.get_edges(),
                                  hypers, priority_goals)
            breakdown, normalized = result if result else (None, None)
        else:
            # The repetition adjustment is a property of the whole pool, so
            # it comes from the ranking pass rather than being recomputed
            # here — that way the modal can never report a score the Next
            # tab disagrees with.
            scored = graph_manager.calculate_priority_scores(
                all_nodes, priority_goals=priority_goals,
            )
            ranked = next((n for n in scored if n.name == node_name), None)
            breakdown = explain_score(
                node_name,
                all_nodes,
                graph_manager.get_edges(),
                hypers,
                priority_goals=priority_goals,
                variety=getattr(ranked, 'variety', None),
            )
            # Same base as every other 0-100 priority in the app — see
            # GraphManager.get_priority_normalizer.
            if breakdown and breakdown['eligible'] and breakdown['score'] > 0:
                top = graph_manager.get_priority_normalizer()
                if top > 0:
                    normalized = round((breakdown['score'] / top) * 100)
        title = node_name if breakdown else "Node not found"

        # Where this node's total value sits among comparable ones. Goals are
        # ranked against Goals because their value is computed on the inverted
        # prerequisite graph and is not comparable to an ordinary node's.
        subtitle = ""
        tv = breakdown['composition']['total_value'] if breakdown else None
        if tv is not None:
            if is_goal:
                from analyze_callbacks import _rank_goals
                goals = [n for n in all_nodes if n.type == 'Goal']
                ranked_goals = _rank_goals(
                    goals, all_nodes, graph_manager.get_edges(),
                    priority_goals, hypers, with_components=True,
                )
                peers = [c.get('tv') for _, c in ranked_goals]
                subtitle = format_value_rank(tv, peers, "goals")
            else:
                peer_nodes = graph_manager.calculate_priority_scores(
                    all_nodes, priority_goals=priority_goals,
                )
                peers = [getattr(n, 'total_value', None) for n in peer_nodes
                         if n.type not in ('Goal', 'Milestone')
                         and n.status != STATUS_DONE]
                subtitle = format_value_rank(tv, peers, "projects")

        contributors = breakdown['contributors'] if breakdown else []
        # Reset count to default only when the modal opens — not when the
        # user selects a different node while it's already open.
        count_out = 10 if ctx.triggered_id == "modal-details-explain" else no_update
        return (title, subtitle, build_explain_summary(breakdown, normalized),
                contributors, count_out, node_name)

    @app.callback(
        [Output("details-explain-chart", "figure"),
         Output("details-explain-chart", "style"),
         Output("details-explain-chart-placeholder", "style"),
         Output("details-explain-chart-placeholder", "children")],
        [Input("details-explain-count", "value"),
         Input("details-explain-contrib-store", "data"),
         Input("details-explain-ready-node", "data"),
         Input("modal-details-explain", "is_open"),
         Input("details-node-select", "value")],
        prevent_initial_call=True,
    )
    def update_explain_chart(count, contributors, ready_node, is_open,
                             selected_node):
        placeholder_style = {
            "minHeight": "260px",
            "fontSize": "0.85rem",
        }
        if not is_open or not selected_node or ready_node != selected_node:
            return (no_update, {"display": "none"}, placeholder_style,
                    "Preparing explanation…")
        if not contributors:
            return (no_update, {"display": "none"}, placeholder_style,
                    "No contributors to display.")
        try:
            n = max(1, int(count)) if count else 10
        except (TypeError, ValueError):
            n = 10
        return (build_explain_chart(contributors, top_n=n), {},
                {"display": "none"}, "")

    @app.callback(
        [Output("details-explain-focus-feedback", "children"),
         Output("btn-details-explain-focus", "disabled")],
        Input("details-explain-focus-count", "value"),
        prevent_initial_call=True,
    )
    def validate_focus_count(val):
        if val is None:
            return "", False
        try:
            n = int(val)
        except (TypeError, ValueError):
            return "", False
        if n > 5:
            return "Max is 5", True
        if n < 1:
            return "Min is 1", True
        return "", False

    @app.callback(
        Output("focus-goal-store", "data", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Output("modal-details-explain", "is_open", allow_duplicate=True),
        Input("btn-details-explain-focus", "n_clicks"),
        [State("details-selected-node-store", "data"),
         State("details-explain-contrib-store", "data"),
         State("details-explain-focus-count", "value")],
        prevent_initial_call=True,
    )
    def focus_top_contributor_paths(n_clicks, selected_node, contributors, k):
        if not n_clicks or not selected_node or not contributors:
            return no_update, no_update, no_update
        try:
            k_int = max(1, min(5, int(k))) if k else 3
        except (TypeError, ValueError):
            k_int = 3
        # Top-K contributors excluding Self; rank by list position.
        ranked_targets = []
        for c in contributors:
            name = c.get('name')
            if not name or name == selected_node:
                continue
            ranked_targets.append((len(ranked_targets) + 1, name))
            if len(ranked_targets) >= k_int:
                break
        all_nodes_fc = graph_manager.get_all_nodes()
        node_fc = next((n for n in all_nodes_fc if n.name == selected_node), None)
        is_goal_fc = node_fc is not None and node_fc.type == 'Goal'
        edges_fc = graph_manager.get_edges()
        if is_goal_fc:
            # A Goal's contributors are its prerequisites (upstream), so the
            # paths to them run against the arrows — walk the inverted
            # Hard/Soft graph. Helps is symmetric and left alone.
            edges_fc = [
                {'source': e['target'], 'target': e['source'], 'type': e['type']}
                if e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT) else e
                for e in edges_fc
            ]
        pi = shortest_paths_focus_data(
            selected_node, ranked_targets, all_nodes_fc, edges_fc,
        )
        edge_rank_items = list(pi['edge_rank'].items())
        if is_goal_fc:
            # Flip keys back to real edge orientation so the canvas matches
            # them against actual prereq -> dependent edges.
            edge_rank_items = [((t, s, etype), r)
                               for (s, t, etype), r in edge_rank_items]
        # Serialize edge_rank keys for JSON compatibility in dcc.Store.
        edge_rank_str = {
            f"{s}|{t}|{etype}": r
            for (s, t, etype), r in edge_rank_items
        }
        return (
            {"node": selected_node,
             "subtree": pi['subtree'],
             "path_info": {
                 "node_rank": pi['node_rank'],
                 "edge_rank": edge_rank_str,
                 "target_labels": pi['target_labels'],
             }},
            "tab-canvas", False,
        )


def _build_graph_elements(selected_node, include_soft_val, include_synergies_val,
                          global_filters=None, max_depth=None,
                          show_cross_links=True):
    """Shared helper to build Cytoscape elements for the dependency graph."""
    include_soft = bool(include_soft_val and "include" in include_soft_val)
    include_synergies = bool(include_synergies_val and "include" in include_synergies_val)
    global_filters = global_filters or {}

    edge_types = {EDGE_NEEDS_HARD}
    if include_soft:
        edge_types.add(EDGE_NEEDS_SOFT)
    if include_synergies:
        edge_types.add(EDGE_HELPS)

    view = graph_manager.get_dependency_view(
        selected_node,
        include_soft=include_soft,
        include_synergies=include_synergies,
        max_depth=max_depth,
        filters=global_filters,
    )
    node_names = set(view["node_names"])
    discovery_edges = set(view["discovery_edges"])

    styles = canvas_node_styles(graph_manager, event_manager)

    elements = []
    filtered_names = set()
    for name in sorted(node_names):
        node = graph_manager.get_node(name)
        if not node:
            continue
        filtered_names.add(name)
        is_root = node.name == selected_node
        elements.append(build_node_element(
            node, styles,
            # Keep the node this Details view is centered on in Cytoscape's
            # actual selection state. Canvas taps do this implicitly, but
            # dropdown searches and empty-state suggestions create the view
            # without a tap, so the root otherwise misses the shared white
            # `node:selected` outline.
            selected=is_root,
            # Lets the client distinguish a newly selected view from an
            # incremental same-root topology change without depending on
            # Dash's ordering of separate callback outputs.
            extra_data={'details_root': is_root},
        ))

    edges = sorted(
        graph_manager.get_edges(),
        key=lambda edge: (edge['source'], edge['target'], edge['type']))
    for e in edges:
        edge_key = (e['source'], e['target'], e['type'])
        if (e['source'] in filtered_names and e['target'] in filtered_names
                and e['type'] in edge_types
                and (show_cross_links or edge_key in discovery_edges)):
            elements.append(build_edge_element(e))

    return elements
