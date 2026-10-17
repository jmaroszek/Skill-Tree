"""
Callback definitions for the Details tab.
"""

from skilltree.ui import payloads as bridge_payloads
from skilltree.store import database
import json
from dash import html, Input, Output, State, ALL, ctx, no_update, ClientsideFunction
from skilltree.store import settings
from skilltree.ui.styles import badge_style
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_DONE
from skilltree.features.details.layout import (build_suggestion_row, build_details_suggestions)
from skilltree.ui.prerender import prerendered
from skilltree.features.details.explore import select_explore_goals
from skilltree.ui.canvas.elements import (
    build_node_element, build_edge_element, canvas_node_styles,
)
from skilltree.ui.filters import (
    build_filters, FILTER_INPUTS, FILTER_STATES, filters_from, is_filters_active,
    filter_summary, filter_chip_state, filter_chip_updates,
)
from skilltree.ui.dash_tools import get_trigger_id
from skilltree.ui.components.duration import format_time_friendly
from skilltree.domain.goals import normalize_goal_scores, rank_goals
from skilltree.features.details.subtasks import register_subtask_callbacks
from skilltree.features.details.simulation import register_simulation_callbacks
from skilltree.features.details.explain import register_explain_callbacks
from skilltree.features.details.subtasks import (
    build_milestones_section,
    collect_details_subtasks,
)
from skilltree.features.details.layout import (
    normalize_max_depth,
)


# The node panel's style while a node is selected. The browser applies it as
# soon as the selection changes; select_detail_node restates it.
DETAILS_CONTENT_SHOWN = {"display": "flex", "flexDirection": "column", "flex": "1",
                         "padding": "0 18px", "overflowY": "auto"}


