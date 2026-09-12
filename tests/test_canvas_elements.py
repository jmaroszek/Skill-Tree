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
from canvases import CANVASES
from config import DEFAULT_NODE_COLORS, ConfigManager
from details_callbacks import _build_graph_elements
from event_callbacks import register_event_callbacks
from event_manager import EventManager
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Event, Node

# The nodes all three canvases render from the seeded graph.
SHARED = {'Root', 'Open Prereq', 'Done Prereq', 'Blocked Prereq',
          'Soft Prereq', 'Hub'}


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
    """The seeded graph as each canvas renders it, keyed by canvas key.

    Root is dormant, attached to the Trip event, and Blocked. Every other
    shared node leads into Root, so it is one of Root's prerequisites on
    Details and one of the event's neighbors on Events.
    """
    graph, events = GraphManager(), EventManager()
    graph.add_node(_node('Open Prereq', now=1))
    graph.add_node(_node('Done Prereq', status='Done'))
    graph.add_node(_node('Upstream'))
    graph.add_node(_node('Blocked Prereq'))
    graph.add_node(_node('Soft Prereq'))
    graph.add_node(_node('Hub', value_mode='inherited', time_mode='inherited'))
    events.add_event(Event(name='Trip', trigger_nodes=['Open Prereq']))
    events.create_dormant_node(_node('Root'), 'Trip')
    graph.add_edge('Upstream', 'Blocked Prereq', EDGE_NEEDS_HARD)
    graph.add_edge('Open Prereq', 'Root', EDGE_NEEDS_HARD)
    graph.add_edge('Done Prereq', 'Root', EDGE_NEEDS_HARD)
    for name in ('Blocked Prereq', 'Soft Prereq', 'Hub'):
        graph.add_edge(name, 'Root', EDGE_NEEDS_SOFT)

    # The premises the tests below rely on.
    assert graph.get_node('Root').status == 'Blocked'
    assert graph.get_node('Blocked Prereq').status == 'Blocked'
    assert graph.get_node('Open Prereq').now == 1

    show_dormant = {'show_dormant': True}
    render_event_graph = _callback(_app(register_event_callbacks), 'render_event_graph')
    rendered = {
        'main': generate_elements(filters=show_dormant),
        'details': _build_graph_elements(
            'Root', ['include'], ['include'], global_filters=show_dormant),
        'events': render_event_graph('Trip', 0),
    }
    assert set(rendered) == {canvas.key for canvas in CANVASES}
    return rendered


def test_every_canvas_renders_the_shared_nodes(canvases):
    for key, elements in canvases.items():
        assert SHARED <= set(_nodes(elements)), key


def test_fill_follows_one_rule_on_every_canvas(canvases):
    colors = ConfigManager.get_node_colors()
    expected = {
        'Root': colors['Blocked'],              # dormant, and still red on Events
        'Blocked Prereq': colors['Blocked'],
        'Done Prereq': colors['Done'],
        'Soft Prereq': colors['Learn'],
        'Open Prereq': colors['Learn'],
        'Hub': colors['Learn'],
    }
    for key, elements in canvases.items():
        nodes = _nodes(elements)
        assert {name: nodes[name]['data']['color'] for name in expected} == expected, key


def test_shared_nodes_carry_the_same_classes_on_every_canvas(canvases):
    expected = {name: set() for name in SHARED}
    expected['Root'] = {'dormant'}
    expected['Open Prereq'] = {'trigger', 'now'}
    for key, elements in canvases.items():
        nodes = _nodes(elements)
        classes = {name: set(nodes[name]['classes'].split()) for name in SHARED}
        assert classes == expected, key


def test_hovering_a_node_shows_the_same_tooltip_on_every_canvas(canvases, monkeypatch):
    display_hover_data = _callback(_app(register_callbacks), 'display_hover_data')

    def tooltip(key, name):
        trigger = next(canvas.cytoscape_id for canvas in CANVASES if canvas.key == key)
        monkeypatch.setattr(callbacks, 'get_trigger_id', lambda: trigger)
        data = _nodes(canvases[key])[name]['data']
        return str(display_hover_data(
            *(data if canvas.key == key else None for canvas in CANVASES)))

    for name in SHARED:
        tooltips = {key: tooltip(key, name) for key in canvases}
        assert len(set(tooltips.values())) == 1, (name, tooltips)
    # Hub inherits both its ratings and its time, so it reads as a container.
    assert "children='Container'" in tooltip('details', 'Hub')


_STYLES = CanvasNodeStyles(colors=dict(DEFAULT_NODE_COLORS), shapes={},
                           trigger_names=frozenset())


def test_status_beats_type_in_the_fill():
    """Now has no say in the fill — it is drawn as the pulsing border."""
    assert (node_fill_color(_node('Finished', status='Done'), _STYLES.colors)
            == DEFAULT_NODE_COLORS['Done'])
    assert (node_fill_color(_node('Busy', now=3), _STYLES.colors)
            == DEFAULT_NODE_COLORS['Learn'])


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
