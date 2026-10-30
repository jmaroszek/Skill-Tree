"""Regression tests for the view-aware "Locate on graph" flow."""

import inspect
import shutil
import subprocess

import dash
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

from skilltree.services import AppServices
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.ui.canvas.callbacks import register_canvas_callbacks
from support.paths import asset_file


def _locate_callback():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_canvas_callbacks(app, AppServices())
    key = next(k for k in app.callback_map if "locate-message.children" in k
               and "locate-request-store.data" in k)
    fn = app.callback_map[key]["callback"]
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _locate_result_callback():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_canvas_callbacks(app, AppServices())
    key = next(k for k in app.callback_map if "modal-locate-missing.is_open" in k
               and "locate-missing-node-store.data" in k)
    fn = app.callback_map[key]["callback"]
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


def _call_with_trigger(fn, trigger, *args):
    token = context_value.set(AttributeDict(
        triggered_inputs=[{"prop_id": trigger, "value": 1}]))
    try:
        return fn(*args)
    finally:
        context_value.reset(token)


@pytest.fixture
def locate_node(monkeypatch):
    """A non-dormant node that manager.get_node resolves for any name."""
    class _Node:
        dormant = False

    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: _Node())
    return _Node


def test_locate_routes_the_active_tab_to_the_live_canvas(locate_node):
    fn = _locate_callback()
    assert len(inspect.signature(fn).parameters) == 3

    message, request = fn(
        1, "Some Node", "tab-details")
    assert message == ""
    assert request == {
        "name": "Some Node",
        "activeTab": "tab-details",
        "request": 1,
    }


def test_dormant_node_is_allowed_to_resolve_against_the_active_canvas(monkeypatch):
    class _Dormant:
        dormant = True

    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: _Dormant())
    fn = _locate_callback()
    _message, request = fn(1, "Asleep", "tab-events")
    assert request["name"] == "Asleep"
    assert request["activeTab"] == "tab-events"


def test_deleted_node_reports_in_editor(monkeypatch):
    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: None)
    fn = _locate_callback()
    message, request = fn(1, "Gone", "tab-canvas")
    assert message == "This node no longer exists."
    assert request is dash.no_update


def test_missing_node_opens_view_specific_fallback(locate_node):
    fn = _locate_result_callback()
    result = _call_with_trigger(
        fn, "locate-result-store.data",
        {"status": "missing", "name": "Target", "view": "events"},
        None, None, None, "tab-events",
    )
    assert result[2] is True
    assert result[3] == '“Target” is not in the Events view'
    assert result[4] == "It isn't in this event or linked to one of its nodes."
    assert result[5] == {"name": "Target"}
    assert result[6] == "View Details"


def _dormant(monkeypatch, membership):
    class _Dormant:
        dormant = True

    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: _Dormant())
    monkeypatch.setattr(EventManager, "get_node_membership",
                        lambda self, name: membership)


def test_missing_dormant_node_offers_its_event(monkeypatch):
    """Details leaves a dormant node out too, so the dialog sends it to
    the one canvas that shows it: its event's."""
    _dormant(monkeypatch, {"event": "Job Hunt", "event_status": "Pending",
                           "activation_date": None})
    fn = _locate_result_callback()
    result = _call_with_trigger(
        fn, "locate-result-store.data",
        {"status": "missing", "name": "Interview Process", "view": "main"},
        None, None, None, "tab-canvas",
    )
    assert result[2] is True
    assert result[3] == '“Interview Process” is dormant'
    assert "Job Hunt" in result[4]
    assert result[5] == {"name": "Interview Process", "event": "Job Hunt"}
    assert result[6] == "Open Event"
    assert result[7] == {}


def test_dormant_node_without_an_event_offers_nothing(monkeypatch):
    _dormant(monkeypatch, None)
    fn = _locate_result_callback()
    result = _call_with_trigger(
        fn, "locate-result-store.data",
        {"status": "missing", "name": "Stray", "view": "main"},
        None, None, None, "tab-canvas",
    )
    assert result[2] is True
    assert result[7] == {"display": "none"}


def test_open_event_selects_the_event_and_pulses_the_node(monkeypatch):
    _dormant(monkeypatch, None)
    monkeypatch.setattr(EventManager, "get_event", lambda self, name: object())
    fn = _locate_result_callback()
    result = _call_with_trigger(
        fn, "btn-locate-go.n_clicks",
        None, None, 3, {"name": "Interview Process", "event": "Job Hunt"},
        "tab-canvas",
    )
    assert result[1] == {
        "name": "Interview Process", "canvasId": "events-detail-graph",
        "request": 3,
    }
    assert result[2] is False
    assert result[8] is dash.no_update
    event, action, _stamp = result[9].split("|")
    assert (event, action) == ("Job Hunt", "edit")


def test_no_canvas_tab_navigates_to_nodes_before_pulsing():
    fn = _locate_result_callback()
    result = _call_with_trigger(
        fn, "locate-result-store.data",
        {"status": "navigate", "name": "Target", "request": 2,
         "canvasId": "cytoscape-graph", "targetTab": "tab-canvas"},
        None, None, None, "tab-next",
    )
    assert result[0] == "tab-canvas"
    assert result[1] == {
        "name": "Target", "canvasId": "cytoscape-graph", "request": 2,
    }


def test_view_details_reroots_details_and_retries_pulse(locate_node):
    fn = _locate_result_callback()
    result = _call_with_trigger(
        fn, "btn-locate-go.n_clicks",
        None, None, 4, {"name": "Target"}, "tab-events",
    )
    assert result[0] == "tab-details"
    assert result[1] == {
        "name": "Target", "canvasId": "details-mini-graph", "request": 4,
    }
    assert result[2] is False
    assert result[8] == "Target"
    assert result[9] is dash.no_update


def test_pulse_survives_a_forced_stop_and_runs_concurrently():
    """Browser contract for assets/canvas/locate_node.js.

    Drives a fake Cytoscape node that behaves like the real one on the two
    points that broke: animate() honours `queue`, and stop(clearQueue) drops
    queued animations without running their `complete`.
    """
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the locate pulse contract")

    asset = asset_file("locate_node.js")
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
        length: 1,
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
global.document = {getElementById: () => ({_cyreg: {cy: {
    getElementById: id => id === 'Target' ? node : {length: 0}
}}})};
require(process.argv[2]);  // 00_browser_bridge.js, passed in
require(process.argv[1]);

window.SkillTree.canvases = [
    {key: 'main', tabId: 'tab-canvas', cytoscapeId: 'cytoscape-graph'},
    {key: 'details', tabId: 'tab-details', cytoscapeId: 'details-mini-graph'},
    {key: 'events', tabId: 'tab-events', cytoscapeId: 'events-detail-graph'},
];
assert.equal(window.SkillTree.canvasHasNode('details-mini-graph', 'Target'), true);
assert.equal(window.SkillTree.canvasHasNode('details-mini-graph', 'Missing'), false);

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

let route = window.SkillTree.resolveLocateRequest({
    name: 'Target', activeTab: 'tab-details', request: 1
});
assert.equal(route.status, 'located');
assert.equal(route.canvasId, 'details-mini-graph');

route = window.SkillTree.resolveLocateRequest({
    name: 'Target', activeTab: 'tab-next', request: 2
});
assert.equal(route.status, 'navigate');
assert.equal(route.targetTab, 'tab-canvas');

route = window.SkillTree.resolveLocateRequest({
    name: 'Missing', activeTab: 'tab-events', request: 3
});
assert.equal(route.status, 'missing');
assert.equal(route.view, 'events');
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset), str(asset_file("00_browser_bridge.js"))],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
