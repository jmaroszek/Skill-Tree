"""Regression tests for the view-aware "Locate on graph" flow."""

import inspect
import shutil
import subprocess

import dash
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

from skilltree.domain.models import STATUS_DONE
from skilltree.services import AppServices
from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager
from skilltree.ui.canvas.callbacks import register_canvas_callbacks
from support.graphs import make_node
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
        "event": None,
    }


def test_dormant_node_request_names_its_event(monkeypatch):
    class _Dormant:
        dormant = True

    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: _Dormant())
    monkeypatch.setattr(EventManager, "get_node_membership",
                        lambda self, name: {"event": "Job Hunt"})
    fn = _locate_callback()
    _message, request = fn(1, "Asleep", "tab-canvas")
    assert request["name"] == "Asleep"
    assert request["event"] == "Job Hunt"


def test_deleted_node_reports_in_editor(monkeypatch):
    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: None)
    fn = _locate_callback()
    message, request = fn(1, "Gone", "tab-canvas")
    assert message == "This node no longer exists."
    assert request is dash.no_update


# The result callback's outputs, in order.
TAB, ANIMATE, IS_OPEN, TITLE, BODY, STORE, LABEL, STYLE, EVENT, REVEAL, DONE, DORMANT = range(12)


def _result(trigger, result=None, go=None, hidden=None, sidebar=None,
            community="All", method="louvain"):
    fn = _locate_result_callback()
    return _call_with_trigger(fn, trigger, result, None, go, hidden,
                              sidebar or {}, community, method)


def _missing(monkeypatch, node, **kwargs):
    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: node)
    return _result("locate-result-store.data",
                   {"status": "missing", "name": node.name, "view": "main",
                    "targetTab": "tab-canvas"}, **kwargs)


def test_dormant_node_goes_straight_to_its_event(monkeypatch):
    monkeypatch.setattr(EventManager, "get_event", lambda self, name: object())
    result = _result("locate-result-store.data",
                     {"status": "event", "name": "Interview Process",
                      "event": "Job Hunt", "request": 3})
    assert result[IS_OPEN] is False
    assert result[ANIMATE] == {
        "name": "Interview Process", "canvasId": "events-detail-graph",
        "request": 3,
    }
    event, action, _stamp = result[EVENT].split("|")
    assert (event, action) == ("Job Hunt", "edit")


def test_done_node_offers_show_done(monkeypatch, temp_database):
    result = _missing(monkeypatch, make_node("Finished", status=STATUS_DONE))
    # The dialog opens where Locate ran; a tab switch with it closed it.
    assert result[TAB] is dash.no_update
    assert result[IS_OPEN] is True
    assert result[TITLE] == "“Finished” is hidden on the Nodes canvas"
    assert result[BODY] == "It's Done, and Show Done is off."
    assert result[LABEL] == "Show Done"
    assert result[STORE] == {"name": "Finished", "reveal": {"show_done": True},
                             "targetTab": "tab-canvas"}


def test_filtered_node_offers_clear_filters(monkeypatch, temp_database):
    result = _missing(monkeypatch, make_node("Elsewhere"),
                      sidebar={"types": ["Goal"]})
    assert result[BODY] == "Filters are hiding it."
    assert result[LABEL] == "Clear Filters"
    assert result[STORE]["reveal"] == {
        "clear": True, "show_done": False, "show_dormant": False}


def test_done_and_filtered_node_clears_filters_and_shows_done(monkeypatch, temp_database):
    result = _missing(monkeypatch, make_node("Both", status=STATUS_DONE),
                      sidebar={"types": ["Goal"]})
    assert result[BODY] == "It's Done, and filters hide it too."
    assert result[STORE]["reveal"]["show_done"]


