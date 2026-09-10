"""Browser contract for the Details deferred-release gate.

The subtasks table and Time Simulation both wait on `layoutstop`, which
Cytoscape emits only once every per-node animation the layout started has
completed. Anything that stops one of those animations instead of completing
it swallows the event — `now_pulse.js` force-stopping a Now node's animations
was one such path — and the panels then wait on a signal that can never
arrive. The deadline below is what keeps that from being permanent.
"""

from pathlib import Path
import shutil
import subprocess

import pytest


HARNESS = r'''
const assert = require('node:assert/strict');

// Timers fire in time order, as the browser would run them.
const timers = [];
let clock = 0;
global.setTimeout = (fn, ms) => { timers.push({fn, at: clock + ms}); return timers.length; };
global.clearTimeout = h => { if (timers[h - 1]) timers[h - 1].cancelled = true; };
function advanceTo(ms) {
    let next;
    while ((next = timers
        .filter(t => !t.cancelled && !t.done && t.at <= ms)
        .sort((a, b) => a.at - b.at)[0])) {
        next.done = true;
        clock = next.at;
        next.fn();
    }
    clock = ms;
}

const written = {};
function makeInput(id) {
    return {id, _value: '', dispatchEvent() { return true; }};
}
const inputs = {
    'details-layout-settled-trigger-input': makeInput('table'),
    'details-simulation-settled-trigger-input': makeInput('sim')
};
global.Event = class { constructor(type) { this.type = type; } };
global.document = {getElementById: id => inputs[id] || null};

const handlers = {};
const cy = {on: (name, fn) => { (handlers[name] = handlers[name] || []).push(fn); }};

global.window = {
    SkillTree: {onCytoReady: (_sel, cb) => cb(cy)},
    HTMLInputElement: {prototype: {}}
};
Object.defineProperty(window.HTMLInputElement.prototype, 'value', {
    set(v) { this._value = v; written[this.id] = v; }
});

require(process.argv[1]);
const fire = (name, layout) => handlers[name].forEach(fn => fn({layout}));
const rootOf = key => written[key] ? JSON.parse(written[key]).root : null;
function reset() { delete written.table; delete written.sim; }
'''


def _run(body):
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the deferred-release contract")
    asset = (Path(__file__).resolve().parents[1]
             / "assets" / "details_deferred_subtasks.js")
    result = subprocess.run(
        [node_binary, "-e", HARNESS + body, str(asset)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    return result


def test_settled_layout_releases_both_panels():
    _run(r'''
window.SkillTree._detailsLayoutRoot = 'Root';
const layout = {};
fire('layoutstart', layout);
fire('layoutstop', layout);
advanceTo(200);
assert.equal(rootOf('table'), 'Root');
assert.equal(rootOf('sim'), 'Root');
''')


def test_a_swallowed_layoutstop_still_releases_on_the_deadline():
    """The regression: a Now node's animations being stopped mid-layout meant
    layoutstop never fired, and both panels waited on it forever."""
    _run(r'''
window.SkillTree._detailsLayoutRoot = 'Root';
fire('layoutstart', {});
// No layoutstop ever arrives.
advanceTo(2000);
assert.equal(written.table, undefined, 'must not release early');
assert.equal(written.sim, undefined);

advanceTo(5000);
assert.equal(rootOf('table'), 'Root', 'deadline must release the table');
assert.equal(rootOf('sim'), 'Root', 'deadline must release the simulation');
''')


def test_deadline_does_not_fire_again_after_a_normal_settle():
    _run(r'''
window.SkillTree._detailsLayoutRoot = 'Root';
const layout = {};
fire('layoutstart', layout);
fire('layoutstop', layout);
advanceTo(200);
assert.equal(rootOf('table'), 'Root');
reset();
advanceTo(9000);
assert.equal(written.table, undefined, 'deadline was already cancelled');
assert.equal(written.sim, undefined);
''')


def test_deadline_release_is_rejected_once_the_root_moved_on():
    _run(r'''
window.SkillTree._detailsLayoutRoot = 'Root';
fire('layoutstart', {});
// The user picks something else; that selection's own layout will release it.
window.SkillTree._detailsLayoutRoot = 'Other';
advanceTo(9000);
assert.equal(written.table, undefined);
assert.equal(written.sim, undefined);
''')


def test_same_root_relayout_releases_simulation_but_not_the_table():
    _run(r'''
window.SkillTree._detailsLayoutRoot = 'Root';
const first = {};
fire('layoutstart', first);
fire('layoutstop', first);
advanceTo(200);
assert.equal(rootOf('table'), 'Root');
reset();

// A filter change re-lays out the same root: the table is already correct.
const second = {};
fire('layoutstart', second);
fire('layoutstop', second);
advanceTo(400);
assert.equal(rootOf('sim'), 'Root');
assert.equal(written.table, undefined);
''')


def test_superseded_layout_generation_is_ignored():
    _run(r'''
window.SkillTree._detailsLayoutRoot = 'Root';
const stale = {};
fire('layoutstart', stale);
const current = {};
fire('layoutstart', current);
// The older layout finishes late; it must not release anything.
fire('layoutstop', stale);
advanceTo(300);
assert.equal(written.table, undefined);
assert.equal(written.sim, undefined);

fire('layoutstop', current);
advanceTo(600);
assert.equal(rootOf('table'), 'Root');
''')
