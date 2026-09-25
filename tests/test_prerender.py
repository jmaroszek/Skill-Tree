"""Startup callbacks that run while the layout is built, not in the browser.

Each page-load callback costs the browser a round of store updates, and
dash-renderer re-checks every mounted component on each one. See
prerender.py.
"""
import json

import dash
import pytest
from dash import Input, Output, State, dcc, html, no_update

import prerender
from prerender import prerender_layout, prerendered, prerendered_specs


def _app():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    return app


def _layout():
    return html.Div([
        dcc.Store(id='source', data=3),
        html.Div(id='doubled'),
        html.Div(id='labelled'),
        html.Div(id='kept', children='from the layout'),
        html.Div(id='untouched', children='before'),
    ])


def _find(layout, component_id):
    return prerender._index(layout)[component_id]


def test_outputs_land_in_the_layout_in_dependency_order():
    app = _app()

    # Registered consumer first: the order must come from the dependencies.
    @app.callback(Output('labelled', 'children'), Input('doubled', 'children'),
                  prevent_initial_call=True)
    @prerendered
    def label(doubled):
        return f'got {doubled}'

    @app.callback(Output('doubled', 'children'), Output('kept', 'children'),
                  Input('source', 'data'), prevent_initial_call=True)
    @prerendered
    def double(value):
        return value * 2, no_update

    layout = prerender_layout(_layout(), app)
    assert _find(layout, 'doubled').children == 6
    assert _find(layout, 'labelled').children == 'got 6'
    assert _find(layout, 'kept').children == 'from the layout'


def test_an_initial_call_sees_nothing_triggered():
    app = _app()

    @app.callback(Output('doubled', 'children'), Input('source', 'data'),
                  prevent_initial_call=True)
    @prerendered
    def which(_value):
        return repr(dash.ctx.triggered_id)

    layout = prerender_layout(_layout(), app)
    assert _find(layout, 'doubled').children == 'None'


def test_unmarked_callbacks_and_missing_inputs_are_left_alone():
    app = _app()

    @app.callback(Output('untouched', 'children'), Input('source', 'data'))
    def unmarked(value):
        return 'after'

    @app.callback(Output('doubled', 'children'), Input('not-on-the-page', 'value'),
                  prevent_initial_call=True)
    @prerendered
    def orphan(_value):
        raise AssertionError('Dash would not call this on load')

    layout = prerender_layout(_layout(), app)
    assert _find(layout, 'untouched').children == 'before'
    assert _find(layout, 'doubled').children is None


def test_a_prerendered_callback_must_not_also_run_on_load():
    app = _app()

    @app.callback(Output('doubled', 'children'), Input('source', 'data'))
    @prerendered
    def double(value):
        return value * 2

    with pytest.raises(RuntimeError, match='prevent_initial_call'):
        prerendered_specs(app)


def test_pattern_matching_ids_are_refused():
    app = _app()

    @app.callback(Output('doubled', 'children'),
                  Input({'type': 'row', 'index': dash.ALL}, 'value'),
                  prevent_initial_call=True)
    @prerendered
    def rows(_values):
        return ''

    with pytest.raises(ValueError, match='pattern-matching'):
        prerendered_specs(app)


@pytest.fixture
def real_app():
    import app as app_module
    return app_module.create_app(
        app_module.AppSettings(environment='sandbox', configure_logging=False))


def _served_layout(app):
    response = app.server.test_client().get('/_dash-layout')
    assert response.status_code == 200
    return response.get_json()


def _served_props(layout):
    found = {}

    def walk(node):
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict) and 'props' in node and 'type' in node:
            component_id = node['props'].get('id')
            if component_id is not None:
                key = (json.dumps(component_id, sort_keys=True)
                       if isinstance(component_id, dict) else component_id)
                found[key] = (node['type'], node['props'])
            for value in node['props'].values():
                walk(value)
    walk(layout)
    return found


def test_prerendered_inputs_are_on_the_page(real_app):
    """Dash doesn't run a callback on load when an input is missing, and
    neither does the prerender."""
    props = _served_props(_served_layout(real_app))
    specs = prerendered_specs(real_app)
    assert specs
    for spec in specs:
        for component_id, _prop in spec.inputs:
            assert component_id in props, (spec.name, component_id)


def test_the_editor_form_is_ready_without_a_load_time_callback(real_app):
    """The alias and link rows used to arrive with a dozen startup
    callbacks. The layout now carries them, and the editor doesn't populate
    itself on load: every path that opens it runs populate_editor."""
    props = _served_props(_served_layout(real_app))
    for container in ('aliases-container', 'editor-resources'):
        assert props[container][1].get('children'), container

    populate = next(c for c in real_app._callback_list
                    if c['output'].startswith('..node-name.value'))
    assert populate['prevent_initial_call'] is True


def test_startup_requests_nothing_a_prerendered_callback_answers(real_app):
    """What the browser is told to run on load leaves out every
    @prerendered callback."""
    dependencies = real_app.server.test_client().get('/_dash-dependencies').get_json()
    names = {spec.name for spec in prerendered_specs(real_app)}
    for dependency in dependencies:
        if dependency['output'] in names:
            assert dependency['prevent_initial_call'] is True
