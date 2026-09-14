"""Browser contract for the Analyze tab's first visible chart frame.

Analyze prewarms while its tab is ``display:none``. Plotly gives each hidden
graph a 700 px fallback SVG, then ``responsive=True`` corrects it after the
tab opens. Without a reveal gate, that fallback gets one visible frame and the
top-left chart visibly jumps. ``assets/analyze_first_paint.js`` hides only the
graph drawings, resizes them against the visible columns, and then reveals
them.
"""

from pathlib import Path
import shutil
import subprocess

import pytest


def _run_contract(script):
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the Analyze first-paint contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "analyze_first_paint.js"
    harness = r'''
const assert = require('node:assert/strict');

const frames = [];
global.requestAnimationFrame = fn => { frames.push(fn); return frames.length; };
global.flushFrame = () => {
    const current = frames.splice(0);
    current.forEach(fn => fn());
};

const observers = [];
global.MutationObserver = class {
    constructor(fn) { this.fn = fn; this.target = null; }
    observe(target) { this.target = target; observers.push(this); }
    disconnect() { this.target = null; }
};

function notifyPane(record) {
    observers.forEach(observer => {
        if (observer.target === pane) observer.fn([record]);
    });
}

function classList() {
    const values = new Set();
    return {
        add(value) { values.add(value); },
        remove(value) { values.delete(value); },
        contains(value) { return values.has(value); },
    };
}

const svg = {width: '700'};
const plot = {
    querySelector(selector) { return selector === '.main-svg' ? svg : null; },
};
const wrapper = {};
const pane = {
    style: {display: 'none'},
    clientWidth: 0,
    classList: classList(),
    querySelectorAll(selector) {
        if (selector === '.dash-graph') return this.hasGraphs ? [wrapper] : [];
        if (selector === '.js-plotly-plot') return this.hasPlots ? [plot] : [];
        return [];
    },
    hasGraphs: true,
    hasPlots: true,
};

global.document = {
    readyState: 'complete',
    documentElement: {},
    getElementById(id) { return id === 'analyze-tab-content' ? pane : null; },
    addEventListener() {},
};

let resizeCallCount = 0;
global.window = {
    Plotly: {Plots: {resize(target) {
        assert.equal(target, plot);
        resizeCallCount += 1;
        svg.width = String(pane.clientWidth);
        return Promise.resolve();
    }}},
};

global.openTab = () => {
    pane.style.display = 'block';
    pane.clientWidth = 536;
    notifyPane({type: 'attributes', target: pane});
};
global.closeTab = () => {
    pane.style.display = 'none';
    pane.clientWidth = 0;
    notifyPane({type: 'attributes', target: pane});
};
global.mountGraph = () => {
    pane.hasGraphs = true;
    pane.hasPlots = true;
    notifyPane({type: 'childList', target: pane, addedNodes: [{
        nodeType: 1,
        matches(selector) { return selector === '.dash-graph'; },
        querySelector() { return null; },
    }]});
};
global.pane = pane;
global.svg = svg;
global.resizeCalls = () => resizeCallCount;

require(process.argv[1]);
'''
    async_script = """
;(async () => {
%s
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
""" % script
    result = subprocess.run(
        [node_binary, "-e", harness + async_script, str(asset)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_hidden_fallback_is_gated_until_the_visible_width_lands():
    _run_contract(r'''
openTab();

assert.equal(svg.width, '700', 'the hidden Plotly fallback still exists');
assert.equal(pane.classList.contains('analyze-is-sizing'), true,
    'the graph is hidden in the same task that reveals the tab');

flushFrame();
assert.equal(resizeCalls(), 1);
assert.equal(svg.width, '536', 'Plotly resized against the visible pane');
assert.equal(pane.classList.contains('analyze-is-sizing'), true,
    'the drawing remains gated until the resize promise settles');

await new Promise(resolve => setImmediate(resolve));
flushFrame();
assert.equal(pane.classList.contains('analyze-is-sizing'), false,
    'the first visible chart frame already has the correct width');
''')


def test_opening_before_the_graph_mounts_gates_it_when_it_arrives():
    _run_contract(r'''
pane.hasGraphs = false;
pane.hasPlots = false;
openTab();
assert.equal(pane.classList.contains('analyze-is-sizing'), false,
    'the loading cover remains responsible while there is no graph');

mountGraph();
assert.equal(pane.classList.contains('analyze-is-sizing'), true,
    'a graph mounted into the visible tab is gated before paint');

flushFrame();
await new Promise(resolve => setImmediate(resolve));
flushFrame();
assert.equal(svg.width, '536');
assert.equal(pane.classList.contains('analyze-is-sizing'), false);
''')


def test_leaving_mid_resize_cancels_the_gate():
    _run_contract(r'''
openTab();
assert.equal(pane.classList.contains('analyze-is-sizing'), true);

closeTab();
assert.equal(pane.classList.contains('analyze-is-sizing'), false,
    'a hidden tab cannot be stranded in a sizing state');

flushFrame();
assert.equal(resizeCalls(), 0, 'the stale visible-width job was cancelled');
''')


def test_css_hides_only_graph_drawings_while_they_are_sized():
    css = (Path(__file__).resolve().parents[1] / "assets" / "theme.css").read_text()
    rule = "#analyze-tab-content.analyze-is-sizing .dash-graph"
    assert rule in css
    assert "visibility: hidden" in css[css.index(rule):css.index(rule) + 160]
