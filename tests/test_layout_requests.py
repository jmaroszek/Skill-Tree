"""Browser contract for assets/layout_requests.js.

Every canvas's Graph Layout callback returns the layout prop this module
builds. These tests run it under Node against the canvas registry the page
receives.
"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from canvases import client_registry

ASSET = Path(__file__).resolve().parents[1] / 'assets' / 'layout_requests.js'

HARNESS = r'''
const assert = require('node:assert/strict');
let settling = false;
const cyReady = {};
const liveCy = {};
global.window = {
    dash_clientside: {no_update: 'NO', callback_context: {triggered: []}},
    SkillTree: {
        canvases: __CANVASES__,
        allowOneLayout: key => { window.allowed = key; },
        onCytoReady: (selector, callback) => { cyReady[selector] = callback; },
        detailsLayoutSettling: () => settling
    }
};
global.document = {
    getElementById: id => liveCy[id] ? {_cyreg: {cy: liveCy[id]}} : null
};
// A Cytoscape stand-in whose layout() records the options each run received.
function fakeCy(nodeCount = 0) {
    const cy = {
        runs: [],
        nodes: () => ({length: nodeCount}),
        layout(options) { cy.runs.push(options); return {run() {}}; }
    };
    return cy;
}
require(process.argv[1]);
const api = window.dash_clientside.skillTreeLayout;
const canvas = key => window.SkillTree.canvases.find(c => c.key === key);
function trigger(id, prop = 'value') {
    window.dash_clientside.callback_context.triggered = [{prop_id: `${id}.${prop}`}];
}
'''


def _run(body):
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the layout request contract')
    script = HARNESS.replace('__CANVASES__', json.dumps(client_registry())) + body
    result = subprocess.run(
        [node_binary, '-e', script, str(ASSET)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_details_position_echo_does_not_start_a_second_layout():
    _run(r'''
const details = canvas('details');
liveCy[details.cytoscapeId] = fakeCy(2);
const nodes = [
    {data: {id: 'A', label: 'Alpha'}},
    {data: {id: 'B', label: 'Beta', details_root: true}},
    {data: {id: 'A_B_Needs_Hard', source: 'A', target: 'B', type: 'Needs_Hard'}}
];
function request(id, elements = nodes, root = 'B', frozen = false, animate = true) {
    trigger(id, 'elements');
    return api.details(50, 0.25, 4500, animate, 0, elements, frozen, root);
}

const first = request(details.cytoscapeId);
assert.equal(first.name, 'cose');
assert.equal(first.randomize, true);
assert.equal(first.skillTreeRequestId, 1);
assert.equal(first.animate, true);
assert.equal(first.skillTreeTween, true);
assert.equal(first.animationDuration, 1000);

// Cytoscape's echo changes positions and ordinary display data, not topology.
const echoed = nodes.map(element => ({
    ...element,
    data: {...element.data, color: '#fff'},
    position: {x: 10, y: 20}
}));
assert.equal(request(details.cytoscapeId, echoed), 'NO');

// A replacement Cytoscape instance has no positions even when its graph is
// identical. Its first update must be treated as a new randomized layout.
liveCy[details.cytoscapeId] = fakeCy(2);
cyReady['#' + details.cytoscapeId](liveCy[details.cytoscapeId]);
assert.equal(request(details.cytoscapeId, echoed).randomize, true);
assert.equal(request(details.cytoscapeId, echoed), 'NO');

// A real same-root topology change still gets one incremental layout.
const changed = [
    ...nodes,
    {data: {id: 'C'}},
    {data: {id: 'C_B_Needs_Hard', source: 'C', target: 'B', type: 'Needs_Hard'}}
];
const incremental = request(details.cytoscapeId, changed);
assert.equal(incremental.randomize, false);
assert(incremental.skillTreeRequestId > first.skillTreeRequestId);
assert.equal(request(details.cytoscapeId, changed), 'NO');

// A new root is detected from the elements even when Dash State is one render
// behind. It is a new view even if the topology itself is identical.
const rerooted = changed.map(element => ({
    ...element,
    data: {...element.data, details_root: element.data.id === 'A'}
}));
const rerootedLayout = request(details.cytoscapeId, rerooted, 'B');
assert.equal(rerootedLayout.randomize, true);
assert(rerootedLayout.skillTreeRequestId > incremental.skillTreeRequestId);
assert.equal(window.SkillTree.layoutRoot('details'), 'A');

// Larger subtrees keep fCoSE, whose animate:true already tweens to the end.
const large = Array.from({length: 25}, (_, index) => ({
    data: {id: `large-${index}`, details_root: index === 0}
}));
const largeLayout = request(details.cytoscapeId, large, 'Large');
assert.equal(largeLayout.name, 'fcose');
assert.equal(largeLayout.quality, 'proof');
assert.equal(largeLayout.randomize, true);
assert.equal(largeLayout.animate, true);
assert.equal(largeLayout.skillTreeTween, undefined);

// Turning Smooth off must still mean no motion, at both sizes.
assert.equal(request(details.cytoscapeId, [...large, {data: {id: 'extra'}}],
                     'Large', false, false).animate, false);
const still = request(details.cytoscapeId, [...nodes, {data: {id: 'extra2'}}],
                      'B', false, false);
assert.equal(still.animate, false);
assert.equal(still.skillTreeTween, undefined);

// Explicit Settle keeps its forced randomized pass and freeze bypass.
const settled = request(details.settleButtonId, rerooted, 'A', true);
assert.equal(settled.randomize, true);
assert.equal(window.allowed, 'details');
assert.equal(request(details.cytoscapeId, [...changed, {data: {id: 'D'}}], 'A', true), 'NO');
''')


def test_payload_that_starts_no_layout_releases_the_simulation():
    """The regression: adding a filter context with no nodes in the selected
    subtree left Time Simulation on "Calculating…" for good. The graph came
    back unchanged, so no layout ran and no settle signal was ever sent."""
    _run(r'''
const details = canvas('details');
liveCy[details.cytoscapeId] = fakeCy(2);
const nodes = [
    {data: {id: 'A', label: 'Alpha'}},
    {data: {id: 'B', label: 'Beta', details_root: true}},
    {data: {id: 'A_B_Needs_Hard', source: 'A', target: 'B', type: 'Needs_Hard'}}
];
function layOut(elements, root = 'B') {
    trigger(details.cytoscapeId, 'elements');
    return api.details(50, 0.25, 4500, true, 0, elements, false, root);
}
function released(pending, frozen = false, root = 'B') {
    const token = api.settleUnchanged(pending, frozen, root);
    return token === 'NO' ? null : JSON.parse(token).root;
}

// Nothing is on screen yet, so the first payload will be laid out.
assert.equal(released(nodes), null);
assert.notEqual(layOut(nodes), 'NO');

// The same subtree again, with only display data changed: no layout will run,
// and the layout request agrees.
const redrawn = nodes.map(element => ({
    ...element, data: {...element.data, color: '#fff'}
}));
assert.equal(released(redrawn), 'B');
assert.equal(layOut(redrawn), 'NO');

// An earlier layout still settling will release the simulation itself.
settling = true;
assert.equal(released(redrawn), null);
settling = false;

// A frozen canvas bypasses the gate, so there is nothing to release.
assert.equal(released(redrawn, true), null);

// A real topology change is compared before the request records it, and is
// left to its own layout.
const changed = [...nodes, {data: {id: 'C'}}];
assert.equal(released(changed), null);
assert.notEqual(layOut(changed), 'NO');
assert.equal(released(changed), 'B');

// The same nodes under a different root are a new view with its own layout.
const rerooted = changed.map(element => ({
    ...element,
    data: {...element.data, details_root: element.data.id === 'A'}
}));
assert.equal(released(rerooted), null);

// A replacement Cytoscape instance lays out even an identical payload.
liveCy[details.cytoscapeId] = fakeCy(3);
assert.equal(released(changed), null);

// No selection means no simulation to release.
assert.equal(released([], false, null), null);
assert.equal(released(null), null);
''')


def test_events_position_echo_does_not_start_a_second_layout():
    _run(r'''
const events = canvas('events');
liveCy[events.cytoscapeId] = fakeCy(2);
const moveGraph = [
    {data: {id: 'A', dormant: 1}},
    {data: {id: 'B', dormant: 0}},
    {data: {id: 'A_B_Needs_Hard', source: 'A', target: 'B', type: 'Needs_Hard'}}
];
function request(id, elements = moveGraph, event = 'Move', frozen = false, animate = true) {
    trigger(id);
    return api.events(50, 0.25, 4500, animate, 0, elements, frozen, event);
}

const first = request(events.cytoscapeId);
assert.equal(first.name, 'cose');
assert.equal(first.animate, true);
assert.equal(first.skillTreeTween, true);
assert.equal(first.animationDuration, 1000);
assert.equal(first.randomize, true);
assert.equal(first.skillTreeRequestId, 1);

// Cytoscape's echo adds positions and keeps data, but not a new topology.
const echoed = moveGraph.map(element => ({
    ...element,
    position: element.data.source === undefined ? {x: 10, y: 20} : undefined
}));
assert.equal(request(events.cytoscapeId, echoed), 'NO');

// A different event produces the same options apart from the request id, so
// the id is what makes dash-cytoscape run a layout for it at all.
const jobGraph = [
    {data: {id: 'C', dormant: 1}},
    {data: {id: 'D', dormant: 0}},
    {data: {id: 'C_D_Needs_Soft', source: 'C', target: 'D', type: 'Needs_Soft'}}
];
const second = request(events.cytoscapeId, jobGraph, 'Job');
const {skillTreeRequestId: firstId, ...firstOptions} = first;
const {skillTreeRequestId: secondId, ...secondOptions} = second;
assert.deepEqual(secondOptions, firstOptions);
assert(secondId > firstId);
assert.equal(request(events.cytoscapeId, jobGraph, 'Job'), 'NO');

// Returning to an earlier event is a new view again.
assert.equal(request(events.cytoscapeId, moveGraph, 'Move').randomize, true);

// Adding a dormant node to the open event nudges the existing layout.
const grown = [
    ...moveGraph,
    {data: {id: 'E', dormant: 1}},
    {data: {id: 'E_A_Needs_Hard', source: 'E', target: 'A', type: 'Needs_Hard'}}
];
const incremental = request(events.cytoscapeId, grown);
assert.equal(incremental.randomize, false);
assert(incremental.skillTreeRequestId > secondId);
assert.equal(request(events.cytoscapeId, grown), 'NO');

// A replacement Cytoscape instance has no positions for an identical graph.
liveCy[events.cytoscapeId] = fakeCy(3);
cyReady['#' + events.cytoscapeId](liveCy[events.cytoscapeId]);
assert.equal(request(events.cytoscapeId, grown).randomize, true);
assert.equal(request(events.cytoscapeId, grown), 'NO');

// Slider changes still re-run the current graph without reseeding it.
assert.equal(request('events-graph-settings-edge-length', grown).randomize, false);

// Turning Smooth off still means no motion.
assert.equal(request('events-graph-settings-animate', grown, 'Move', false, false).animate, false);

// Frozen canvases ignore element updates; Settle bypasses the freeze.
assert.equal(request(events.cytoscapeId, [...grown, {data: {id: 'F'}}], 'Move', true), 'NO');
const settled = request(events.settleButtonId, grown, 'Move', true);
assert.equal(settled.randomize, true);
assert.equal(window.allowed, 'events');

const large = Array.from({length: 39}, (_, i) => ({data: {id: 'N' + i}}));
const largeLayout = request(events.cytoscapeId, large, 'Video');
assert.equal(largeLayout.name, 'fcose');
assert.equal(largeLayout.quality, 'proof');
assert.equal(largeLayout.animate, true);
assert.equal(largeLayout.animationDuration, 1000);
assert.equal(largeLayout.numIter, 975);
assert.equal(request(events.cytoscapeId, large, 'Video'), 'NO');
''')


def test_nodes_requests_leave_element_updates_to_auto_refresh():
    _run(r'''
const main = canvas('main');
assert.equal(main.laysOutElements, false);
liveCy[main.cytoscapeId] = fakeCy(5);

trigger(main.settleButtonId, 'n_clicks');
const settle = api.main(120, 0, 50000, true, 1, false);
// The whole graph keeps fCoSE and its full iteration budget at every size.
assert.equal(settle.name, 'fcose');
assert.equal(settle.numIter, 2500);
assert.equal(settle.padding, 30);
assert.equal(settle.animate, true);
assert.equal(settle.randomize, true);
assert.equal(window.allowed, 'main');

trigger('graph-settings-edge-length');
const slider = api.main(130, 0, 50000, true, 1, false);
assert.equal(slider.randomize, false);
assert.equal(slider.idealEdgeLength, 130);
assert(slider.skillTreeRequestId > settle.skillTreeRequestId);

// Empty controls fall back to this canvas's own physics.
trigger('graph-settings-repulsion');
const fallback = api.main(null, null, null, false, 1, false);
assert.deepEqual(
    [fallback.idealEdgeLength, fallback.nodeRepulsion, fallback.gravity, fallback.animate],
    [100, 50000, 0, false]);
''')


def test_freeze_holds_control_changes_until_the_freeze_off_layout():
    """Turning freeze off used to run one hard-coded fCoSE pass on every
    canvas. Each canvas's own request now lays it out, with the controls that
    changed while it was frozen."""
    _run(r'''
function call(c, {edgeLength = 100, gravity = 0.25, repulsion = 4500, frozen = false} = {}) {
    // A frozen canvas can show elements the prop never received.
    const stale = [{data: {id: 'stale'}}];
    return c.laysOutElements
        ? api[c.key](edgeLength, gravity, repulsion, true, 0, stale, frozen, null)
        : api[c.key](edgeLength, gravity, repulsion, true, 0, frozen);
}
for (const c of window.SkillTree.canvases) {
    liveCy[c.cytoscapeId] = fakeCy(30);
    trigger(c.freezeStoreId, 'data');
    assert.equal(call(c, {frozen: true}), 'NO', c.key);
    trigger(c.settleButtonId.replace(/relayout$/, 'edge-length'));
    assert.equal(call(c, {edgeLength: 80, frozen: true}), 'NO', c.key);

    trigger(c.freezeStoreId, 'data');
    const thawed = call(c, {edgeLength: 80, gravity: 0.4, repulsion: 6000});
    assert.equal(thawed.idealEdgeLength, 80, c.key);
    assert.equal(thawed.gravity, 0.4, c.key);
    assert.equal(thawed.nodeRepulsion, 6000, c.key);
    assert.equal(thawed.randomize, false, c.key);
    // Sized by the 30 nodes on screen, not the one-node prop.
    assert.equal(thawed.name, 'fcose', c.key);
}
''')


def test_cose_tween_reaches_cytoscape_without_breaking_the_prop_type():
    """dash-cytoscape declares layout.animate a boolean. In debug mode Dash's
    prop check tore the Details and Events canvases down over the string 'end'
    their small views requested."""
    _run(r'''
const events = canvas('events');
const cy = fakeCy(2);
liveCy[events.cytoscapeId] = cy;
const graph = [{data: {id: 'A'}}, {data: {id: 'B'}}];

trigger(events.cytoscapeId, 'elements');
const smooth = api.events(50, 0.25, 4500, true, 0, graph, false, 'Move');
assert.equal(typeof smooth.animate, 'boolean');
assert.equal(smooth.skillTreeTween, true);
// dash-cytoscape starts every layout through cy.layout().
cy.layout(smooth);
assert.equal(cy.runs[0].animate, 'end');

trigger(events.cytoscapeId, 'elements');
const still = api.events(50, 0.25, 4500, false, 0, [...graph, {data: {id: 'C'}}], false, 'Move');
assert.equal(still.animate, false);
cy.layout(still);
assert.equal(cy.runs[1].animate, false);

// Layouts the app didn't request pass through untouched.
cy.layout({name: 'cose', animate: true, skillTreeTween: true});
assert.equal(cy.runs[2].animate, true);
''')


def test_a_settle_randomizes_only_its_own_run():
    """autoRefreshLayout re-runs the Nodes prop on every add or remove. After a
    Settle that prop said randomize: true, so every later filter change
    reshuffled the whole graph."""
    _run(r'''
const main = canvas('main');
const cy = fakeCy(10);
liveCy[main.cytoscapeId] = cy;

trigger(main.settleButtonId, 'n_clicks');
const settle = api.main(100, 0, 50000, true, 1, false);
cy.layout(settle);  // the Settle itself
cy.layout(settle);  // re-runs after filter changes
cy.layout(settle);
assert.deepEqual(cy.runs.map(run => run.randomize), [true, false, false]);

// The next Settle is randomized again.
trigger(main.settleButtonId, 'n_clicks');
cy.layout(api.main(100, 0, 50000, true, 2, false));
assert.equal(cy.runs[3].randomize, true);
''')
