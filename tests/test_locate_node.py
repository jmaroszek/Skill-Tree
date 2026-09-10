"""Regression tests for "Locate on graph".

Two defects motivated these. The button wrote `main-tabs.active_tab` even when
already on the canvas, and Dash re-fires dependents on any write — so every
click dragged core_engine's full scoring + generate_elements cycle into the
middle of the 1.45 s pulse. And the pulse's own animations queued behind
now_pulse.js's endless border loop on a Now node, where `stop(clearQueue)`
could discard the contract half along with the callback that cleared the
inline size, stranding the node at three times its width.
"""

from pathlib import Path
import inspect
import shutil
import subprocess

import dash
import pytest

import callbacks


def _locate_callback():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    key = next(k for k in app.callback_map if "locate-message.children" in k
               and "locate-animate-trigger.data" in k)
    fn = app.callback_map[key]["callback"]
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


_TAB_SLOT = 3
_TRIGGER_SLOT = 4


@pytest.fixture
def locate_node(monkeypatch):
    """A non-dormant node that manager.get_node resolves for any name."""
    class _Node:
        dormant = False

    monkeypatch.setattr(callbacks.manager, "get_node", lambda name: _Node())
    return _Node


def test_locate_does_not_rewrite_the_tab_it_is_already_on(locate_node):
    fn = _locate_callback()
    assert len(inspect.signature(fn).parameters) == 3

    result = fn(1, "Some Node", "tab-canvas")
    assert result[_TAB_SLOT] is dash.no_update
    # The pulse still has to be told to run.
    assert result[_TRIGGER_SLOT] == 1


def test_locate_still_switches_from_another_tab(locate_node):
    fn = _locate_callback()
    result = fn(1, "Some Node", "tab-details")
    assert result[_TAB_SLOT] == "tab-canvas"
    assert result[_TRIGGER_SLOT] == 1


def test_dormant_node_reports_instead_of_pulsing(monkeypatch):
    class _Dormant:
        dormant = True

    monkeypatch.setattr(callbacks.manager, "get_node", lambda name: _Dormant())
    fn = _locate_callback()
    message, interval_disabled, _n, tab, trigger = fn(1, "Asleep", "tab-canvas")
    assert "dormant" in message
    assert interval_disabled is False
    assert tab is dash.no_update
    assert trigger is dash.no_update


def test_pulse_survives_a_forced_stop_and_runs_concurrently():
    """Browser contract for assets/locate_node.js.

    Drives a fake Cytoscape node that behaves like the real one on the two
    points that broke: animate() honours `queue`, and stop(clearQueue) drops
    queued animations without running their `complete`.
    """
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the locate pulse contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "locate_node.js"
    script = r'''
const assert = require('node:assert/strict');

// Minimal stand-in for a Cytoscape node. `queued` mirrors the real rule:
// animate() queues behind a running animation unless queue===false, and
// stop(clearQueue) throws the queue away without calling complete.
function makeNode(id) {
    return {
        classes: new Set(),
        styles: {},
        running: [],
        queued: [],
        _w: 30,
        _h: 30,
        id: () => id,
        width() { return this.styles.width !== undefined ? this.styles.width : this._w; },
        height() { return this.styles.height !== undefined ? this.styles.height : this._h; },
        addClass(c) { this.classes.add(c); },
        removeClass(c) { this.classes.delete(c); },
        removeStyle(name) { delete this.styles[name]; },
        animate(props, opts) {
            const ani = {props, opts};
            if (this.running.length && opts.queue !== false) this.queued.push(ani);
            else this.running.push(ani);
        },
        // Run every animation currently in flight to completion.
        flush() {
            const inflight = this.running.splice(0, this.running.length);
            for (const ani of inflight) {
                Object.assign(this.styles, ani.props.style);
                if (ani.opts.complete) ani.opts.complete();
            }
        },
        stop(clearQueue) {
            if (clearQueue) this.queued.length = 0;
            this.running.length = 0;
        }
    };
}

// Timers fire in time order, as the browser would run them.
const timers = [];
let clock = 0;
global.setTimeout = (fn, ms) => { timers.push({fn, at: clock + ms}); return timers.length; };
global.clearTimeout = handle => { if (timers[handle - 1]) timers[handle - 1].cancelled = true; };
function runTimers(upToMs) {
    let next;
    while ((next = timers
        .filter(t => !t.cancelled && !t.done && t.at <= upToMs)
        .sort((a, b) => a.at - b.at)[0])) {
        next.done = true;
        clock = next.at;
        next.fn();
    }
    clock = upToMs;
}

const node = makeNode('Target');
global.window = {SkillTree: {}};
global.document = {getElementById: () => ({_cyreg: {cy: {getElementById: () => node}}})};
require(process.argv[1]);

// now_pulse.js keeps an endless border animation on a Now node. The locate
// pulse has to overlap it rather than wait its turn behind it in the queue.
node.animate({style: {'border-width': 7}}, {duration: 1000, complete: () => {}});
assert.equal(node.running.length, 1);

window.locateNodeOnGraph('Target');
runTimers(50);

assert.equal(node.queued.length, 0, 'expand must not be queued');
assert.equal(node.running.length, 2, 'expand must run alongside the border pulse');
assert.equal(node.classes.has('locate-pulse'), true);
assert.equal(window.SkillTree.isLocating('cytoscape-graph', 'Target'), true);

node.flush();
assert.equal(node.styles.width, 90, 'expanded to 3x');

// now_pulse.js is told to leave a locating node alone, but any other
// stop(clearQueue) — or an interrupted contract — must not strand the size.
node.stop(true);
runTimers(2100);

assert.equal(node.styles.width, undefined, 'inline width cleared');
assert.equal(node.styles.height, undefined, 'inline height cleared');
assert.equal(node.classes.has('locate-pulse'), false);
assert.equal(window.SkillTree.isLocating('cytoscape-graph', 'Target'), false);
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
