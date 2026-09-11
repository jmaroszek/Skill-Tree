"""The canvases are listed once, in canvases.py.

Everything that applies to every canvas reads that list: the hover tooltip,
freeze wiring and layout requests in Python, and the shared modules in assets/.
The goal-mini-graph canvas outlived its removal in three asset files that each
kept their own list.
"""

import json
import re
from dataclasses import fields
from pathlib import Path

import dash

from callbacks import register_callbacks
from canvases import CANVASES, client_registry, install_client_registry
from layout import build_app_layout

ASSETS = Path(__file__).resolve().parents[1] / 'assets'

# The assets that act on every canvas. They take the canvases from the page.
SHARED_CANVAS_ASSETS = ('context_menu.js', 'freeze_positions.js', 'fullscreen.js',
                        'layout_requests.js', 'now_pulse.js', 'tooltip.js')

# The Graph Layout controls each canvas's layout request listens to, in order.
LAYOUT_CONTROLS = ('edge-length', 'gravity', 'repulsion', 'animate', 'relayout')


def _walk(component):
    yield component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _core_app():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_callbacks(app)
    return app


def _component_ids(canvas):
    ids = [getattr(canvas, field.name) for field in fields(canvas)
           if field.name.endswith('_id') and getattr(canvas, field.name)]
    return ids + [canvas.control_id(control)
                  for control in LAYOUT_CONTROLS + ('freeze-rerender',)]


def test_every_registered_component_exists_in_the_layout():
    layout_ids = {getattr(item, 'id', None)
                  for item in _walk(build_app_layout([], env='sandbox'))}
    for canvas in CANVASES:
        for component_id in _component_ids(canvas):
            assert component_id in layout_ids, (canvas.key, component_id)


def test_page_receives_the_registry_before_any_script():
    app = dash.Dash(__name__)
    install_client_registry(app)
    index = app.index_string
    assert index.index('window.SkillTree.canvases') < index.index('{%scripts%}')
    payload = re.search(r'window\.SkillTree\.canvases = (\[.*?\]);', index).group(1)
    assert json.loads(payload) == client_registry()


def test_tooltip_listens_to_every_canvas_in_registry_order():
    spec = _core_app().callback_map['hover-tooltip.children']
    assert [item['id'] for item in spec['inputs']] == [c.cytoscape_id for c in CANVASES]


def test_every_canvas_gets_the_freeze_wiring():
    callbacks = _core_app()._callback_list
    for canvas in CANVASES:
        forward = next(c for c in callbacks
                       if c['output'] == f'{canvas.cytoscape_id}.elements')
        assert [i['id'] for i in forward['inputs']] == [canvas.pending_store_id]
        sync = next(c for c in callbacks
                    if c['output'] == f'{canvas.freeze_store_id}.data')
        assert [i['id'] for i in sync['inputs']] == [canvas.control_id('freeze-rerender')]
        assert any(canvas.freeze_indicator_id in c['output']
                   and canvas.container_id in c['output'] for c in callbacks), canvas.key


def test_every_canvas_gets_a_layout_request():
    callbacks = _core_app()._callback_list
    for canvas in CANVASES:
        spec = next(c for c in callbacks
                    if c['output'] == f'{canvas.cytoscape_id}.layout')
        assert spec['clientside_function'] == {
            'namespace': 'skillTreeLayout', 'function_name': canvas.key}
        expected = [canvas.control_id(control) for control in LAYOUT_CONTROLS]
        if canvas.lays_out_elements:
            expected.append(canvas.cytoscape_id)
        # The freeze-off transition is what lays out the held control changes.
        expected.append(canvas.freeze_store_id)
        assert [i['id'] for i in spec['inputs']] == expected, canvas.key
        assert [s['id'] for s in spec['state']] == (
            [canvas.view_store_id] if canvas.view_store_id else []), canvas.key


def test_shared_canvas_assets_name_no_canvas_of_their_own():
    for name in SHARED_CANVAS_ASSETS:
        source = (ASSETS / name).read_text(encoding='utf-8')
        assert 'window.SkillTree.canvases' in source, name
        for canvas in CANVASES:
            assert canvas.cytoscape_id not in source, (name, canvas.cytoscape_id)
