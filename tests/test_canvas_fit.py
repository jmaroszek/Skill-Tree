"""Contract for assets/canvas_fit.js: a layout's fit lands even on a hidden tab.

Cytoscape fits against the canvas size it has cached, and at 0x0 the fit does
nothing. View Details from a context menu opens the Details tab and selects the
node in one step, so the layout could start before Cytoscape noticed the tab
had a size, and the graph drew in the canvas's top-left corner. Explain
Priority lays Details out while its tab is still hidden, with the same result
once the tab opens.
"""

from pathlib import Path
import shutil
import subprocess

import pytest


def _run_contract(script):
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the canvas fit contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "canvas_fit.js"
    harness = r'''
const assert = require('node:assert/strict');

// A MutationObserver stand-in that delivers synchronously, as the real one
// does in the task that reveals the tab.
const mutationObservers = [];
global.MutationObserver = class {
    constructor(fn) { this.fn = fn; this.targets = []; mutationObservers.push(this); }
    observe(target) { this.targets.push(target); }
    disconnect() { this.targets = []; }
};
global.ResizeObserver = undefined;

const body = {};
const pane = {parentElement: body, style: {display: 'none'}};
const canvas = {parentElement: pane, clientWidth: 0, clientHeight: 0};

// Reveal and hide the tab the way toggle_tab_content does.
global.openTab = () => {
    pane.style.display = 'flex';
    canvas.clientWidth = 1200;
    canvas.clientHeight = 500;
    mutationObservers.forEach(mo => { if (mo.targets.includes(pane)) mo.fn([]); });
};
global.closeTab = () => {
    pane.style.display = 'none';
    canvas.clientWidth = 0;
    canvas.clientHeight = 0;
    mutationObservers.forEach(mo => { if (mo.targets.includes(pane)) mo.fn([]); });
};

// The pieces of Cytoscape this module touches. `calls` records resize, the
// layout reaching Cytoscape, and each fit with its padding, in order.
global.makeCy = () => {
    const cy = {
        calls: [],
        runs: [],
        container: () => canvas,
        resize() { cy.calls.push('resize'); },
        fit(eles, padding) { cy.calls.push('fit:' + padding); },
        layout(options) {
            cy.calls.push('layout');
            const handlers = {};
            const run = {
                one(name, fn) { (handlers[name] = handlers[name] || []).push(fn); },
                stop() { (handlers.layoutstop || []).splice(0).forEach(fn => fn()); },
            };
            cy.runs.push(run);
            return run;
        },
    };
    return cy;
};
global.fits = cy => cy.calls.filter(call => call.startsWith('fit'));

const cytoHandlers = [];
global.document = {
    readyState: 'complete',
    body,
    addEventListener: () => {},
};
global.window = {
    SkillTree: {
        canvases: [{key: 'details', cytoscapeId: 'details-mini-graph'}],
        onCytoReady(selector, fn) { cytoHandlers.push(fn); },
    },
};
global.attachCy = cy => { cytoHandlers.forEach(fn => fn(cy)); return cy; };

require(process.argv[1]);
'''
    result = subprocess.run(
        [node_binary, "-e", harness + script, str(asset)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_every_layout_refreshes_the_cached_size_first():
    """The tab opened moments ago and Cytoscape's own refresh is 100 ms out."""
    _run_contract(r'''
const cy = attachCy(makeCy());
openTab();
cy.layout({fit: true, padding: 20}).stop();
assert.deepEqual(cy.calls, ['resize', 'layout']);
''')


def test_a_layout_on_a_hidden_tab_is_framed_when_the_tab_opens():
    _run_contract(r'''
const cy = attachCy(makeCy());
cy.layout({fit: true, padding: 20}).stop();
assert.deepEqual(fits(cy), [], 'nothing to fit into yet');

openTab();
assert.deepEqual(fits(cy), ['fit:20'], 'framed in the revealing task');
const i = cy.calls.lastIndexOf('fit:20');
assert.equal(cy.calls[i - 1], 'resize', 'against the size it has now');

closeTab();
openTab();
assert.deepEqual(fits(cy), ['fit:20'], 'paid once');
''')


def test_a_tab_opened_mid_layout_is_framed_when_the_layout_stops():
    """Framing the positions halfway through the tween would be wrong."""
    _run_contract(r'''
const cy = attachCy(makeCy());
const run = cy.layout({fit: true, padding: 20});
openTab();
assert.deepEqual(fits(cy), []);
run.stop();
assert.deepEqual(fits(cy), ['fit:20']);
''')


def test_a_later_layout_that_can_fit_cancels_the_debt():
    _run_contract(r'''
const cy = attachCy(makeCy());
const hidden = cy.layout({fit: true, padding: 20});
openTab();
cy.layout({fit: true, padding: 20}).stop();
hidden.stop();
assert.deepEqual(fits(cy), [], 'the newer layout frames itself');
''')


def test_returning_to_a_framed_tab_keeps_the_viewport():
    """Only a debt moves the viewport, so a user's pan and zoom survive."""
    _run_contract(r'''
const cy = attachCy(makeCy());
openTab();
cy.layout({fit: true, padding: 20}).stop();
closeTab();
openTab();
assert.deepEqual(fits(cy), []);
''')


def test_a_layout_that_asks_for_no_fit_owes_none():
    _run_contract(r'''
const cy = attachCy(makeCy());
cy.layout({fit: false}).stop();
openTab();
assert.deepEqual(fits(cy), []);
''')
