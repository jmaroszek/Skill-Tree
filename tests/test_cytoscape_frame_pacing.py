"""Browser contract for assets/cytoscape_frame_pacing.js.

The tests run the module under Node against a stand-in for Cytoscape's render
loop. The stand-in keeps the loop's order: a tick draws only if a redraw was
requested before it, runs the tick callbacks (the animation step among them),
draws, then clears the request. Each tick carries its frame stamp, as
requestAnimationFrame's does, and performance.now() reads when the tick runs.
A tick after a long task runs well after its stamp.
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
let runsAt = 0;
global.performance = {now: () => runsAt};

// Cytoscape's renderer, reduced to what its render loop does each tick.
function fakeRenderer(drawMs = 1, frameMs = 1000 / 60) {
    let stamp = 0;
    const r = {
        beforeRenderPriorities: {animations: 400, eleCalcs: 300, eleTxrDeq: 200,
                                 lyrTxrDeq: 150, lyrTxrSkip: 100},
        beforeRenderCallbacks: [],
        requestedFrame: false,
        draws: 0,
        destroyed: false,
        // Running animations, each with the steps it has left.
        moving: [],
        // Each step that moved something: its stamp, and whether its tick drew.
        steps: [],
        nodes: [0, 1, 2].map(() => ({measured: 0, boundingBox() { this.measured += 1; }})),
        // How often each node had been measured when each draw began.
        measuredAtDraw: [],
        beforeRender(fn, priority) {
            this.beforeRenderCallbacks.push({fn, priority});
            this.beforeRenderCallbacks.sort((a, b) => b.priority - a.priority);
        },
        redraw() { this.requestedFrame = true; },
        render() {
            this.draws += 1;
            this.measuredAtDraw.push(this.nodes.map(node => node.measured));
        }
    };
    r.cy = {
        _private: {aniEles: r.moving},
        renderer: () => r,
        nodes: () => r.nodes,
        animated: () => false
    };
    // Cytoscape's animation step. The core registers it when it starts,
    // before any canvas module sees the renderer. A paused animation stays in
    // the pool, but nothing moves and no redraw is asked for.
    r.beforeRender(function stepAll(willDraw, now) {
        const playing = r.moving.filter(animation => !animation.paused);
        if (!playing.length) return;
        playing.forEach(animation => { animation.left -= 1; });
        for (let i = r.moving.length - 1; i >= 0; i--) {
            if (r.moving[i].left <= 0) r.moving.splice(i, 1);
        }
        r.steps.push({stamp: now, drew: willDraw});
        r.redraw();
    }, r.beforeRenderPriorities.animations);
    // late: how long after its stamp the tick runs.
    r.tick = async function (late = 0) {
        stamp += frameMs;
        runsAt = stamp + late;
        if (r.requestedFrame) {
            r.beforeRenderCallbacks.forEach(cb => cb.fn(true, stamp));
            r.render();
            r.averageRedrawTime = drawMs;
            r.requestedFrame = false;
        } else {
            r.beforeRenderCallbacks.forEach(cb => cb.fn(false, stamp));
        }
        // The next frame is stamped after this one ran, and comes after this
        // one's microtasks.
        stamp += late;
        await new Promise(resolve => setTimeout(resolve, 0));
    };
    return r;
}

// An animation of `steps` steps, started as Cytoscape's play() starts one: it
// joins the pool of running animations and asks for a redraw.
function animate(r, steps) {
    r.moving.push({left: steps});
    r.redraw();
}

async function ticks(r, count) {
    for (let i = 0; i < count; i++) await r.tick();
}

// The loop ticks from the moment the canvas mounts, long before any animation.
async function paced(r) {
    pace(r.cy);
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
for (const drawMs of [1, 12]) {
    const r = fakeRenderer(drawMs);
    await paced(r);
    r.redraw();
    await ticks(r, 5);
    assert.equal(r.draws, 1);
    r.redraw();
    await ticks(r, 5);
    assert.equal(r.draws, 2);
}
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


def test_a_slow_draws_animation_steps_only_on_ticks_that_draw():
    """The ticks between slow draws used to step, and the next tick stepped
    again before anything was drawn."""
    _run(r'''
const r = fakeRenderer(12);
await paced(r);
animate(r, 10);
await ticks(r, 40);
assert.equal(r.moving.length, 0);
assert.equal(r.steps.length, 10);
assert.ok(r.steps.every(step => step.drew), JSON.stringify(r.steps));
// One draw for each step, and none once the last step has been drawn.
assert.equal(r.draws, 10);
await ticks(r, 10);
assert.equal(r.draws, 10);
''')


def test_a_slow_canvas_whose_step_moves_nothing_goes_idle():
    """A paused animation stays in Cytoscape's pool without moving anything.
    Once nothing else moves, the ticks must stop asking for slow draws."""
    _run(r'''
const r = fakeRenderer(12);
await paced(r);
animate(r, 4);
r.moving.push({left: 1, paused: true});
await ticks(r, 20);
assert.equal(r.moving.length, 1);
const settled = r.draws;
await ticks(r, 10);
assert.equal(r.draws, settled);
assert.equal(r.requestedFrame, false);
''')


def test_unpaced_animation_steps_by_a_stale_frame_stamp():
    _run(r'''
const r = fakeRenderer();
animate(r, 5);
// A layout computed for 300 ms before its tween's first frame.
await r.tick(300);
assert.ok(r.steps[0].stamp <= performance.now() - 300, JSON.stringify(r.steps));
''')


def test_a_tween_starts_its_clock_on_its_first_frame():
    _run(r'''
const r = fakeRenderer();
await paced(r);
animate(r, 5);
await r.tick(300);
const firstFrame = performance.now();
await ticks(r, 4);
const frame = 1000 / 60;
assert.ok(r.steps[0].stamp >= firstFrame - 2 * frame - 1e-9, JSON.stringify(r.steps));
for (let i = 1; i < r.steps.length; i++) {
    assert.ok(r.steps[i].stamp > r.steps[i - 1].stamp, JSON.stringify(r.steps));
}
// Ticks on time keep their own stamps.
assert.ok(Math.abs(r.steps[1].stamp - (performance.now() - 3 * frame)) < 1e-6,
          JSON.stringify(r.steps));
''')


def test_nodes_are_measured_before_a_slow_draw():
    _run(r'''
const r = fakeRenderer(12);
await paced(r);
animate(r, 6);
await ticks(r, 14);
// The first draw comes before any draw has been timed. Each later one found
// every node measured once more.
assert.equal(r.measuredAtDraw.length, 6);
r.measuredAtDraw.forEach((counts, i) => assert.deepEqual(counts, [i, i, i]));
''')


def test_fast_draws_leave_the_nodes_alone():
    _run(r'''
const r = fakeRenderer(1);
await paced(r);
animate(r, 6);
await ticks(r, 14);
assert.ok(r.nodes.every(node => node.measured === 0));
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
pace(r.cy);
const render = r.render;
const callbacks = r.beforeRenderCallbacks.length;
const step = r.beforeRenderCallbacks.find(cb => cb.priority === 400).fn;
pace(r.cy);
assert.equal(r.render, render);
assert.equal(r.beforeRenderCallbacks.length, callbacks);
assert.equal(r.beforeRenderCallbacks.find(cb => cb.priority === 400).fn, step);
''')


def test_every_canvas_is_paced():
    _run(r'''
const selectors = window.SkillTree.canvases.map(c => '#' + c.cytoscapeId).sort();
assert.deepEqual(Object.keys(ready).sort(), selectors);
''')
