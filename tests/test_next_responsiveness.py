"""Next selection stays local; initial content honors the visible filter state."""
import json
from pathlib import Path
import shutil
import subprocess

import dash
import pytest

from config import ConfigManager
from next_callbacks import register_next_callbacks, _initial_next_view, _components_by_id
from test_atomic_saves import graph


def test_selection_has_no_server_subscribers():
    from callbacks import register_callbacks
    app = dash.Dash(__name__)
    register_callbacks(app)
    register_next_callbacks(app)
    for spec in app.callback_map.values():
        if 'callback' in spec:
            assert not any(item['id'] == 'selected-suggestion-store' or
                           'suggestion-row' in item['id'] or 'now-row' in item['id']
                           for item in spec['inputs'])
    # Mixed Input/State grouping preserves the established core argument order.
    core = next(spec for spec in app.callback_map.values()
                if getattr(spec.get('callback'), '__name__', '') == 'core_engine')
    assert any(item['id'] == 'selected-suggestion-store' for item in core['state'])


def test_initial_next_is_populated_and_respects_remembered_filters():
    from layout import next_view
    from sidebars_layout import build_all_sidebars
    manager = graph('Visible', 'Filtered')
    node = manager.get_node('Filtered')
    node.value = 1
    manager.update_node(node)
    ConfigManager.set_remember_filters(True)
    ConfigManager.set_filters({'value': 4})
    view = _initial_next_view(next_view, build_all_sidebars())
    table = _components_by_id(view)['suggestions-table']
    from plotly.utils import PlotlyJSONEncoder
    payload = json.dumps(table, cls=PlotlyJSONEncoder)
    assert 'Visible' in payload and 'Filtered' not in payload
    # Per-request hydration must not mutate the global layout template.
    assert 'Loading suggestions' in json.dumps(
        _components_by_id(next_view)['suggestions-table'], cls=PlotlyJSONEncoder)


def test_browser_selection_refresh_and_removal():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js unavailable')
    source = Path('assets/next_selection.js').read_text(encoding='utf-8')
    script = r'''
const assert = require('node:assert/strict');
global.window = {dash_clientside: {callback_context: {triggered: []}}};
SOURCE
const select = window.dash_clientside.skillTreeNext.select;
const row = (name, description, type='suggestion-row') =>
    ({props:{id:{type,index:name},'data-description':description,style:{padding:'9px'}}});
const a = row('A', '<script>plain text</script>\nSecond line');
const b = row('B', '');
const c = row('C', 'Now description', 'now-row');
function click(name, type='suggestion-row') {
    window.dash_clientside.callback_context.triggered = [
        {prop_id:JSON.stringify({type,index:name})+'.n_clicks',value:1}];
}
click('A');
let result = select([1,0],[0],[a,b],[c],null);
assert.equal(result[0], 'A');
assert.equal(result[1], a.props['data-description']);
assert.equal(result[2][0].backgroundColor, '#2b3035');
assert.equal(result[2][1].backgroundColor, undefined);
click('B'); result = select([1,1],[0],[a,b],[c],result[0]);
assert.equal(result[1], 'No description');
assert.equal(result[2][0].backgroundColor, undefined);
click('C','now-row'); result = select([1,1],[1],[a,b],[c],result[0]);
assert.equal(result[1], 'Now description');
assert.equal(result[3][0].border, '2px solid #0d6efd');
window.dash_clientside.callback_context.triggered = [{prop_id:'now-nodes-table.children'}];
result = select([0,0],[0],[a,b],[row('C','Edited','now-row')],result[0]);
assert.equal(result[1], 'Edited');
result = select([0,0],[],[a,b],[],result[0]);
assert.equal(result[0], null);
assert.equal(result[1], 'Click a card or row to see its description');
assert.equal(a.props.style.backgroundColor, undefined);
'''.replace('SOURCE', source)
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)
