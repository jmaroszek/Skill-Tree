"""Next selection stays local; initial content honors the visible filter state."""
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.domain.models import STATUS_DONE
from skilltree.features.home.callbacks import register_home_callbacks
from skilltree.features.home.view import initial_next_view, perf_stats_text, _components_by_id
from skilltree.store import settings
from support.callbacks import registered
from support.triggers import fire
from support.graphs import graph, make_node
from support.paths import asset_file


def test_selection_has_no_server_subscribers(services):
    from skilltree.engine.callbacks import register_engine_callbacks
    app = dash.Dash(__name__)
    register_engine_callbacks(app, services)
    register_home_callbacks(app, services)
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
    from skilltree.features.home.layout import build_next_view
    from skilltree.shell import build_all_sidebars
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
    _components_by_id(sidebars)['filter-value'].value = [4, 10]
    view = initial_next_view(manager, next_view, sidebars)
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
    source = asset_file('next_selection.js').read_text(encoding='utf-8')
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
assert.equal(result[2][0].backgroundColor, 'var(--st-bg-raised)');
assert.equal(result[2][1].backgroundColor, undefined);
click('B'); result = select([1,1],[0],[a,b],[c],result[0]);
assert.equal(result[1], 'No description');
assert.equal(result[2][0].backgroundColor, undefined);
click('C','now-row'); result = select([1,1],[1],[a,b],[c],result[0]);
assert.equal(result[1], 'Now description');
assert.equal(result[3][0].border, '2px solid var(--st-accent)');
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
assert.equal(result[3][0].border, '1px solid var(--st-border-card)');  // N3
assert.equal(result[3][1].border, '1px solid var(--st-border-card)');  // N1
assert.equal(result[3][2].border, '2px solid var(--st-accent)');  // N2
'''.replace('SOURCE', source)
    subprocess.run([node, '-e', script], check=True, capture_output=True, text=True)


def test_home_tables_are_not_rebuilt_on_page_load(services):
    """The layout already carries both, from the same snapshot and filters.
    Rebuilding the table on load held up the whole startup: it feeds
    selected-suggestion-store, a State of the core engine, so Dash kept the
    core engine waiting for it. A row clicked meanwhile was also lost when
    the rebuilt table replaced it."""
    app = dash.Dash(__name__)
    register_home_callbacks(app, services)
    for output in ("suggestions-table.children", "now-nodes-table.children"):
        spec = next(c for c in app._callback_list if output in c["output"])
        assert spec["prevent_initial_call"] is True, output


def test_the_first_layout_carries_the_scoring_time_caption(monkeypatch):
    """The table's rebuild on load used to be the caption's first update, so
    without it the corner of Home stayed blank until the next refresh."""
    from skilltree.store.graph.manager import GraphManager
    from skilltree.shell import build_app_layout

    settings.SHOW_SCORING_PERF.set(True)
    graph = GraphManager()
    graph.last_perf_timings = {"n_nodes": 3, "n_edges": 2, "total_ms": 12.4}
    graph.startup_perf_recorded = True
    caption = _components_by_id(build_app_layout(graph, env="sandbox"))["next-perf-stats"]

    assert caption.children == "0 nodes · 0 edges · 12ms"


def _caption_graph():
    manager = graph("First")
    manager.add_node(make_node("Second", status=STATUS_DONE))
    manager.add_edge("First", "Second", "Needs_Soft")
    return manager


def test_the_caption_leaves_when_the_setting_is_off():
    # It kept showing, even after a reload, once a time had been recorded.
    manager = _caption_graph()
    manager.last_perf_timings = {"total_ms": 12.4}
    settings.SHOW_SCORING_PERF.set(False)

    assert perf_stats_text(manager) is None


def test_the_caption_counts_the_graph_as_it_is_now():
    # The counts were the first scoring pass's, and never changed after it.
    manager = _caption_graph()
    manager.last_perf_timings = {"n_nodes": 900, "n_edges": 900, "total_ms": 12.4}
    settings.SHOW_SCORING_PERF.set(True)

    assert perf_stats_text(manager) == "1 nodes · 1 edges · 12ms"


def test_the_table_refresh_clears_the_caption_when_it_turns_off(services):
    fn = registered(register_home_callbacks, services=services)["populate_suggestions"]
    services.graph.last_perf_timings = {"total_ms": 12.4}
    settings.SHOW_SCORING_PERF.set(False)
    args = [None] * 17

    assert fn(*args, "0 nodes · 0 edges · 12ms")[1] is None
    assert fn(*args, None)[1] is dash.no_update


def test_no_caption_before_any_timing_is_recorded(monkeypatch):
    from skilltree.store.graph.manager import GraphManager
    from skilltree.features.home.view import perf_stats_text

    assert perf_stats_text(GraphManager()) is None


def test_the_now_cap_message_counts_properly():
    from skilltree.features.home.now import now_cap_message

    settings.NOW_NODE_CAP.set(1)
    assert now_cap_message().startswith("1 Now node is the cap.")
    settings.NOW_NODE_CAP.set(3)
    assert now_cap_message().startswith("3 Now nodes is the cap.")


@pytest.mark.parametrize("trigger, typed, current, stored, shown", [
    ("btn-sugg-plus", None, 10, 11, 11),
    ("btn-sugg-minus", None, 10, 9, 9),
    ("btn-sugg-minus", None, 1, 1, 1),
    ("suggestion-count-display.value", 20, 5, 20, 20),
    ("suggestion-count-display.value", 5000, 5, 999, 999),
])
def test_the_row_count_is_saved(services, trigger, typed, current, stored, shown):
    fn = registered(register_home_callbacks, services=services)["update_suggestion_count"]
    settings.NEXT_TABLE_ROWS.set(current)
    fire(trigger)
    _, display = fn(1, 1, typed, current)
    assert display == shown
    assert settings.NEXT_TABLE_ROWS.get() == stored


@pytest.mark.parametrize("typed", [None, 0, -3, 2.5, "abc"])
def test_a_bad_row_count_puts_the_last_one_back(services, typed):
    fn = registered(register_home_callbacks, services=services)["update_suggestion_count"]
    settings.NEXT_TABLE_ROWS.set(7)
    fire("suggestion-count-display.value")
    store, display = fn(1, 1, typed, 7)
    assert store is dash.no_update and display == 7
    assert settings.NEXT_TABLE_ROWS.get() == 7
