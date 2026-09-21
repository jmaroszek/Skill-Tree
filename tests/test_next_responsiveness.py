"""Next selection stays local; initial content honors the visible filter state."""
import json
from pathlib import Path
import shutil
import subprocess

import dash
import pytest

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


def test_initial_next_is_populated_and_reads_the_sidebar_controls():
    from layout import build_next_view
    from sidebars_layout import build_all_sidebars
    # Built once and reused: the assertion below checks that hydration does not
    # mutate the template it was handed, so both uses must be the same object.
    next_view = build_next_view()
    manager = graph('Visible', 'Filtered')
    node = manager.get_node('Filtered')
    node.value = 1
    manager.update_node(node)
    # First paint reads the live sidebar components, not stored filter state —
    # the sidebar always opens unfiltered, so set the control directly.
    sidebars = build_all_sidebars()
    _components_by_id(sidebars)['filter-value'].value = 4
    view = _initial_next_view(next_view, sidebars)
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

// After a reorder Dash's wildcard outputs no longer follow layout order;
// each style must land on the card it belongs to.
const n1 = row('N1', '', 'now-row'), n2 = row('N2', '', 'now-row'), n3 = row('N3', '', 'now-row');
const out = names => names.map(name => ({id: {type: 'now-row', index: name}, property: 'style'}));
window.dash_clientside.callback_context.outputs_list =
    [null, null, out(['A', 'B']), out(['N3', 'N1', 'N2']), null];
click('N2', 'now-row'); result = select([0,0],[0,1,0],[a,b],[n1,n2,n3],null);
assert.equal(result[0], 'N2');
assert.equal(result[3][0].border, '1px solid #495057');  // N3
assert.equal(result[3][1].border, '1px solid #495057');  // N1
assert.equal(result[3][2].border, '2px solid #0d6efd');  // N2
'''.replace('SOURCE', source)
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)


def test_home_tables_are_not_rebuilt_on_page_load():
    """The layout already carries both, from the same snapshot and filters.
    Rebuilding the table on load held up the whole startup: it feeds
    selected-suggestion-store, a State of the core engine, so Dash kept the
    core engine waiting for it. A row clicked meanwhile was also lost when
    the rebuilt table replaced it."""
    app = dash.Dash(__name__)
    register_next_callbacks(app)
    for output in ("suggestions-table.children", "now-nodes-table.children"):
        spec = next(c for c in app._callback_list if c["output"] == output)
        assert spec["prevent_initial_call"] is True, output


def test_the_first_layout_carries_the_scoring_time_caption(monkeypatch):
    """The table's rebuild on load used to be the caption's first update, so
    without it the corner of Home stayed blank until the next refresh."""
    from graph_manager import GraphManager
    from layout import build_app_layout

    monkeypatch.setattr(GraphManager, "_last_perf_timings",
                        {"n_nodes": 3, "n_edges": 2, "total_ms": 12.4})
    monkeypatch.setattr(GraphManager, "_startup_perf_recorded", True)
    caption = _components_by_id(build_app_layout([], env="sandbox"))["next-perf-stats"]

    assert caption.children == "3 nodes · 2 edges · 12ms"


def test_no_caption_before_any_timing_is_recorded(monkeypatch):
    from graph_manager import GraphManager
    from next_view import perf_stats_text

    monkeypatch.setattr(GraphManager, "_last_perf_timings", None)
    assert perf_stats_text() is None
