"""
Shared Cytoscape stylesheet definitions for Cytoscape graph components.
"""

# Badge for nodes whose completion triggers an event: a gold lightning bolt in
# a dark circle. Served from assets/ — Dash exposes this at /assets/ automatically.
_TRIGGER_BADGE_SVG = "/assets/trigger_badge.svg"

# --- Main Cytoscape Stylesheet ---
stylesheet = [
    {
        'selector': 'node',
        'style': {
            'label': 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            'background-color': 'data(color)',
            'shape': 'data(shape)',
            'color': '#fff',
            'text-outline-width': 2,
            'text-outline-color': '#1a1d21',
            'width': 60,
            'height': 60,
            'text-max-width': '200px',
            'text-overflow-wrap': 'ellipsis',
            'text-wrap': 'ellipsis',
        }
    },
    {
        # Now flag: nodes the user is currently working on. Layered ON
        # TOP of the status color via a border. Placed BEFORE :selected so
        # selection feedback (white border) wins during click interaction —
        # a Now node briefly shows the white border on click, returns
        # to amber when deselected. The color is sourced per-element via
        # data(now_color) so the settings-modal color picker can change
        # it without restyling the canvas. The pulse animation is driven
        # separately by assets/now_pulse.js.
        'selector': '.now',
        'style': {
            'border-width': 5,
            'border-color': 'data(now_color)',
            'border-opacity': 1,
        }
    },
    {
        # Selection indicator: thick white border, no background override.
        # Previously used cyan #0dcaf0 as the bg, which clashed with the
        # Milestone type color (teal #17a2b8) — the two looked nearly
        # identical. A border-only indicator works regardless of the
        # node's underlying type color and avoids future clashes.
        'selector': 'node:selected',
        'style': {
            'border-width': 5,
            'border-color': '#ffffff',
            'border-opacity': 1,
        }
    },
    {
        'selector': 'edge',
        'style': {
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#666',
            'line-color': '#666',
            'width': 2
        }
    },
    {
        'selector': '[type = "Needs_Hard"]',
        'style': {
            'target-arrow-color': '#6c757d',
            'line-color': '#6c757d',
            'line-style': 'solid'
        }
    },
    {
        'selector': '[type = "Needs_Soft"]',
        'style': {
            'target-arrow-color': '#6c757d',
            'line-color': '#6c757d',
            'line-style': 'dashed'
        }
    },
    {
        'selector': '[type = "Helps"]',
        'style': {
            'source-arrow-shape': 'triangle',
            'source-arrow-color': '#0d6efd',
            'target-arrow-color': '#0d6efd',
            'line-color': '#0d6efd',
            'line-style': 'solid'
        }
    },
    {
        'selector': '.locate-pulse',
        'style': {
            'border-width': 8,
            'border-color': '#ffd000',
            'border-opacity': 1,
            'z-index': 9999,
        }
    },
    {
        'selector': '.trigger',
        'style': {
            'background-image': _TRIGGER_BADGE_SVG,
            'background-fit': 'none',
            'background-clip': 'none',
            'background-width': '32%',
            'background-height': '32%',
            'background-position-x': '100%',
            'background-position-y': '0%',
        }
    },
    {
        # Dormant: muted ghost effect with a high-contrast dashed border.
        # Light gray contrasts against every node fill (especially Learn,
        # which previously made the old blue ring invisible). Reduced
        # opacity reads as "asleep / not part of the live workspace".
        'selector': '.dormant',
        'style': {
            'border-width': 2,
            'border-color': '#adb5bd',
            'border-style': 'dashed',
            'opacity': 0.6,
        }
    },
]

# --- Mini Graph Stylesheet (smaller nodes for embedded views) ---
# Derived from the main stylesheet with node/edge size overrides.

_MINI_OVERRIDES = {
    'node': {
        'text-outline-width': 1,
        'font-size': 10,
        'width': 40,
        'height': 40,
    },
    'node:selected': {
        'border-width': 3,
    },
    'edge': {
        'width': 1.5,
    },
}


def _build_mini_stylesheet():
    """Derive a smaller-node stylesheet from the main stylesheet."""
    import copy
    mini = copy.deepcopy(stylesheet)
    for rule in mini:
        overrides = _MINI_OVERRIDES.get(rule['selector'])
        if overrides:
            rule['style'].update(overrides)
    return mini


mini_stylesheet = _build_mini_stylesheet()

# --- Event graph stylesheet ---
# The .dormant rule now lives on the base stylesheet so all canvases
# (main, details, events) render dormant nodes consistently. Kept as a
# separate alias for any future events-only style overrides.
events_graph_stylesheet = stylesheet