def test_clearing_filters_keeps_show_done_on_for_a_done_node(monkeypatch, temp_database):
    """Clear Filters turns Show Done off, which would hide the node again."""
    result = _missing(monkeypatch, make_node("Shown", status=STATUS_DONE),
                      sidebar={"types": ["Goal"], "done": ["show_done"]})
    assert result[BODY] == "Filters are hiding it."
    assert result[STORE]["reveal"]["show_done"] is True


def test_a_chosen_community_counts_as_a_filter(monkeypatch, temp_database):
    result = _missing(monkeypatch, make_node("Outside"), community="Cluster 2")
    assert result[LABEL] == "Clear Filters"


def test_node_no_filter_hides_offers_nothing(monkeypatch, temp_database):
    result = _missing(monkeypatch, make_node("Plain"))
    assert result[STORE]["reveal"] is None
    assert result[STYLE] == {"display": "none"}


def test_show_done_flips_the_switch_and_pulses_on_nodes(locate_node):
    result = _result("btn-locate-go.n_clicks", go=4,
                     hidden={"name": "Target", "reveal": {"show_done": True},
                             "targetTab": "tab-canvas"})
    assert result[TAB] == "tab-canvas"
    assert result[IS_OPEN] is False
    assert result[DONE] == ["show_done"]
    assert result[REVEAL] is dash.no_update
    assert result[ANIMATE] == {
        "name": "Target", "canvasId": "cytoscape-graph", "request": 4,
    }


def test_clear_filters_goes_through_the_clear_filters_callback(locate_node):
    reveal = {"clear": True, "show_done": True, "show_dormant": False}
    result = _result("btn-locate-go.n_clicks", go=5,
                     hidden={"name": "Target", "reveal": reveal})
    # Clear Filters resets Show Done too, so it applies the whole reveal:
    # a separate write here could land before the reset.
    assert result[DONE] is dash.no_update
    assert result[REVEAL] == {**reveal, "request": 5}


def test_navigating_to_an_unloaded_nodes_canvas_checks_the_filters(monkeypatch, temp_database):
    """A Nodes canvas not loaded yet can't say a node is hidden; the filters can."""
    monkeypatch.setattr(GraphManager, "get_node",
                        lambda self, name: make_node(name, status=STATUS_DONE))
    result = _result("locate-result-store.data",
                     {"status": "navigate", "name": "Target", "request": 2,
                      "canvasId": "cytoscape-graph", "targetTab": "tab-canvas"})
    assert result[TAB] is dash.no_update
    assert result[IS_OPEN] is True
    assert result[LABEL] == "Show Done"


def test_no_canvas_tab_navigates_to_nodes_before_pulsing(monkeypatch, temp_database):
    monkeypatch.setattr(GraphManager, "get_node", lambda self, name: make_node(name))
    result = _result("locate-result-store.data",
                     {"status": "navigate", "name": "Target", "request": 2,
                      "canvasId": "cytoscape-graph", "targetTab": "tab-canvas"})
    assert result[TAB] == "tab-canvas"
    assert result[ANIMATE] == {
        "name": "Target", "canvasId": "cytoscape-graph", "request": 2,
    }


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

// Missing from the open canvas: Locate looks on Nodes, never Details.
route = window.SkillTree.resolveLocateRequest({
    name: 'Missing', activeTab: 'tab-events', request: 3
});
assert.equal(route.status, 'missing');
assert.equal(route.view, 'main');
assert.equal(route.targetTab, 'tab-canvas');

// A dormant node goes to its event when the open canvas lacks it.
route = window.SkillTree.resolveLocateRequest({
    name: 'Missing', activeTab: 'tab-canvas', request: 4, event: 'Job Hunt'
});
assert.equal(route.status, 'event');
assert.equal(route.event, 'Job Hunt');

// Already on the open canvas: pulse in place, wherever its event is.
route = window.SkillTree.resolveLocateRequest({
    name: 'Target', activeTab: 'tab-events', request: 5, event: 'Job Hunt'
});
assert.equal(route.status, 'located');
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset), str(asset_file("00_browser_bridge.js"))],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
