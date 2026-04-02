"""
Shared Cytoscape stylesheet definitions.
Extracted to avoid circular imports between layout.py and goals_layout.py.
"""

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
        'selector': 'node:selected',
        'style': {
            'background-color': '#0dcaf0',
            'border-width': 4,
            'border-color': '#055160'
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
        'selector': '[type = "Resource"]',
        'style': {
            'line-style': 'dotted'
        }
    }
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

