"""The Cytoscape canvases, listed once.

The Nodes, Details and Events tabs each render the graph in their own
Cytoscape component. Behavior every canvas shares loops over this list instead
of naming the canvases again. In Python that is the hover tooltip and the
freeze wiring. In assets/ it is the tooltip binding, freeze, fullscreen, scroll
zoom, right-click pan, the node context menu and the Now pulse.
"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Canvas:
    # Short name assets/ uses for the canvas: its freeze state and its
    # context-menu source.
    key: str
    cytoscape_id: str
    # The wrapper that goes fullscreen and carries the frozen outline.
    container_id: str
    fullscreen_button_id: str
    # Callbacks write element lists here. The freeze wiring forwards them to
    # Cytoscape, or applies them in place while the canvas is frozen.
    pending_store_id: str
    freeze_switch_id: str
    freeze_store_id: str
    freeze_indicator_id: str


CANVASES = (
    Canvas(
        key='main',
        cytoscape_id='cytoscape-graph',
        container_id='canvas-container',
        fullscreen_button_id='btn-fullscreen',
        pending_store_id='elements-pending-store',
        freeze_switch_id='graph-settings-freeze-rerender',
        freeze_store_id='freeze-rerender-store',
        freeze_indicator_id='freeze-indicator',
    ),
    Canvas(
        key='details',
        cytoscape_id='details-mini-graph',
        container_id='details-dep-graph-container',
        fullscreen_button_id='btn-details-graph-fullscreen',
        pending_store_id='details-elements-pending-store',
        freeze_switch_id='details-graph-settings-freeze-rerender',
        freeze_store_id='details-freeze-rerender-store',
        freeze_indicator_id='details-freeze-indicator',
    ),
    Canvas(
        key='events',
        cytoscape_id='events-detail-graph',
        container_id='events-detail-graph-container',
        fullscreen_button_id='btn-events-graph-fullscreen',
        pending_store_id='events-elements-pending-store',
        freeze_switch_id='events-graph-settings-freeze-rerender',
        freeze_store_id='events-freeze-rerender-store',
        freeze_indicator_id='events-freeze-indicator',
    ),
)


def client_registry():
    """The fields assets/ reads for each canvas, in ``CANVASES`` order."""
    return [
        {
            'key': canvas.key,
            'cytoscapeId': canvas.cytoscape_id,
            'containerId': canvas.container_id,
            'fullscreenButtonId': canvas.fullscreen_button_id,
        }
        for canvas in CANVASES
    ]


def install_client_registry(app):
    """Give the page ``window.SkillTree.canvases`` before any asset script runs.

    freeze_positions.js registers each canvas, and now_pulse.js starts
    scanning them, as soon as they load. That is before Dash renders any
    layout, so the list can't wait in a data attribute. It goes in an inline
    script ahead of Dash's own script tags instead.
    """
    payload = json.dumps(client_registry()).replace('</', '<\\/')
    script = ('<script>window.SkillTree = window.SkillTree || {}; '
              f'window.SkillTree.canvases = {payload};</script>')
    app.index_string = app.index_string.replace(
        '{%scripts%}', script + '\n            {%scripts%}', 1)
