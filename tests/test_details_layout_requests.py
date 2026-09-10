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