def register_details_callbacks(app, services):
    graph_manager = services.graph

    # --- Populate node dropdown when its underlying data changes ---
    # All tab contents stay mounted, so the initial call hydrates this once;
    # graph/version refreshes keep it current without resending ~42 KB merely
    # because the user opened Details.
    @app.callback(
        Output("details-node-select", "options"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        prevent_initial_call=True,
    )
    @prerendered
    def populate_details_dropdown(_refresh, _version):
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name}
                for n in sorted(nodes, key=lambda n: n.name)]

    # --- Navigation History: push new entries, handle back/forward ---
    # In the browser: it is pure bookkeeping, and as a server callback it was
    # one more request queued behind every selection while the graph waited.
    app.clientside_callback(
        ClientsideFunction(namespace='details_nav', function_name='step'),
        Output("details-nav-history", "data"),
        Output("details-nav-index", "data"),
        Output("btn-details-nav-back", "disabled"),
        Output("btn-details-nav-forward", "disabled"),
        Input("details-selected-node-store", "data"),
        Input("btn-details-nav-back", "n_clicks"),
        Input("btn-details-nav-forward", "n_clicks"),
        Input("details-node-select", "options"),
        State("details-nav-history", "data"),
        State("details-nav-index", "data"),
        prevent_initial_call=True,
    )

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
        Output("details-attr-effort-wrap", "style"),
        # Inputs
        Input("details-node-select", "value"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("details-max-depth", "value"),
        State("details-include-soft-needs", "value"),
        State("details-include-synergies", "value"),
        FILTER_STATES,
        State("details-hide-blocked", "value"),
        # What the store already holds. Most of this callback's Inputs are
        # refresh signals, not selection changes, so the store slot below is
        # left untouched unless the selection actually moved — see the note
        # on `_selection_output`.
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    @database.snapshot_read
    def select_detail_node(node_name, _refresh, _version,
                           max_depth_val, include_soft_val, include_synergies_val,
                           sidebar_filters, hide_blocked_val, current_selection):
        # Dash re-fires every dependent callback when an Output is written,
        # even with an unchanged value. Writing the same node name back on a
        # refresh would look like a fresh selection: the simulation would go
        # back to waiting for a layout settle that a same-root refresh never
        # produces.
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
                {}, {"display": "none"}, "", {},
            )

        node = graph_manager.get_node(node_name)
        if not node:
            return (no_update,) * 25

        include_soft = bool(include_soft_val and "include" in include_soft_val)
        include_synergies = bool(include_synergies_val and "include" in include_synergies_val)
        max_depth = normalize_max_depth(max_depth_val)

        # Build badges. Order: Status → Priority → Type → RelPriority.
        # Goal type tile is suppressed when a Priority N tile is shown
        # (the Priority tile already implies "this is a Goal").
        badges = []
        priority_goals = settings.PRIORITY_GOALS.get()
        is_priority_goal = node_name in priority_goals

        # 1. Status (always)
        badges.append(html.Span(node.status, className="badge",
                                style=badge_style(node.status)))

        # 2b. Now (if currently being worked on). Uses the same
        # configurable color as the canvas border encoding.
        if node.now:
            badges.append(html.Span("Now", className="badge",
                                    style=badge_style('Now')))

        # 2. Priority (Priority N for priority Goals)
        if is_priority_goal:
            rank = priority_goals.index(node_name) + 1
            badges.append(html.Span(f"Priority {rank}", className="badge",
                                    style=badge_style('Priority')))

        # 3. Type (skip Goal when Priority N already rendered above)
        if node.type and not is_priority_goal:
            badges.append(html.Span(node.type, className="badge",
                                    style=badge_style(node.type)))

        # 4. Relationship Priority (Hard/Soft N for non-priority nodes in a priority Goal's subtree)
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
        time_str = format_time_friendly(effective_time) if effective_time else "—"

        # Ratings display: when a node's ratings are inherited (containers and
        # Milestones), its stored value/interest are scoring-inert, so
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
                show_progress = {"display": "block"}
                progress_val = completion["pct"]
                remaining = format_time_friendly(
                    completion["remaining_time"])
                # Milestone count: walk the same hard-subtree the completion
                # walked, count Milestones in it. Filter-independent, like
                # the percent beside it.
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
                # The bar and its percent weigh each node by its estimate.
                parts = [f"{completion['pct']}% done"]
                if ms_total > 0:
                    parts.append(f"{ms_done}/{ms_total} {ms_label}")
                parts.append(f"{remaining} remaining")
                #   (nbsp) sits next to the regular space so it doesn't
                # collapse — gives a visibly wider gap on each side of the
                # middle dot than a plain " · " would.
                progress_text = "  ·  ".join(parts)

        show_priority = {"display": "none"}
        priority_badge = ""

        # Subtasks use the same filter-aware dependency view as the graph and
        # simulation, so a hidden bridge cannot leave orphaned descendants.
        global_filters = filters_from(sidebar_filters)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        subtask_nodes, edges = collect_details_subtasks(
            graph_manager, node_name, include_soft, include_synergies, max_depth,
            global_filters)

        # Milestones roster — derived from the same filtered subtask_nodes the
        # Subtasks table uses, so the strip stays in lockstep with the table.
        ms_section_style, bottom_toggles_style, ms_tiles = build_milestones_section(
            graph_manager, subtask_nodes, node_name, edges)

        return (
            {"display": "none"},
            DETAILS_CONTENT_SHOWN,
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
            {"display": "none"} if node.has_no_own_work else {},
        )


    # A frozen canvas starts no layout, so nothing would release a new
    # selection's table. Send the settle signal once the selection lands.
    app.clientside_callback(
        """
        function(node, frozen) {
            if (!node || !frozen) return;
            window.dash_clientside.set_props('details-layout-settled-trigger-input', {
                value: JSON.stringify({root: node, settledAt: Date.now()})
            });
        }
        """,
        Input("details-selected-node-store", "data"),
        State("details-freeze-rerender-store", "data"),
        prevent_initial_call=True,
    )


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
    # It reads the dropdown, not details-selected-node-store, so its request
    # goes out with select_detail_node's instead of after that callback's
    # 24 outputs have been applied. The graph is the opening animation's
    # critical path; the panel can fill in around it.
    @app.callback(
        Output("details-elements-pending-store", "data"),
        Input("details-node-select", "value"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("details-include-soft-needs", "value"),
        Input("details-include-synergies", "value"),
        Input("details-max-depth", "value"),
        Input("details-show-cross-links", "value"),
        FILTER_INPUTS,
        Input("details-hide-blocked", "value"),
    )
    @database.snapshot_read
    def update_details_graph(selected_node, _refresh, _version,
                             include_soft_val, include_synergies_val,
                             max_depth_val, show_cross_links_val,
                             sidebar_filters, hide_blocked_val):
        if not selected_node:
            return []
        # select_detail_node keeps the previous view for a name that no
        # longer exists, so this keeps its graph too.
        if not graph_manager.get_node(selected_node):
            return no_update
        global_filters = filters_from(sidebar_filters)
        if hide_blocked_val and "hide_blocked" in hide_blocked_val:
            global_filters['hide_blocked'] = True
        return _build_graph_elements(graph_manager, services.events,
                                     selected_node, include_soft_val,
                                     include_synergies_val, global_filters,
                                     max_depth=normalize_max_depth(max_depth_val),
                                     show_cross_links=bool(
                                         show_cross_links_val
                                         and "show" in show_cross_links_val))

    # --- Clicking a node in the dep graph → select it ---
    # In the browser: a server round trip here only delayed the graph's
    # opening animation by one more request.
    app.clientside_callback(
        """
        function(tapData, activeTab) {
            // A click with Ctrl, Cmd or Shift held picks nodes (context_menu.js);
            // moving the view would drop the ones already picked.
            if (activeTab !== 'tab-details' || !tapData || tapData.id == null
                    || (window.SkillTree && window.SkillTree.additiveTap)) {
                return window.dash_clientside.no_update;
            }
            return tapData.id;
        }
        """,
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-mini-graph", "tapNodeData"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )


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
        Input({"type": "details-subtask-edit", "index": ALL}, "n_clicks"),
        State("details-selected-node-store", "data"),
        prevent_initial_call=True,
    )
    def details_edit_node(n_clicks, subtask_clicks, selected_node):
        triggered = ctx.triggered_id
        if isinstance(triggered, dict):
            if not any(subtask_clicks or []):
                return no_update
            node_name = triggered.get("index")
        else:
            # Re-rendering the subtask list re-fires this callback with no
            # real trigger. Without this check, the Edit button's stale
            # n_clicks reopened the editor on every node selection.
            if triggered != "btn-details-edit" or not n_clicks:
                return no_update
            node_name = selected_node
        if not node_name:
            return no_update
        import time
        return f"{node_name}|{time.time_ns()}"


    # --- Context Menu "View Details" → Navigate to Details tab with node selected ---
    @app.callback(
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Output("details-node-select", "value", allow_duplicate=True),
        Input("details-navigate-trigger-input", "value"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def context_menu_details_navigate(trigger_val, active_tab):
        if not trigger_val:
            return no_update, no_update
        node_name = bridge_payloads.strip_stamp(trigger_val).strip()
        if not node_name:
            return no_update, no_update
        # Re-sending the current tab would re-run everything keyed on it.
        next_tab = "tab-details" if active_tab != "tab-details" else no_update
        return next_tab, node_name


    # --- Empty-state starting points: priority goals + top-ranked goals ---
    @app.callback(
        Output("details-suggestions-container", "children"),
        Input("details-refresh-trigger", "data"),
        Input("graph-version-store", "data"),
        Input("filter-context", "value"),
        Input("filter-subcontext", "value"),
        Input("filter-done", "value"),
        Input("filter-value", "value"),
        Input("filter-interest", "value"),
        Input("filter-time", "value"),
        Input("filter-time-unit", "value"),
        Input("filter-difficulty", "value"),
        Input("filter-node-type", "value"),
        Input("filter-dormant", "value"),
        Input("settings-save-status", "children"),
        Input("filter-time-min", "value"),
        Input("filter-search-query", "data"),
        prevent_initial_call=True,
    )
    @prerendered
    @database.snapshot_read
    def build_empty_state_suggestions(
            _refresh, _version, f_context, f_subcontext, f_done,
            f_value, f_interest, f_time, f_time_unit, f_difficulty,
            f_node_types, f_show_dormant, _settings, f_time_min, f_search):
        # Priority Goals are explicit pins, so filters do not hide them. The
        # Explore section below is discovery-oriented and does honor the
        # active global filters.
        all_nodes = graph_manager.get_all_nodes()
        edges = graph_manager.get_edges()
        priority_goals = settings.PRIORITY_GOALS.get()
        nodes_by_name = {node.name: node for node in all_nodes}
        priority_names = []
        goal_rows = []
        seen = set()
        for rank, goal_name in enumerate(priority_goals[:3], start=1):
            if goal_name in seen:
                continue
            goal_node = nodes_by_name.get(goal_name)
            if not goal_node or goal_node.status == STATUS_DONE:
                continue
            goal_rows.append(build_suggestion_row(
                goal_node, priority_rank=rank))
            priority_names.append(goal_name)
            seen.add(goal_name)

        global_filters = build_filters(
            f_context, f_subcontext, f_done, f_value, f_interest, f_time,
            f_difficulty, f_node_types, f_time_unit=f_time_unit,
            f_show_dormant=f_show_dormant, f_time_min=f_time_min,
            f_search=f_search)
        eligible_names = {
            node.name for node in graph_manager.filter_nodes(
                all_nodes, global_filters)
        }
        # Explore follows the Goals sidebar's Priority ranking and shows the
        # same 0-100 number, so a Goal reads the same on both surfaces. The
        # number keeps its app-wide base when filters narrow the list.
        ranked = rank_goals(
            [node for node in all_nodes if node.type == "Goal"], all_nodes,
            edges, priority_goals, settings.hyperparams(),
            context_weights=settings.CONTEXT_WEIGHTS.get(),
            with_scores=True)
        priorities = normalize_goal_scores(ranked, all_nodes, edges)
        explore = select_explore_goals(
            [goal for goal, _ in ranked if goal.name in priorities],
            all_nodes, edges, count=5, candidate_names=eligible_names,
            seed_names=priority_names,
        )
        explore_rows = [
            build_suggestion_row(goal, priority=priorities[goal.name])
            for goal in explore
        ]
        filters_active = is_filters_active(
            node_type=f_node_types, context=f_context,
            subcontext=f_subcontext, value=f_value, interest=f_interest,
            difficulty=f_difficulty, time=f_time, time_min=f_time_min,
            search=f_search,
        )
        return build_details_suggestions(
            goal_rows, explore_rows, filters_active=filters_active)

    # --- Suggestion Click → Select that node in Details ---
    # In the browser, for the same reason as a graph tap.
    app.clientside_callback(
        """
        function(clicks, activeTab) {
            var no = window.dash_clientside.no_update;
            if (activeTab !== 'tab-details' || !(clicks || []).some(Boolean)) return no;
            var context = window.dash_clientside.callback_context;
            var triggered = context && context.triggered_id;
            return triggered && triggered.index != null ? triggered.index : no;
        }
        """,
        Output("details-node-select", "value", allow_duplicate=True),
        Input({"type": "details-suggestion-item", "index": ALL}, "n_clicks"),
        State("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )


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
        gl = settings.DETAILS_GRAPH_LAYOUT_DEFAULTS.get()
        return (
            True,
            gl.get('edge_length', 50),
            gl.get('gravity', 0.25),
            gl.get('repulsion', 4500),
            False,
        )

    # --- Details Tab: Filter Chip ---
    # The Details canvas honors the global Context/Subcontext/Type/Done/
    # ratings/time filters but ignores Goal and Community (those only narrow
    # the main canvas), so the chip only lists the filters that actually
    # affect the subtree being rendered here. Show Done is not among them —
    # see is_filters_active on why a reveal is not a filter.
    @app.callback(
        Output('details-filter-chip-text', 'children'),
        Output('details-filter-chip', 'title'),
        Output('details-filter-chip', 'hidden'),
        Input('filter-node-type', 'value'),
        Input('filter-context', 'value'),
        Input('filter-subcontext', 'value'),
        Input('filter-value', 'value'),
        Input('filter-interest', 'value'),
        Input('filter-difficulty', 'value'),
        Input('filter-time', 'value'),
        Input('filter-time-min', 'value'),
        Input('filter-search-query', 'data'),
        Input('filter-time-unit', 'value'),
        State('details-filter-chip-text', 'children'),
        State('details-filter-chip', 'title'),
        State('details-filter-chip', 'hidden'),
        prevent_initial_call=True,
    )
    @prerendered
    def update_details_filter_chip(f_type, f_ctx, f_sub, f_val, f_int,
                                   f_diff, f_time, f_time_min, f_search,
                                   f_time_unit, chip_text, chip_title,
                                   chip_class):
        # The depth limit is a graph setting, not a filter: Clear Filters
        # leaves it, so the chip leaves it out and the node count shows it.
        shared = dict(node_type=f_type, context=f_ctx, subcontext=f_sub,
                      value=f_val, interest=f_int, difficulty=f_diff,
                      time=f_time, time_min=f_time_min, search=f_search)
        chip = filter_chip_state(filter_summary(time_unit=f_time_unit, **shared))
        return filter_chip_updates(chip, (chip_text, chip_title, chip_class))

    # --- Details Tab: Node Count Canvas Overlay ---
    # The count itself is read in the browser from the payload on its way to
    # Cytoscape. Reading it from the canvas's elements sent the whole graph to
    # the server twice per selection, once for the payload and once for
    # dash-cytoscape's positional echo, both inside the opening animation.
    # A depth limit is named after it, since the filter chip leaves it out;
    # the slider's 6 means All, as in normalize_max_depth.
    app.clientside_callback(
        """
        function(pending, maxDepth) {
            if (!Array.isArray(pending)) return window.dash_clientside.no_update;
            var n = 0;
            for (var i = 0; i < pending.length; i++) {
                var data = pending[i] && pending[i].data;
                if (data && data.source === undefined) n += 1;
            }
            var text = n + (n === 1 ? ' node' : ' nodes');
            return maxDepth && maxDepth !== 6 ? text + ' · depth ' + maxDepth : text;
        }
        """,
        Output('details-canvas-node-count', 'children'),
        Input('details-elements-pending-store', 'data'),
        State('details-max-depth', 'value'),
        prevent_initial_call=True,
    )

    # --- Details Graph Layout: layout requests ---
    # Registered with every canvas's in callbacks.py; built by
    # assets/canvas/layout_requests.js.

    # Time Simulation waits for the layout a filter change causes. A change
    # that leaves this subtree's nodes and edges as they were (a context with
    # no nodes here) starts no layout, so that wait would never end. This
    # sends the settle signal itself whenever a payload will not be laid out.
    # It writes with set_props rather than an Output, so the simulation's
    # request doesn't wait on this payload; see releaseUnchanged.
    app.clientside_callback(
        ClientsideFunction(
            namespace="skillTreeLayout", function_name="releaseUnchanged"),
        Input('details-elements-pending-store', 'data'),
        State('details-freeze-rerender-store', 'data'),
        State('details-selected-node-store', 'data'),
        prevent_initial_call=True,
    )


    # Both Explain callbacks run only while the modal is open. They used to
    # take the selection directly and return nothing while closed, which
    # still made two server round trips on every selection, just as the
    # Details graph started its opening animation.
    #
    # The same browser callback reveals the panel as soon as there is a
    # selection. The graph's payload can now arrive before
    # select_detail_node's answer, and a layout run in the hidden panel
    # would animate at a zero size.
    #
    # It also replaces the previous subtasks table with its placeholder, so
    # that unmount happens while the graph's request is out, not in the
    # layout's first frames. The swap waits a task so the requests leave
    # first. render_details_subtasks fills the table once the layout
    # settles. A frozen canvas runs no layout, so the server renders its
    # table at once, and a selection that didn't move keeps its table:
    # nothing would settle to replace the placeholder. A cleared selection
    # gets the no-selection message, as before the table stopped listening
    # to the selection.
    app.clientside_callback(
        """
        function(node, isOpen, current, frozen, options) {
            var no = window.dash_clientside.no_update;
            var known = (options || []).some(function (option) {
                return option && option.value === node;
            });
            var props = null;
            if (!node) {
                props = {children: 'Select a node to see subtasks.'};
            } else if (known && node !== current && !frozen) {
                props = {children: 'Loading subtasks…', role: 'status'};
            }
            if (props) {
                props.className = 'text-muted text-center py-3';
                setTimeout(function () {
                    window.dash_clientside.set_props('details-subtasks-table-container', {
                        children: {namespace: 'dash_html_components', type: 'Div', props: props}
                    });
                }, 0);
            }
            return [
                node ? {display: 'none'} : {display: 'block'},
                node ? __SHOWN__ : {display: 'none'},
                isOpen ? node : no
            ];
        }
        """.replace("__SHOWN__", json.dumps(DETAILS_CONTENT_SHOWN)),
        Output("details-empty", "style", allow_duplicate=True),
        Output("details-content", "style", allow_duplicate=True),
        Output("details-explain-node", "data"),
        Input("details-node-select", "value"),
        State("modal-details-explain", "is_open"),
        State("details-selected-node-store", "data"),
        State("details-freeze-rerender-store", "data"),
        State("details-node-select", "options"),
        prevent_initial_call=True,
    )

    register_subtask_callbacks(app, services)
    register_simulation_callbacks(app, services)
    register_explain_callbacks(app, services)


def _build_graph_elements(graph, events, selected_node, include_soft_val,
                          include_synergies_val, global_filters=None, max_depth=None,
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

    view = graph.get_dependency_view(
        selected_node,
        include_soft=include_soft,
        include_synergies=include_synergies,
        max_depth=max_depth,
        filters=global_filters,
    )
    node_names = set(view["node_names"])
    discovery_edges = set(view["discovery_edges"])

    styles = canvas_node_styles(events)

    elements = []
    filtered_names = set()
    for name in sorted(node_names):
        node = graph.get_node(name)
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
        graph.get_edges(),
        key=lambda edge: (edge['source'], edge['target'], edge['type']))
    for e in edges:
        edge_key = (e['source'], e['target'], e['type'])
        if (e['source'] in filtered_names and e['target'] in filtered_names
                and e['type'] in edge_types
                and (show_cross_links or edge_key in discovery_edges)):
            elements.append(build_edge_element(e))

    return elements
