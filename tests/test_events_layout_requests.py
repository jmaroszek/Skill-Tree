"""Browser contract for Events layout request de-duplication."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_events_position_echo_does_not_start_a_second_layout():
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the Events layout contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "events_layout.js"
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
    getElementById: id => id === 'events-detail-graph'
        ? {_cyreg: {cy: currentCy}}
        : null
};
require(process.argv[1]);
const build = window.dash_clientside.skillTreeEventsLayout.build;
const moveGraph = [
    {data: {id: 'A', dormant: 1}},
    {data: {id: 'B', dormant: 0}},
    {data: {id: 'A_B_Needs_Hard', source: 'A', target: 'B', type: 'Needs_Hard'}}
];
function request(trigger, elements = moveGraph, event = 'Move',
                 frozen = false, animate = true) {
    window.dash_clientside.callback_context.triggered = [
        {prop_id: `${trigger}.value`}
    ];
    return build(50, 0.25, 4500, animate, 0, elements, frozen, event);
}

const first = request('events-detail-graph');
assert.equal(first.name, 'fcose');
assert.equal(first.quality, 'proof');
assert.equal(first.animate, true);
assert.equal(first.randomize, true);
assert.equal(first.skillTreeRequestId, 1);

// Cytoscape's echo adds positions and keeps data, but not a new topology.
const echoed = moveGraph.map(element => ({
    ...element,
    position: element.data.source === undefined ? {x: 10, y: 20} : undefined
}));
assert.equal(request('events-detail-graph', echoed), 'NO');

// A different event produces the same options apart from the request id, so
// the id is what makes dash-cytoscape run a layout for it at all.
const jobGraph = [
    {data: {id: 'C', dormant: 1}},
    {data: {id: 'D', dormant: 0}},
    {data: {id: 'C_D_Needs_Soft', source: 'C', target: 'D', type: 'Needs_Soft'}}
];
const second = request('events-detail-graph', jobGraph, 'Job');
const {skillTreeRequestId: firstId, ...firstOptions} = first;
const {skillTreeRequestId: secondId, ...secondOptions} = second;
assert.deepEqual(secondOptions, firstOptions);
assert(secondId > firstId);
assert.equal(request('events-detail-graph', jobGraph, 'Job'), 'NO');

// Returning to an earlier event is a new view again.
assert.equal(request('events-detail-graph', moveGraph, 'Move').randomize, true);

// Adding a dormant node to the open event nudges the existing layout.
const grown = [
    ...moveGraph,
    {data: {id: 'E', dormant: 1}},
    {data: {id: 'E_A_Needs_Hard', source: 'E', target: 'A', type: 'Needs_Hard'}}
];
const incremental = request('events-detail-graph', grown);
assert.equal(incremental.randomize, false);
assert(incremental.skillTreeRequestId > secondId);
assert.equal(request('events-detail-graph', grown), 'NO');

// A replacement Cytoscape instance has no positions for an identical graph.
currentCy = {instance: 2};
window.cyReady(currentCy);
assert.equal(request('events-detail-graph', grown).randomize, true);
assert.equal(request('events-detail-graph', grown), 'NO');

// Slider changes still re-run the current graph without reseeding it.
const slider = request('events-graph-settings-edge-length', grown);
assert.equal(slider.randomize, false);

// Turning the animate toggle off still means no motion.
assert.equal(request('events-graph-settings-animate', grown, 'Move', false, false).animate, false);

// Frozen canvases ignore element updates; Settle bypasses the freeze.
assert.equal(request('events-detail-graph', [...grown, {data: {id: 'F'}}], 'Move', true), 'NO');
const settled = request('events-graph-settings-relayout', grown, 'Move', true);
assert.equal(settled.randomize, true);
assert.equal(window.allowed, 'events');
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
