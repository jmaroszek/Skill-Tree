"""The sidebar filters narrow the Events canvas's outside nodes, never the event.

The event's own nodes are the list the user loaded, and are dormant, so
filtering them would hide the very nodes the canvas exists to check.
"""

import dash
import pytest

from skilltree.features.events.callbacks import register_event_callbacks
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Event, Node


def _node(name, **overrides):
    fields = dict(name=name, type='Learn', description='', value=6,
                  time_o=2.0, time_m=4.0, time_p=8.0, interest=7,
                  difficulty=5, status='Open', context='Mind')
    fields.update(overrides)
    return Node(**fields)


def _callback(name):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)
    for spec in app.callback_map.values():
        callback = spec.get('callback')
        while callback is not None and hasattr(callback, '__wrapped__'):
            callback = callback.__wrapped__
        if callback is not None and callback.__name__ == name:
            return callback
    raise LookupError(name)


@pytest.fixture
def render():
    """Trip holds two dormant nodes, one in Mind and one in Body. Outside it
    sit a Mind and a Body prerequisite, a Done one, and a node asleep under
    another event."""
    graph, events = GraphManager(), EventManager()
    graph.add_node(_node('Mind Prereq'))
    graph.add_node(_node('Body Prereq', context='Body'))
    graph.add_node(_node('Done Prereq', status='Done'))
    events.add_event(Event(name='Trip'))
    events.add_event(Event(name='Later'))
    events.create_dormant_node(_node('Mind Task'), 'Trip')
    events.create_dormant_node(_node('Body Task', context='Body'), 'Trip')
    events.create_dormant_node(_node('Elsewhere'), 'Later')
    graph.add_edge('Mind Prereq', 'Mind Task', EDGE_NEEDS_HARD)
    graph.add_edge('Body Prereq', 'Body Task', EDGE_NEEDS_HARD)
    graph.add_edge('Done Prereq', 'Mind Task', EDGE_NEEDS_HARD)
    graph.add_edge('Elsewhere', 'Body Task', EDGE_NEEDS_SOFT)
    callback = _callback('render_event_graph')

    def run(**filters):
        elements = callback('Trip', 0, True, None, filters)
        nodes = {e['data']['id'] for e in elements if 'source' not in e['data']}
        edges = {(e['data']['source'], e['data']['target'])
                 for e in elements if 'source' in e['data']}
        return nodes, edges
    return run


def test_a_context_filter_hides_only_outside_nodes(render):
    nodes, edges = render(context=['Mind'])
    assert nodes == {'Mind Task', 'Body Task', 'Mind Prereq'}
    assert edges == {('Mind Prereq', 'Mind Task')}


def test_show_done_and_show_dormant_gate_outside_nodes(render):
    nodes, _ = render()
    assert nodes == {'Mind Task', 'Body Task', 'Mind Prereq', 'Body Prereq'}
    nodes, _ = render(done=['show_done'], dormant=['show_dormant'])
    assert {'Done Prereq', 'Elsewhere'} <= nodes


def test_a_filter_that_matches_nothing_still_shows_the_event(render):
    nodes, edges = render(search={'text': 'no such node'})
    assert nodes == {'Mind Task', 'Body Task'}
    assert edges == set()


def test_the_chip_names_the_filters():
    chip = _callback('update_events_filter_chip')
    text, title, hidden = chip(None, ['Mind'], None, None, None, None, None,
                               None, None, 'hours', '', '', True)
    assert (text, title, hidden) == ('Mind', 'Mind', False)
