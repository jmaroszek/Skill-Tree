"""Browser contract for Details layout selection and request de-duplication."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_position_echo_does_not_start_a_second_layout():
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the Details layout contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "details_layout.js"
    script = r'''
const assert = require('node:assert/strict');
global.window = {
    dash_clientside: {no_update: 'NO', callback_context: {triggered: []}},
    SkillTree: {
        allowOneLayout: id => { window.allowed = id; },
        onCytoReady: (_selector, callback) => { window.cyReady = callback; }
    }
};
let currentCy = {instance: 1};
global.document = {
    getElementById: id => id === 'details-mini-graph'
        ? {_cyreg: {cy: currentCy}}
        : null
};
require(process.argv[1]);
const build = window.dash_clientside.skillTreeDetailsLayout.build;
const nodes = [
    {data: {id: 'A', label: 'Alpha'}},
    {data: {id: 'B', label: 'Beta', details_root: true}},
    {data: {id: 'A_B_Needs_Hard', source: 'A', target: 'B', type: 'Needs_Hard'}}
];
function request(trigger, elements = nodes, root = 'B', frozen = false) {
    window.dash_clientside.callback_context.triggered = [
        {prop_id: `${trigger}.data`}
    ];
    return build(50, 0.25, 4500, true, 0, elements, frozen, root);
}

const first = request('details-mini-graph');
assert.equal(first.name, 'cose');
assert.equal(first.randomize, true);
assert.equal(first.skillTreeRequestId, 1);
// CoSE's animate:true repaints the running physics and skips the first 250 ms,
// so a subtree this small finished before anything reached the screen. 'end'
// tweens start -> final, the same motion fCoSE animates through.
assert.equal(first.animate, 'end');
assert.equal(first.animationDuration, 1000);

// Cytoscape's echo changes positions and ordinary display data, not topology.
const echoed = nodes.map(element => ({
    ...element,
    data: {...element.data, color: '#fff'},
    position: {x: 10, y: 20}
}));
assert.equal(request('details-mini-graph', echoed), 'NO');

// A replacement Cytoscape instance has no positions even when its graph is
// identical. Its first update must be treated as a new randomized layout.
currentCy = {instance: 2};
window.cyReady(currentCy);
assert.equal(request('details-mini-graph', echoed).randomize, true);
assert.equal(request('details-mini-graph', echoed), 'NO');

// A real same-root topology change still gets one incremental layout.
const changed = [
    ...nodes,
    {data: {id: 'C'}},
    {data: {id: 'C_B_Needs_Hard', source: 'C', target: 'B', type: 'Needs_Hard'}}
];
const incremental = request('details-mini-graph', changed);
assert.equal(incremental.randomize, false);
assert(incremental.skillTreeRequestId > first.skillTreeRequestId);
assert.equal(request('details-mini-graph', changed), 'NO');

// A new root is detected from the elements even when Dash State is one render
// behind. It is a new view even if the topology itself is identical.
const rerooted = changed.map(element => ({
    ...element,
    data: {
        ...element.data,
        details_root: element.data.id === 'A'
    }
}));
const rerootedLayout = request('details-mini-graph', rerooted, 'B');
assert.equal(rerootedLayout.randomize, true);
assert(rerootedLayout.skillTreeRequestId > incremental.skillTreeRequestId);

// Larger subtrees retain fCoSE, where its speed advantage matters.
const large = Array.from({length: 25}, (_, index) => ({
    data: {id: `large-${index}`, details_root: index === 0}
}));
const largeLayout = request('details-mini-graph', large, 'Large');
assert.equal(largeLayout.name, 'fcose');
assert.equal(largeLayout.quality, 'proof');
assert.equal(largeLayout.randomize, true);
// fCoSE has no 'end' mode: true already means "tween to the final positions".
assert.equal(largeLayout.animate, true);
assert.equal(largeLayout.animationDuration, 1000);

// Turning the animate toggle off must still mean no motion, both sizes.
window.dash_clientside.callback_context.triggered = [{prop_id: 'details-mini-graph.data'}];
assert.equal(build(50, 0.25, 4500, false, 0, [...large, {data: {id: 'extra'}}], false, 'Large').animate, false);
window.dash_clientside.callback_context.triggered = [{prop_id: 'details-mini-graph.data'}];
assert.equal(build(50, 0.25, 4500, false, 0, [...nodes, {data: {id: 'extra2'}}], false, 'B').animate, false);

// Explicit Settle keeps its forced randomized pass and freeze bypass.
const settled = request('details-graph-settings-relayout', rerooted, 'A', true);
assert.equal(settled.randomize, true);
assert.equal(window.allowed, 'details');
assert.equal(request('details-mini-graph', [...changed, {data: {id: 'D'}}], 'A', true), 'NO');
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_payload_that_starts_no_layout_releases_the_simulation():
    """The regression: adding a filter context with no nodes in the selected
    subtree left Time Simulation on "Calculating…" for good. The graph came
    back unchanged, so no layout ran and no settle signal was ever sent."""
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the Details layout contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "details_layout.js"
    script = r'''
const assert = require('node:assert/strict');
let settling = false;
global.window = {
    dash_clientside: {no_update: 'NO', callback_context: {triggered: []}},
    SkillTree: {
        onCytoReady: () => {},
        detailsLayoutSettling: () => settling
    }
};
let currentCy = {instance: 1};
global.document = {
    getElementById: id => id === 'details-mini-graph'
        ? {_cyreg: {cy: currentCy}}
        : null
};
require(process.argv[1]);
const api = window.dash_clientside.skillTreeDetailsLayout;
const nodes = [
    {data: {id: 'A', label: 'Alpha'}},
    {data: {id: 'B', label: 'Beta', details_root: true}},
    {data: {id: 'A_B_Needs_Hard', source: 'A', target: 'B', type: 'Needs_Hard'}}
];
function layOut(elements, root = 'B') {
    window.dash_clientside.callback_context.triggered = [
        {prop_id: 'details-mini-graph.elements'}
    ];
    return api.build(50, 0.25, 4500, true, 0, elements, false, root);
}
function released(pending, frozen = false, root = 'B') {
    const token = api.settleUnchanged(pending, frozen, root);
    return token === 'NO' ? null : JSON.parse(token).root;
}

// Nothing is on screen yet, so the first payload will be laid out.
assert.equal(released(nodes), null);
assert.notEqual(layOut(nodes), 'NO');

// The same subtree again, with only display data changed: no layout will run,
// and build() agrees.
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

// A real topology change is compared before build() records it, and is left
// to its own layout.
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
currentCy = {instance: 2};
assert.equal(released(changed), null);

// No selection means no simulation to release.
assert.equal(released([], false, null), null);
assert.equal(released(null), null);
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
