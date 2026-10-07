"""Browser contract for assets/cytoscape_frame_pacing.js.

The tests run the module under Node against a stand-in for Cytoscape's render
loop. The stand-in keeps the loop's order: a tick draws only if a redraw was
requested before it, runs the tick callbacks (the animation step among them),
draws, then clears the request. Each tick carries its frame time, as
requestAnimationFrame's does.
"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from canvases import client_registry

ASSET = Path(__file__).resolve().parents[1] / 'assets' / 'cytoscape_frame_pacing.js'

HARNESS = r'''
const assert = require('node:assert/strict');
const ready = {};
global.window = {
    SkillTree: {
        canvases: __CANVASES__,
        onCytoReady: (selector, callback) => { ready[selector] = callback; }
    }
};
global.document = {readyState: 'complete'};

// Cytoscape's renderer, reduced to what its render loop does each tick.
function fakeRenderer(drawMs = 1, frameMs = 1000 / 60) {
    let clock = 0;
    const r = {
        beforeRenderPriorities: {animations: 400, eleCalcs: 300, eleTxrDeq: 200,
                                 lyrTxrDeq: 150, lyrTxrSkip: 100},
        beforeRenderCallbacks: [],
        requestedFrame: false,
        draws: 0,
        destroyed: false,
        beforeRender(fn, priority) {
            this.beforeRenderCallbacks.push({fn, priority});
            this.beforeRenderCallbacks.sort((a, b) => b.priority - a.priority);
        },
        redraw() { this.requestedFrame = true; },
        render() { this.draws += 1; }
    };
    r.tick = async function () {
        clock += frameMs;
        if (r.requestedFrame) {
            r.beforeRenderCallbacks.forEach(cb => cb.fn(true, clock));
            r.render();
            r.averageRedrawTime = drawMs;
            r.requestedFrame = false;
        } else {
            r.beforeRenderCallbacks.forEach(cb => cb.fn(false, clock));
        }
        // The next frame comes after this one's microtasks.
        await new Promise(resolve => setTimeout(resolve, 0));
    };
    return r;
}

// An animation of `steps` steps. Each step asks for a redraw, as Cytoscape's
// step does through notify('draw').
function animate(r, steps) {
    let left = steps;
    r.beforeRender(() => {
        if (left > 0) {
            left -= 1;
            r.redraw();
        }
    }, r.beforeRenderPriorities.animations);
    r.redraw();
}

async function ticks(r, count) {
    for (let i = 0; i < count; i++) await r.tick();
}

const cyOf = r => ({renderer: () => r});
// The loop ticks from the moment the canvas mounts, long before any animation.
async function paced(r) {
    pace(cyOf(r));
    await ticks(r, 5);
}
require(process.argv[1]);
const pace = window.SkillTree.paceCanvasFrames;
(async () => {
'''

TAIL = r'''
})().catch(err => { console.error(err); process.exit(1); });
'''


def _run(body):
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the frame pacing contract')
    script = HARNESS.replace('__CANVASES__', json.dumps(client_registry())) + body + TAIL
    result = subprocess.run(
        [node_binary, '-e', script, str(ASSET)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_unpaced_loop_draws_an_animation_on_every_other_tick():
    _run(r'''
const r = fakeRenderer();
animate(r, 40);
await ticks(r, 40);
assert.ok(r.draws <= 21, `drew ${r.draws} of 40 ticks`);
''')


def test_paced_loop_draws_an_animation_on_every_tick():
    _run(r'''
const r = fakeRenderer();
await paced(r);
animate(r, 40);
await ticks(r, 40);
assert.ok(r.draws >= 39, `drew ${r.draws} of 40 ticks`);
''')


def test_drawing_stops_when_the_animation_ends():
    _run(r'''
const r = fakeRenderer();
await paced(r);
animate(r, 10);
await ticks(r, 12);
const settled = r.draws;
await ticks(r, 20);
assert.equal(r.draws, settled);
assert.equal(r.requestedFrame, false);
''')


def test_a_still_graph_draws_once_per_request():
    _run(r'''
const r = fakeRenderer();
await paced(r);
r.redraw();
await ticks(r, 5);
assert.equal(r.draws, 1);
r.redraw();
await ticks(r, 5);
assert.equal(r.draws, 2);
''')


def test_a_draw_longer_than_half_a_frame_keeps_cytoscapes_pacing():
    _run(r'''
const r = fakeRenderer(12);
await paced(r);
animate(r, 40);
await ticks(r, 40);
assert.ok(r.draws <= 21, `drew ${r.draws} of 40 ticks`);
''')


def test_the_budget_follows_the_screens_frame_rate():
    _run(r'''
// 3 ms fits half a 60 Hz frame, but not half of a 240 Hz one.
const slow = fakeRenderer(3, 1000 / 60);
await paced(slow);
animate(slow, 40);
await ticks(slow, 40);
assert.ok(slow.draws >= 39, `60 Hz drew ${slow.draws} of 40 ticks`);
const fast = fakeRenderer(3, 1000 / 240);
await paced(fast);
animate(fast, 40);
await ticks(fast, 40);
assert.ok(fast.draws <= 21, `240 Hz drew ${fast.draws} of 40 ticks`);
const cheap = fakeRenderer(1, 1000 / 240);
await paced(cheap);
animate(cheap, 40);
await ticks(cheap, 40);
assert.ok(cheap.draws >= 39, `240 Hz cheap drew ${cheap.draws} of 40 ticks`);
''')


def test_a_destroyed_renderer_is_not_asked_to_draw():
    _run(r'''
const r = fakeRenderer();
await paced(r);
animate(r, 40);
await ticks(r, 2);
assert.equal(r.requestedFrame, true);
r.destroyed = true;
await r.tick();
assert.equal(r.requestedFrame, false);
''')


def test_pacing_a_canvas_twice_wraps_it_once():
    _run(r'''
const r = fakeRenderer();
pace(cyOf(r));
const render = r.render;
pace(cyOf(r));
assert.equal(r.render, render);
assert.equal(r.beforeRenderCallbacks.length, 1);
''')


def test_every_canvas_is_paced():
    _run(r'''
const selectors = window.SkillTree.canvases.map(c => '#' + c.cytoscapeId).sort();
assert.deepEqual(Object.keys(ready).sort(), selectors);
''')
