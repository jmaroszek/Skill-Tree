"""Rows sent as one component: their description, and the script that builds them."""
import json
import shutil
import subprocess

import dash_bootstrap_components as dbc
import pytest
from dash import dcc, html

from skilltree.features.analyze.callbacks import compute_rating_distribution
from skilltree.features.analyze.charts import render_rating_distribution
from skilltree.features.analyze.inert import inert_rows, to_tree
from support.graphs import make_node
from support.layout import walk
from support.paths import asset_file


def test_the_tree_keeps_classes_styles_and_data_attributes():
    row = html.Div([html.Span("Hi", className="a b"),
                    html.Div(style={'marginLeft': '2px', '--mix': '5%'})],
                   role="row", tabIndex=0, **{'data-tip': 'one\ntwo'})
    assert to_tree(row) == [['div', {'role': 'row', 'tabindex': '0', 'data-tip': 'one\ntwo'}, [
        ['span', {'class': 'a b'}, ['Hi']],
        ['div', {'style': 'margin-left:2px;--mix:5%'}, []],
    ]]]


def test_a_number_and_nothing_are_children_too():
    assert to_tree(html.Div([1, None, 2.5])) == [['div', {}, ['1', '2.5']]]


@pytest.mark.parametrize("live", [dcc.Store(id="s"), dbc.Button("x")])
def test_a_component_with_behaviour_of_its_own_is_refused(live):
    with pytest.raises(TypeError):
        to_tree(html.Div(live))


def test_one_component_stands_for_the_rows():
    holder = inert_rows([html.Div("a"), html.Div("b")], "rows")
    assert holder.className == "rows"
    assert json.loads(getattr(holder, 'data-tree')) == [['div', {}, ['a']], ['div', {}, ['b']]]
    assert getattr(holder, 'children', None) is None


def test_the_contexts_grid_stays_a_few_components(temp_database):
    """Each mounted component makes every store update dearer on every tab: the
    grid's cells used to delay every sidebar by about 90 ms. So a grid with many
    rows mounts no more components than one with a few."""
    def count(contexts):
        nodes = [make_node(f"N{c}{s}", context=f"C{c}", subcontext=f"S{s}")
                 for c in range(contexts) for s in range(4)]
        return sum(1 for _ in walk(
            render_rating_distribution(compute_rating_distribution(nodes))))
    assert count(8) == count(1)
    assert count(8) < 20


# A stand-in for the page, just enough to reach the script's fill through the
# Analyze tab's MutationObserver the way the browser does.
_DRIVER = r"""
const fs = require('node:fs');
class El {
    constructor(tag) { this.tag = tag; this.attrs = {}; this.kids = []; this.open = false; }
    setAttribute(k, v) { this.attrs[k] = v; }
    appendChild(c) { this.kids.push(c); c.parent = this; }
    get textContent() { return this.kids.map(k => k.textContent).join(''); }
    all() { return this.kids.flatMap(k => k instanceof El ? [k, ...k.all()] : []); }
    closest(tag) { let e = this; while (e && e.tag !== tag) e = e.parent; return e; }
    get writes() { return this._writes || 0; }
    replaceChildren(...kids) { this._writes = this.writes + 1; this.kids = []; kids.forEach(k => this.appendChild(k)); }
    getAttribute() { return this.tree; }
    querySelectorAll(sel) {
        const names = this.all().filter(e => e.attrs.class === 'rd-name');
        return sel.includes('[open]') ? names.filter(n => n.closest('details').open) : names;
    }
}
const group = name => ['details', {}, [['summary', {}, [['span', {'class': 'rd-name'}, [name]]]]]];
const holder = new El('div');
holder.tree = JSON.stringify([group('<img src=x onerror=boom()>'), group('Body')]);
const pane = {querySelectorAll: () => [holder]};
let observed = null;
global.MutationObserver = class {
    constructor(fn) { this.fn = fn; }
    observe(target, options) { observed = {fn: this.fn, options}; }
    disconnect() {}
};
global.requestAnimationFrame = () => {};
global.window = {addEventListener() {}};
global.document = {
    readyState: 'complete',
    documentElement: {classList: {contains: () => false}},
    addEventListener() {},
    getElementById: () => pane,
    querySelectorAll: () => [],
    createElement: tag => new El(tag),
    createTextNode: data => ({textContent: data}),
};
(0, eval)(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
const names = () => holder.querySelectorAll('.rd-name');
out.first = names().map(n => n.textContent);
out.elements = holder.all().map(e => e.tag);
observed.fn();
out.writesWhenUnchanged = holder.writes;
names()[1].closest('details').open = true;
holder.tree = JSON.stringify([group('New'), group('Body')]);
observed.fn();
out.second = names().map(n => n.textContent);
out.open = names().filter(n => n.closest('details').open).map(n => n.textContent);
out.watches = observed.options.attributeFilter;
console.log(JSON.stringify(out));
"""


def test_the_script_builds_the_rows_and_keeps_a_context_open(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node isn't installed")
    driver = tmp_path / "driver.js"
    driver.write_text(_DRIVER, encoding="utf-8")
    done = subprocess.run([node, str(driver), str(asset_file("rating_dist.js"))],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    # A name that looks like markup is text: no img element comes of it.
    assert out['first'] == ['<img src=x onerror=boom()>', 'Body']
    assert set(out['elements']) == {'details', 'summary', 'span'}
    assert out['writesWhenUnchanged'] == 1
    assert out['second'] == ['New', 'Body']
    assert out['open'] == ['Body']
    assert out['watches'] == ['data-tree']
