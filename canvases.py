"""The Cytoscape canvases, listed once.

The Nodes, Details and Events tabs each render the graph in their own
Cytoscape component. Behavior every canvas shares loops over this list instead
of naming the canvases again. In Python that is the hover tooltip, the freeze
wiring and the layout requests. In assets/ it is the tooltip binding, freeze,
fullscreen, scroll zoom, right-click pan, the node context menu, the Now pulse
and the layout requests.
"""

import json
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Canvas:
    # Short name assets/ uses for the canvas: its freeze state, its layout
    # policy and its context-menu source.
    key: str
    cytoscape_id: str
    # The wrapper that goes fullscreen and carries the frozen outline.
    container_id: str
    fullscreen_button_id: str
    # Callbacks write element lists here. The freeze wiring forwards them to
    # Cytoscape, or applies them in place while the canvas is frozen.
    pending_store_id: str
    freeze_store_id: str
    freeze_indicator_id: str
    # The prefix build_graph_settings_panel gave this canvas's Graph Layout
    # controls. See control_id().
    settings_prefix: str
    # Details and Events lay out their own element updates, which lets them
    # tell a real topology change from dash-cytoscape's positional echo. Nodes
    # leaves element updates to dash-cytoscape's autoRefreshLayout.
    lays_out_elements: bool
    # The store naming the view the elements belong to, if the canvas has
    # one: the Details root or the selected event.
    view_store_id: Optional[str] = None

    def control_id(self, control):
        """A Graph Layout control, such as 'edge-length' or 'freeze-rerender'."""
        return f'{self.settings_prefix}-{control}'


CANVASES = (
    Canvas(
        key='main',
        cytoscape_id='cytoscape-graph',
        container_id='canvas-container',
        fullscreen_button_id='btn-fullscreen',
        pending_store_id='elements-pending-store',
        freeze_store_id='freeze-rerender-store',
        freeze_indicator_id='freeze-indicator',
        settings_prefix='graph-settings',
        lays_out_elements=False,
    ),
    Canvas(
        key='details',
        cytoscape_id='details-mini-graph',
        container_id='details-dep-graph-container',
        fullscreen_button_id='btn-details-graph-fullscreen',
        pending_store_id='details-elements-pending-store',
        freeze_store_id='details-freeze-rerender-store',
        freeze_indicator_id='details-freeze-indicator',
        settings_prefix='details-graph-settings',
        lays_out_elements=True,
        view_store_id='details-selected-node-store',
    ),
    Canvas(
        key='events',
        cytoscape_id='events-detail-graph',
        container_id='events-detail-graph-container',
        fullscreen_button_id='btn-events-graph-fullscreen',
        pending_store_id='events-elements-pending-store',
        freeze_store_id='events-freeze-rerender-store',
        freeze_indicator_id='events-freeze-indicator',
        settings_prefix='events-graph-settings',
        lays_out_elements=True,
        view_store_id='selected-event-store',
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
            'freezeStoreId': canvas.freeze_store_id,
            'settleButtonId': canvas.control_id('relayout'),
            'laysOutElements': canvas.lays_out_elements,
        }
        for canvas in CANVASES
    ]


def install_client_registry(app):
    """Give the page ``window.SkillTree.canvases`` before any asset script runs.

    Several assets read the list as soon as they load. freeze_positions.js
    registers each canvas, now_pulse.js starts scanning them, and
    layout_requests.js defines each canvas's layout request. That is before
    Dash renders any layout, so the list can't wait in a data attribute. It
    goes in an inline script ahead of Dash's own script tags instead.
    """
    payload = json.dumps(client_registry()).replace('</', '<\\/')
    script = ('<script>window.SkillTree = window.SkillTree || {}; '
              f'window.SkillTree.canvases = {payload};</script>')
    app.index_string = app.index_string.replace(
        '{%scripts%}', script + '\n            {%scripts%}', 1)
