"""Every canvas paints and describes a node the same way.

Nodes, Details and Events each choose which nodes to show, and all three build
the elements with `callback_helpers.build_node_element`. The hover tooltip,
context menu, stylesheet and Now pulse read that payload on whichever canvas
raised them. So one graph rendered by all three canvases must give every node
they share the same fill, classes and tooltip.
"""

import dash
import pytest

import callbacks
from callback_helpers import CanvasNodeStyles, build_node_element, node_fill_color
from callbacks import generate_elements, register_callbacks
from config import DEFAULT_NODE_COLORS, ConfigManager
from details_callbacks import _build_graph_elements
from event_callbacks import register_event_callbacks
from event_manager import EventManager
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Event, Node

# The positional order of display_hover_data's inputs.
CANVAS_IDS = ('cytoscape-graph', 'details-mini-graph', 'events-detail-graph')

# The nodes all three canvases render from the seeded graph.
SHARED = {'Root', 'Open Prereq', 'Done Prereq', 'Blocked Prereq',
          'Override Prereq', 'Hub'}


def _node(name, **overrides):
    fields = dict(name=name, type='Learn', description='', value=6,
                  time_o=2.0, time_m=4.0, time_p=8.0, interest=7,
                  difficulty=5, status='Open', context='Mind')
    fields.update(overrides)
    return Node(**fields)


def _app(*registrars):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    for register in registrars:
        register(app)
    return app


def _callback(app, name):
    for spec in app.callback_map.values():
        callback = spec.get('callback')
        while callback is not None and hasattr(callback, '__wrapped__'):
            callback = callback.__wrapped__
        if callback is not None and callback.__name__ == name:
            return callback
    raise LookupError(name)


def _nodes(elements):
    return {element['data']['id']: element for element in elements
            if 'source' not in element['data']}


@pytest.fixture
def canvases():
    """The seeded graph as each canvas renders it, keyed by Cytoscape id.

    Root is dormant, attached to the Trip event, and Blocked. Every other
    shared node leads into Root, so it is one of Root's prerequisites on
    Details and one of the event's neighbors on Events.
    """
    graph, events = GraphManager(), EventManager()
    graph.add_node(_node('Open Prereq', now=1))
    graph.add_node(_node('Done Prereq', status='Done'))
    graph.add_node(_node('Upstream'))
    graph.add_node(_node('Blocked Prereq'))
    graph.add_node(_node('Override Prereq'))
    graph.add_node(_node('Hub', value_mode='inherited', time_mode='inherited'))
    events.add_event(Event(name='Trip', trigger_nodes=['Open Prereq']))
    events.create_dormant_node(_node('Root'), 'Trip')
    graph.add_edge('Upstream', 'Blocked Prereq', EDGE_NEEDS_HARD)
    graph.add_edge('Open Prereq', 'Root', EDGE_NEEDS_HARD)
    graph.add_edge('Done Prereq', 'Root', EDGE_NEEDS_HARD)
    for name in ('Blocked Prereq', 'Override Prereq', 'Hub'):
        graph.add_edge(name, 'Root', EDGE_NEEDS_SOFT)
    ConfigManager.set_override({'parent': 'Override Prereq', 'mode': 'node_only'})

    # The premises the tests below rely on.
    assert graph.get_node('Root').status == 'Blocked'
    assert graph.get_node('Blocked Prereq').status == 'Blocked'
    assert graph.get_node('Open Prereq').now == 1

    show_dormant = {'show_dormant': True}
    render_event_graph = _callback(_app(register_event_callbacks), 'render_event_graph')
    return {
        'cytoscape-graph': generate_elements(filters=show_dormant),
        'details-mini-graph': _build_graph_elements(
            'Root', ['include'], ['include'], global_filters=show_dormant),
        'events-detail-graph': render_event_graph('Trip', 0),
    }


def test_every_canvas_renders_the_shared_nodes(canvases):
    for canvas_id, elements in canvases.items():
        assert SHARED <= set(_nodes(elements)), canvas_id


def test_fill_follows_one_rule_on_every_canvas(canvases):
    colors = ConfigManager.get_node_colors()
    expected = {
        'Root': colors['Blocked'],              # dormant, and still red on Events
        'Blocked Prereq': colors['Blocked'],
        'Done Prereq': colors['Done'],
        'Override Prereq': colors['Override'],  # pink on Details too
        'Open Prereq': colors['Learn'],
        'Hub': colors['Learn'],
    }
    for canvas_id, elements in canvases.items():
        nodes = _nodes(elements)
        assert {name: nodes[name]['data']['color'] for name in expected} == expected, canvas_id


def test_shared_nodes_carry_the_same_classes_on_every_canvas(canvases):
    expected = {name: set() for name in SHARED}
    expected['Root'] = {'dormant'}
    expected['Open Prereq'] = {'trigger', 'now'}
    for canvas_id, elements in canvases.items():
        nodes = _nodes(elements)
        classes = {name: set(nodes[name]['classes'].split()) for name in SHARED}
        assert classes == expected, canvas_id


def test_hovering_a_node_shows_the_same_tooltip_on_every_canvas(canvases, monkeypatch):
    display_hover_data = _callback(_app(register_callbacks), 'display_hover_data')

    def tooltip(canvas_id, name):
        monkeypatch.setattr(callbacks, 'get_trigger_id', lambda: canvas_id)
        data = _nodes(canvases[canvas_id])[name]['data']
        return str(display_hover_data(
            *(data if other == canvas_id else None for other in CANVAS_IDS)))

    for name in SHARED:
        tooltips = {canvas_id: tooltip(canvas_id, name) for canvas_id in CANVAS_IDS}
        assert len(set(tooltips.values())) == 1, (name, tooltips)
    # Hub inherits both its ratings and its time, so it reads as a container.
    assert "children='Container'" in tooltip('details-mini-graph', 'Hub')


_STYLES = CanvasNodeStyles(colors=dict(DEFAULT_NODE_COLORS), shapes={},
                           override_names=frozenset({'Pinned'}),
                           trigger_names=frozenset())


def test_override_color_takes_precedence_over_status():
    pinned = _node('Pinned', status='Done')
    assert node_fill_color(pinned, _STYLES.colors, _STYLES.override_names) \
        == DEFAULT_NODE_COLORS['Override']


def test_classes_are_always_emitted_and_selection_only_on_request():
    plain = build_node_element(_node('Plain'), _STYLES)
    assert plain['classes'] == ''
    assert 'selected' not in plain
    assert build_node_element(_node('Plain'), _STYLES, selected=False)['selected'] is False


def test_dormant_argument_replaces_the_node_flag():
    attached = build_node_element(_node('Attached'), _STYLES, dormant=True)
    assert (attached['data']['dormant'], attached['classes']) == (1, 'dormant')
    released = build_node_element(_node('Released', dormant=1), _STYLES, dormant=False)
    assert (released['data']['dormant'], released['classes']) == (0, '')
