"""Every canvas paints and describes a node the same way.

Nodes, Details and Events each choose which nodes to show, and all three build
the elements with `ui/canvas/elements.build_node_element`. The hover tooltip,
context menu, stylesheet and Now pulse read that payload on whichever canvas
raised them. So one graph rendered by all three canvases must give every node
they share the same fill, classes and tooltip.
"""

import functools
import dash
import pytest

from skilltree.ui.canvas.elements import (
    CanvasNodeStyles, build_node_element, node_fill_color,
)
from skilltree.ui.canvas.elements import generate_elements
from skilltree.ui.canvas import callbacks as canvas_callbacks
from skilltree.ui.canvas.registry import CANVASES
from skilltree.store.settings import DEFAULT_NODE_COLORS, ConfigManager
from skilltree.features.details.callbacks import _build_graph_elements
from skilltree.features.events.callbacks import register_events_callbacks
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Event, Node
from support.triggers import fire
from skilltree.store.graph.state import revisions
from skilltree.services import AppServices
from skilltree.ui.canvas.callbacks import register_canvas_callbacks

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
    services = AppServices()
    for register in registrars:
        register(app, services)
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
def canvases(services):
    """The seeded graph as each canvas renders it, keyed by canvas key.

    Root is dormant, attached to the Trip event, and Blocked. Every other
    shared node leads into Root, so it is one of Root's prerequisites on
    Details and one of the event's neighbors on Events.
    """
    graph, events = services.graph, services.events
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
    render_event_graph = _callback(_app(register_events_callbacks), 'render_event_graph')
    rendered = {
        'main': generate_elements(services.graph, services.events, filters=show_dormant),
        'details': _build_graph_elements(services.graph, services.events, 
            'Root', ['include'], ['include'], global_filters=show_dormant),
        # Show Done and Show Dormant, as the other two canvases are given.
        'events': render_event_graph('Trip', 0, True, None, {
            'done': ['show_done'], 'dormant': ['show_dormant']}),
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
    display_hover_data = _callback(_app(register_canvas_callbacks), 'display_hover_data')

    def tooltip(key, name):
        trigger = next(canvas.cytoscape_id for canvas in CANVASES if canvas.key == key)
        fire(trigger)
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


def test_no_canvas_lets_a_link_be_selected(canvases):
    """A click on a link selected it, which cleared the node selection."""
    for key, elements in canvases.items():
        edges = [e for e in elements if 'source' in e['data']]
        assert edges, key
        assert all(e['selectable'] is False for e in edges), key


def test_the_nodes_canvas_can_leave_the_selection_alone(canvases, services):
    from skilltree.ui.canvas.elements import KEEP_SELECTION
    kept = generate_elements(services.graph, services.events, filters={'show_dormant': True}, active_node_id=KEEP_SELECTION)
    nodes = [e for e in kept if 'source' not in e['data']]
    assert nodes and all('selected' not in e for e in nodes)


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


def test_elements_carry_every_field_their_readers_use():
    """Canvas elements carry a chosen field list, not the whole node. The
    tooltip and the context menu read fields from element data, so a field
    either of them starts reading has to join CANVAS_NODE_FIELDS."""
    import inspect
    import re
    from pathlib import Path
    from skilltree.ui.canvas.elements import CANVAS_NODE_FIELDS

    carried = set(CANVAS_NODE_FIELDS) | {'id', 'label', 'color', 'shape'}

    source = inspect.getsource(canvas_callbacks.register_canvas_callbacks)
    tooltip = source[source.index('def display_hover_data'):]
    tooltip = tooltip[:tooltip.index('\n    # ---')]
    read = set(re.findall(r"data\.get\('([a-z_]+)'", tooltip))
    assert read and read <= carried, read - carried

    menu = (Path(__file__).resolve().parents[1] / 'assets' / 'context_menu.js'
            ).read_text(encoding='utf-8')
    read = set(re.findall(r"\b(?:nodeData|_currentNodeData|node)\.([a-z_]+)\b", menu))
    read -= {'id', 'push', 'data'}  # node.data() is Cytoscape's accessor
    assert read and read <= carried, read - carried


def test_every_laid_out_canvas_redraws_when_the_graph_changes():
    """A node saved anywhere, such as a bridge linked to an event's node, has
    to reach Details and Events without reopening them."""
    from skilltree.features.details.callbacks import register_details_callbacks
    app = _app(register_events_callbacks, register_details_callbacks)
    for canvas in CANVASES:
        if not canvas.lays_out_elements:
            continue
        specs = [spec for key, spec in app.callback_map.items()
                 if f"{canvas.pending_store_id}.data" in key]
        assert any({'id': 'graph-version-store', 'property': 'data'} in spec['inputs']
                   for spec in specs), canvas.key


def test_canvas_view_preserves_filtering_and_focus_without_mutating_graph():
    from skilltree.ui.canvas.view import build_canvas_view
    from skilltree.ui.canvas.elements import generate_elements
    from test_atomic_saves import graph
    manager = graph('A', 'B')
    manager.add_edge('A', 'B', 'Needs_Hard')
    version = revisions.graph
    view = build_canvas_view(
        manager, functools.partial(generate_elements, manager, EventManager(GraphManager())),
        'filter-context', None,
        'components', {}, 'All', 'B', None, None)
    assert {e['data']['id'] for e in view.elements if 'source' not in e['data']} == {'A', 'B'}
    assert view.clear_focus_style == {'display': 'inline-block'}
    assert any(rule['selector'] == 'node[id = "A"]' for rule in view.stylesheet)
    assert revisions.graph == version
