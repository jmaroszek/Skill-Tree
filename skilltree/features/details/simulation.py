"""The Details tab's Time Simulation: requests, the forecast chart, and the
context menu's Simulate."""
import logging

from dash import ClientsideFunction, Input, Output, State, no_update

from skilltree.domain.models import (
    EDGE_HELPS,
    EDGE_NEEDS_HARD,
    EDGE_NEEDS_SOFT,
    STATUS_DONE,
)
from skilltree.domain.simulation import SimulationCancelled
from skilltree.features.details.layout import normalize_max_depth
from skilltree.features.details.simulation_service import simulation_service
from skilltree.store import database
from skilltree.store.settings import ConfigManager
from skilltree.ui import payloads as bridge_payloads
from skilltree.ui.components.duration import simulation_figure
from skilltree.ui.filters import build_filters


def register_simulation_callbacks(app, services):
    graph = services.graph
    # Browser-generated sequence numbers let both the worker and the chart
    # discard superseded selections, even if responses arrive out of order.
    # Layout-affecting changes first send a node-less request, which shows
    # "Calculating…" and, while an earlier simulation may still be running,
    # cancels it on the server without starting another. The selected node is
    # released only after the newest Cytoscape layout settles. Frozen canvases
    # bypass the gate because they intentionally produce no layout events.
    app.clientside_callback(
        ClientsideFunction(namespace="skillTreeSimulation",
                           function_name="requestAndForward"),
        Output("details-sim-request", "data"),
        Output("details-sim-server-request", "data"),
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
        Input("filter-time-min", "value"),
        Input("filter-search-query", "data"),
        State("details-freeze-rerender-store", "data"),
    )

    @app.callback(Output("details-sim-result", "data"),
                  Input("details-sim-server-request", "data"), prevent_initial_call=True)
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
            f_time_unit=request.get('timeUnit'), f_show_dormant=request.get('dormant'),
            f_time_min=request.get('timeMin'), f_search=request.get('search'))
        if 'hide_blocked' in (request.get('hideBlocked') or []):
            filters['hide_blocked'] = True
        try:
            fig, results_style, empty_style = _run_simulation(
                graph, request['node'], request.get('soft'), request.get('helps'),
                global_filters=filters, max_depth=normalize_max_depth(request.get('depth')),
                should_cancel=cancelled)
            if cancelled():
                return no_update
            if fig is no_update:
                return {**identity, 'error': 'This node is no longer available.'}
            return {**identity, 'figure': fig, 'resultsStyle': results_style,
                    'emptyStyle': empty_style, 'caption': ''}
        except SimulationCancelled:
            return no_update
        except NothingLeft as notice:
            return {**identity, 'notice': str(notice)}
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
        # Parse "nodeName|timestamp"; the name may itself contain "|".
        node_name = bridge_payloads.strip_stamp(trigger_val).strip()
        if not node_name:
            return no_update
        # Select the node — which will auto-run simulation
        return node_name


class NothingLeft(Exception):
    """The node has no unfinished work to simulate. The message says why."""


def _run_simulation(graph, node_name, include_soft_val, include_synergies_val,
                    global_filters=None, max_depth=None, should_cancel=None):
    """Shared helper: run the Monte Carlo simulation and return (figure, style, style).

    Raises NothingLeft when the node and everything it needs are Done: a
    chart of zero hours says nothing a sentence can't.
    """
    include_soft = bool(include_soft_val and "include" in include_soft_val)
    include_helps = bool(include_synergies_val and "include" in include_synergies_val)
    with database.read_snapshot():
        view = graph.get_dependency_view(
            node_name,
            include_soft=include_soft,
            include_synergies=include_helps,
            max_depth=max_depth,
            filters=global_filters,
        )
        allowed = set(view["node_names"])
        nodes_dict = {
            name: graph.get_node(name) for name in allowed
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
            edge for edge in graph.get_edges()
            if edge['type'] in permitted_types
            and edge['source'] in allowed and edge['target'] in allowed
        ]

        requested_trials = ConfigManager.get_monte_carlo_trials()
        time_settings = ConfigManager.get_time_settings()

    # A Done node is finished, whatever is still open before it.
    if nodes_dict[node_name].status == STATUS_DONE:
        raise NothingLeft(f"'{node_name}' is Done, so there is no time left to estimate.")
    result = simulation_service.summarize(
        node_name, nodes_dict, sim_edges, include_soft, include_helps,
        requested_trials, should_cancel=should_cancel)
    # Every run took zero hours: a chart of P10 = P50 = P90 = 0 tells the user
    # nothing. Either the work beneath is all Done, or nothing beneath holds
    # hours at all, like a Milestone over only other Milestones.
    if result['stats']['max'] == 0:
        if any(node.status == STATUS_DONE and not node.has_no_own_work
               for name, node in nodes_dict.items() if name != node_name):
            raise NothingLeft(f"Everything '{node_name}' needs is Done, so there is no "
                              "time left to estimate.")
        raise NothingLeft(f"No work with a time estimate leads into '{node_name}' yet, "
                          "so there is no time to estimate.")

    return (
        simulation_figure(result, time_settings, requested_trials),
        {"display": "flex", "flexDirection": "column", "flex": "1", "minHeight": "0"},
        {"display": "none"},
    )
