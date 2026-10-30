"""The Graph Layout panel every canvas has, and its freeze indicator."""
from dash import dcc
from dash import html
from skilltree.store import settings
from skilltree.ui import tokens
from skilltree.ui.kit import Tooltip
from skilltree.ui.kit import panel_close_button
from skilltree.ui.kit import restore_button
import dash_bootstrap_components as dbc


def freeze_indicator(indicator_id: str):
    """Snowflake overlay shown on a canvas while its freeze toggle is on.

    Hidden by default; a clientside callback flips display + keeps the style
    in sync with the freeze-rerender store. Centered horizontally with the
    tab bar's Filters button (`right: 19px` with a 1.6rem icon).
    """
    return html.I(
        className="bi bi-snow",
        id=indicator_id,
        style={
            "display": "none",
            "position": "absolute",
            "top": "12px",
            "right": "19px",
            "fontSize": tokens.FS_HEADING,
            "color": tokens.ACCENT_SOFT,
            "textShadow": "0 0 6px rgba(126, 200, 227, 0.5)",
            "pointerEvents": "none",
            "zIndex": 10,
        },
    )


def build_graph_settings_panel(
    prefix: str,
    *,
    include_animate: bool = True,
    defaults_getter=settings.GRAPH_LAYOUT_DEFAULTS.get,
    max_depth_id: str = None,
    direction_id: str = None,
    outside_nodes_id: str = None,
):
    """Build a graph-layout panel. Single source of truth for all three canvases
    (Nodes / Details / Events).

    Callers pass the slider `defaults_getter` explicitly: the `get` of
    `settings.GRAPH_LAYOUT_DEFAULTS` (main canvas),
    `DETAILS_GRAPH_LAYOUT_DEFAULTS` or `EVENTS_GRAPH_LAYOUT_DEFAULTS`. Pass
    ``include_animate=False`` to render only Freeze in the behavior row.

    ``max_depth_id`` opts a canvas into a Max Depth slider at the top of the
    panel. Only the Details tab passes it, since that's the only canvas that
    examines a local subtree rather than the whole graph. The id is supplied by
    the caller rather than derived from ``prefix`` on purpose: depth is a
    tab-level control that also redraws the subtasks table, milestones strip,
    inherited ratings and Time Simulation, so it keeps the tab-scoped
    ``details-max-depth`` name instead of a panel-scoped one. It sits above a
    divider, separated from the physics sliders below it.

    ``direction_id`` adds a Direction choice just above Max Depth, for the
    same tab and the same reason: Needs walks to what leads into the node,
    Supports to what it leads to.

    ``outside_nodes_id`` is the Events canvas's counterpart: a switch that
    shows or hides nodes outside the event that link to its nodes. It is
    remembered in the browser between sessions.
    """
    gl = defaults_getter()
    p = prefix
    reset_btn_id = f"btn-reset-{p}"
    close_btn_id = f"btn-close-{p}"

    children = [
        html.Div([
            html.Div([
                html.Span("Graph Layout", style={"fontWeight": "300", "fontSize": tokens.FS_LG}),
                restore_button(reset_btn_id),
            ], className="d-flex align-items-center"),
            panel_close_button(close_btn_id, "Close graph layout panel"),
        ], className="d-flex justify-content-between align-items-center",
           style={"marginBottom": tokens.SPACE_BLOCK}),
    ]

    children += [
        html.Div([
            *([
                dbc.Switch(
                    id=f"{p}-animate",
                    label="Animate",
                    value=True,
                    style={"fontSize": tokens.FS_BASE},
                ),
            ] if include_animate else []),
            dbc.Switch(
                id=f"{p}-freeze-rerender",
                label="Freeze",
                value=False,
                style={"fontSize": tokens.FS_BASE},
            ),
        # 1rem, the same gap Bootstrap leaves between inline radios, so this
        # row and Direction below it are spaced alike.
        ], className="d-flex gap-3"),
        Tooltip("Keep the layout still when you save. Settle redraws it.",
                    target=f"{p}-freeze-rerender", placement="left"),
        html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),
    ]

    # Scope, not physics — so it leads the panel and gets its own divider
    # rather than sitting among the force-layout sliders.
    if outside_nodes_id:
        children += [
            dbc.Switch(
                id=outside_nodes_id,
                label="Nodes outside event",
                value=True,
                persistence=True,
                persistence_type="local",
                style={"fontSize": tokens.FS_BASE},
            ),
            html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),
        ]

    if direction_id:
        children += [
            html.Div("Direction", className="settings-label"),
            dbc.RadioItems(
                id=direction_id,
                options=[{"label": "Needs", "value": "needs"},
                         {"label": "Supports", "value": "supports"}],
                value="needs",
                inline=True,
                style={"fontSize": tokens.FS_BASE},
            ),
            Tooltip("Needs shows what leads into this node. Supports shows "
                    "what it leads to.", target=direction_id, placement="left"),
        ]

    if max_depth_id:
        children += [
            html.Div("Max Depth", className="settings-label"),
            dcc.Slider(
                id=max_depth_id,
                min=1, max=6, step=1, value=6,
                marks={1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "All"},
                updatemode="mouseup",
            ),
            html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),
        ]

    children += [
        html.Div("Edge Length", className="settings-label"),
        dcc.Slider(
            id=f"{p}-edge-length",
            min=50, max=300, step=10, value=gl.get('edge_length', 100),
            marks=None,
            updatemode="mouseup",
        ),
        html.Div([
            html.Span("Short"),
            html.Span("Long"),
        ], id=f"{p}-edge-length-axis", className="graph-settings-axis"),

        html.Div("Gravity", className="settings-label"),
        dcc.Slider(
            id=f"{p}-gravity",
            min=0, max=5, step=0.25, value=gl.get('gravity', 0.25),
            marks=None,
            updatemode="mouseup",
        ),
        html.Div([
            html.Span("Weak"),
            html.Span("Strong"),
        ], id=f"{p}-gravity-axis", className="graph-settings-axis"),

        html.Div("Repulsion", className="settings-label"),
        dcc.Slider(
            id=f"{p}-repulsion",
            min=500, max=100000, step=500, value=gl.get('repulsion', 4500),
            marks=None,
            updatemode="mouseup",
        ),
        html.Div([
            html.Span("Weak"),
            html.Span("Strong"),
        ], id=f"{p}-repulsion-axis", className="graph-settings-axis"),
    ]

    children += [
        html.Hr(style={"borderColor": tokens.BORDER_PANEL, "margin": "12px 0"}),

        dbc.Button("Settle", id=f"{p}-relayout",
                   color="secondary", size="sm", className="w-100 mt-2"),
        Tooltip("Re-run layout physics to untangle nodes",
                    target=f"{p}-relayout", placement="top"),
    ]

    return html.Div(children, id=f"{p}-panel", className="graph-settings-panel",
                    style={"display": "none"})
