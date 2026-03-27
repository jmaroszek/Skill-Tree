"""
Callback definitions for the Simulation tab.
"""

from dash import html, Input, Output, State, ALL, ctx, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from graph_manager import GraphManager
from simulation import simulate_task_chain

graph_manager = GraphManager()


def register_simulate_callbacks(app):

    # --- Populate node dropdown when tab becomes active ---
    @app.callback(
        Output("sim-node-select", "options"),
        Input("main-tabs", "active_tab"),
    )
    def populate_node_dropdown(active_tab):
        if active_tab != "tab-simulate":
            return no_update
        nodes = graph_manager.get_all_nodes()
        return [{"label": n.name, "value": n.name} for n in sorted(nodes, key=lambda n: n.name)]

    # --- Context menu → Simulate trigger ---
    @app.callback(
        Output("sim-node-select", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Output("btn-run-sim", "n_clicks", allow_duplicate=True),
        Input("simulate-trigger-input", "value"),
        prevent_initial_call=True,
    )
    def trigger_simulate_from_context(trigger_value):
        if not trigger_value:
            return no_update, no_update, no_update
        # Parse "nodeName|timestamp"
        node_name = trigger_value.rsplit('|', 1)[0]
        if not node_name:
            return no_update, no_update, no_update
        # Set the dropdown, switch to simulate tab, and trigger the run button
        return node_name, "tab-simulate", 1

    # --- Run Monte Carlo simulation ---
    @app.callback(
        Output("sim-chart", "figure"),
        Output("sim-stats", "children"),
        Output("sim-chain-list", "children"),
        Output("sim-results-container", "style"),
        Output("sim-empty", "style"),
        Output("sim-title", "children"),
        Input("btn-run-sim", "n_clicks"),
        State("sim-node-select", "value"),
        State("sim-include-soft", "value"),
        State("sim-include-helps", "value"),
        prevent_initial_call=True,
    )
    def run_simulation(n_clicks, node_name, include_soft, include_helps):
        if not n_clicks or not node_name:
            return no_update, no_update, no_update, no_update, no_update, no_update

        # Build nodes dict and edges
        all_nodes = graph_manager.get_all_nodes()
        nodes_dict = {n.name: n for n in all_nodes}
        edges = graph_manager.get_edges()

        if node_name not in nodes_dict:
            return no_update, no_update, no_update, no_update, no_update, no_update

        # Run simulation
        result = simulate_task_chain(
            target_name=node_name,
            nodes_dict=nodes_dict,
            edges=edges,
            include_soft=bool(include_soft),
            include_helps=bool(include_helps),
            n_simulations=10000,
        )

        samples = result['samples']
        stats = result['stats']
        chain_nodes = result['chain_nodes']

        # --- Build histogram figure ---
        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=samples,
            nbinsx=50,
            marker_color='#0d6efd',
            opacity=0.85,
        ))

        # Percentile lines
        for label, val, color in [
            ('P10', stats['p10'], '#198754'),
            ('P50', stats['p50'], '#ffc107'),
            ('P90', stats['p90'], '#dc3545'),
        ]:
            fig.add_vline(
                x=val, line_dash="dash", line_color=color, line_width=2,
                annotation_text=f"{label}: {int(round(val))}h",
                annotation_position="top",
                annotation_font_color=color,
            )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor='#1a1d21',
            plot_bgcolor='#1a1d21',
            margin=dict(l=50, r=30, t=40, b=50),
            xaxis_title="Hours",
            yaxis_title="Frequency",
            showlegend=False,
        )

        # --- Stats row ---
        stats_children = html.Div([
            _stat_card("P10", f"{int(round(stats['p10']))}h", "success"),
            _stat_card("P25", f"{int(round(stats['p25']))}h", "success"),
            _stat_card("P50", f"{int(round(stats['p50']))}h", "warning"),
            _stat_card("P75", f"{int(round(stats['p75']))}h", "danger"),
            _stat_card("P90", f"{int(round(stats['p90']))}h", "danger"),
            _stat_card("Mean", f"{int(round(stats['mean']))}h", "info"),
            _stat_card("Std Dev", f"{int(round(stats['std']))}h", "secondary"),
        ], className="d-flex gap-3 flex-wrap")

        # --- Chain node list ---
        if chain_nodes:
            chain_items = []
            for name in chain_nodes:
                node = nodes_dict.get(name)
                if node:
                    status_color = {"Done": "success", "Blocked": "danger", "Open": "primary"}.get(node.status, "secondary")
                    time_str = f"{round(node.time)}h" if node.time else "1h"
                    chain_items.append(
                        html.Div([
                            html.Span(name, id={"type": "sim-chain-node", "index": name},
                                      style={"flex": "1", "cursor": "pointer", "textDecoration": "underline",
                                             "textDecorationColor": "#495057"}),
                            dbc.Badge(node.status, color=status_color,
                                      style={"fontSize": "0.7rem", "width": "55px", "textAlign": "center"}),
                            html.Small(time_str, className="text-muted ms-2",
                                       style={"width": "45px", "textAlign": "right"}),
                        ], className="d-flex align-items-center py-1",
                           style={"fontSize": "0.82rem", "borderBottom": "1px solid #343a40"})
                    )
            chain_content = html.Div([
                html.H6(f"Chain ({len(chain_nodes)} nodes)", className="mb-2 mt-2"),
                html.Div(chain_items, style={"maxHeight": "300px", "overflowY": "auto"}),
            ])
        else:
            chain_content = html.Div(
                html.P("All tasks in chain are complete.", className="text-muted mt-3"),
            )

        title = f"Time Distribution — {node_name}"

        return (
            fig,
            stats_children,
            chain_content,
            {"display": "block"},   # show results
            {"display": "none"},    # hide empty
            title,
        )

    # --- Chain node name click → Navigate to Canvas ---
    @app.callback(
        Output("search-node", "value", allow_duplicate=True),
        Output("main-tabs", "active_tab", allow_duplicate=True),
        Input({"type": "sim-chain-node", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def navigate_to_chain_node(n_clicks_list):
        if not any(n_clicks_list):
            return no_update, no_update
        triggered = ctx.triggered_id
        if not triggered:
            return no_update, no_update
        return triggered["index"], "tab-canvas"


def _stat_card(label: str, value: str, color: str):
    """Build a small stat display card."""
    return html.Div([
        html.Small(label, className=f"text-{color}", style={"fontSize": "0.75rem"}),
        html.Br(),
        html.Strong(value, style={"fontSize": "0.95rem"}),
    ], className="text-center", style={
        "backgroundColor": "#2b3035",
        "borderRadius": "6px",
        "padding": "8px 14px",
        "minWidth": "70px",
    })
