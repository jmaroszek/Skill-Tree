"""Regression tests for the Nodes-tab first paint.

The Nodes canvas mounts inside a hidden tab, so Cytoscape stacks every node at
the origin until the layout runs — about 1.6 s later on a 568-node graph,
because the layout call waits behind React's ingest of the element payload —
and `fit` does nothing while the container is 0x0. Opening the tab inside that
window drew the whole graph in the top-left corner and then jumped.

`assets/canvas_first_paint.js` holds the canvas behind an opaque cover until
the graph is both laid out and framed. Its caption goes up in the same task
that reveals the tab. An earlier 400 ms timer was starved by the very
main-thread work it was meant to explain, so arriving early showed a blank
canvas with no sign anything was happening.

The module also owns the one layout that can't be a transition. The layout prop
keeps positions and follows Smooth, because every filter change re-runs it. A
run starting from nodes stacked at the origin has no shape to keep, so it is
randomized, and it skips the animation while the cover is up.
"""

from pathlib import Path
import shutil
import subprocess

import pytest

from callbacks import register_callbacks
from layout import build_app_layout, create_graph_view


def _walk(component):
    yield component
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float)):
        yield from _walk(children)


def _ids(component):
    return [getattr(item, "id", None) for item in _walk(component)
            if getattr(item, "id", None)]


def _by_id(component, component_id):
    return next(item for item in _walk(component)
                if getattr(item, "id", None) == component_id)


def test_cover_and_its_sink_are_in_the_layout():
    layout = build_app_layout([], env="sandbox")
    ids = _ids(layout)

    assert "canvas-first-paint-cover" in ids
    assert "canvas-first-paint-sink" in ids


def test_cover_is_the_last_child_of_the_canvas_container():
    """It has to cover the overlay buttons and the layout panel, not sit under
    them — they stack above the canvas on their own z-index."""
    layout = build_app_layout([], env="sandbox")
    container = _by_id(layout, "canvas-container")

    assert container.children[-1].id == "canvas-first-paint-cover"


def test_element_payloads_reach_the_cover():
    """A graph with no nodes never runs a layout, so `layoutstop` is never
    coming and only this bridge can release the cover."""
    import dash

    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_callbacks(app)

    bridge = next(c for c in app._callback_list
                  if c["output"] == "canvas-first-paint-sink.data")

    assert [i["id"] for i in bridge["inputs"]] == ["elements-pending-store"]
    # Clientside: the payload never needs to travel back to the server, and the
    # cover has to hear about it in the same tick Cytoscape does.
    assert bridge["clientside_function"] is not None


def test_the_nodes_layout_prop_agrees_with_the_smooth_switch():
    """Filter changes re-run whatever layout prop the canvas holds, and the
    graph-settings callback only rewrites it once a control is touched. A prop
    that disagreed with the switch left Smooth showing on while every
    transition snapped."""
    view = create_graph_view([])
    graph = _by_id(view, "cytoscape-graph")
    smooth = _by_id(view, "graph-settings-animate")

    assert smooth.value is True
    assert graph.layout["animate"] is smooth.value
    # Transitions keep the current shape. The cold start from a pile at the
    # origin is randomized by assets/canvas_first_paint.js instead.
    assert graph.layout["randomize"] is False


def _run_contract(script, observers=True, mounted=True):
    """Run a browser contract for assets/canvas_first_paint.js under Node.

    With `observers`, a MutationObserver stand-in delivers the pane's style
    change synchronously, the way the real one runs in the task that reveals the
    tab and before that frame paints. Without it, only the bounded poll is left,
    as in a document that never composites.
    """
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the first-paint contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "canvas_first_paint.js"
    harness = r'''
const assert = require('node:assert/strict');
const USE_OBSERVERS = __USE_OBSERVERS__;
const MOUNTED = __MOUNTED__;

// Timers fire in time order, as the browser would run them.
const timers = [];
let clock = 0;
global.setTimeout = (fn, ms) => { timers.push({fn, at: clock + (ms || 0)}); return timers.length; };
global.clearTimeout = handle => { if (timers[handle - 1]) timers[handle - 1].cancelled = true; };
global.setInterval = (fn, ms) => { timers.push({fn, at: clock + (ms || 0), every: ms}); return timers.length; };
global.clearInterval = global.clearTimeout;
global.advance = ms => {
    const upToMs = clock + ms;
    let next;
    while ((next = timers
        .filter(t => !t.cancelled && !t.done && t.at <= upToMs)
        .sort((a, b) => a.at - b.at)[0])) {
        if (next.every) {
            // Re-arm a repeating timer before running it, the way setInterval does.
            const handle = timers.indexOf(next) + 1;
            timers.push({fn: next.fn, at: next.at + next.every, every: next.every, handle});
        }
        next.done = true;
        clock = next.at;
        if (next.handle && timers[next.handle - 1].cancelled) continue;
        next.fn();
    }
    clock = upToMs;
};

const mutationObservers = [];
global.MutationObserver = USE_OBSERVERS ? class {
    constructor(fn) { this.fn = fn; this.targets = []; mutationObservers.push(this); }
    observe(target) { this.targets.push(target); }
    disconnect() { this.targets = []; }
} : undefined;
global.ResizeObserver = undefined;

function notify(target) {
    mutationObservers.forEach(mo => { if (mo.targets.includes(target)) mo.fn([]); });
}

function makeElement(id) {
    return {
        id,
        clientWidth: 0,
        clientHeight: 0,
        classList: {
            set: new Set(),
            add(c) { this.set.add(c); },
            contains(c) { return this.set.has(c); },
        },
        style: {},
        classes() { return [...this.classList.set]; },
    };
}

global.makeNode = (x, y) => ({ position: () => ({x, y}) });

// Minimal stand-in for the pieces of Cytoscape this module touches. `layouts`
// records every options object that reaches the real cy.layout().
global.makeCy = nodes => ({
    _nodes: nodes,
    fitted: 0,
    handlers: {},
    layouts: [],
    nodes() { const list = this._nodes; return {length: list.length, some: fn => list.some(fn)}; },
    on(name, fn) { (this.handlers[name] = this.handlers[name] || []).push(fn); },
    emit(name) { (this.handlers[name] || []).forEach(fn => fn()); },
    resize() {},
    fit() { this.fitted++; },
    center() {},
    layout(options) { this.layouts.push(options); return {run() {}}; },
});

const canvas = makeElement('cytoscape-graph');
const pane = makeElement('canvas-tab-content');
const cover = makeElement('canvas-first-paint-cover');
pane.style.display = 'none';

const byId = {
    'cytoscape-graph': canvas,
    'canvas-tab-content': pane,
    'canvas-first-paint-cover': cover,
};
// Until mountCanvas(), nothing is rendered: the state the module loads into,
// since Dash renders its layout after the asset scripts run.
let mounted = MOUNTED;
global.document = {
    readyState: 'complete',
    documentElement: {},
    getElementById: id => (mounted ? byId[id] || null : null),
    addEventListener: () => {},
};
global.mountCanvas = () => {
    mounted = true;
    notify(document.documentElement);
};

// Stands in for assets/cyto_lifecycle.js: hand every handler the instance as
// soon as one exists, and again whenever dash-cytoscape swaps it.
const cytoHandlers = [];
global.window = {
    SkillTree: {
        onCytoReady(selector, fn) {
            cytoHandlers.push(fn);
            if (canvas._cyreg) fn(canvas._cyreg.cy);
        },
    },
};

// Reveal and hide the Nodes tab the way toggle_tab_content does.
global.openTab = () => {
    pane.style.display = 'flex';
    canvas.clientWidth = 1200;
    canvas.clientHeight = 700;
    notify(pane);
};
global.closeTab = () => {
    pane.style.display = 'none';
    canvas.clientWidth = 0;
    canvas.clientHeight = 0;
    notify(pane);
};

global.attachCy = cy => {
    canvas._cyreg = {cy};
    cytoHandlers.forEach(fn => fn(cy));
};
global.canvas = canvas;
global.cover = cover;
global.pane = pane;

require(process.argv[1]);
'''.replace("__USE_OBSERVERS__", "true" if observers else "false").replace("__MOUNTED__", "true" if mounted else "false")
    result = subprocess.run(
        [node_binary, "-e", harness + script, str(asset)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


# --- The cover ---------------------------------------------------------------

def test_a_graph_ready_before_the_reveal_lifts_without_a_spinner():
    """The common path: the layout settled while the tab was still hidden, so
    opening it must show the framed graph and nothing else."""
    _run_contract(r'''
// Laid out while hidden — the positions are already away from the origin.
attachCy(makeCy([makeNode(0, 0), makeNode(140, -60)]));
advance(500);

assert.equal(cover.classes().length, 0,
    'the cover stays up, captionless, while nothing can be framed');

openTab();

// Lifted by the reveal's own observer callback, before that frame paints.
assert.equal(cover.classList.contains('is-lifted'), true, 'lifted in the reveal task');
assert.equal(cover.classList.contains('is-lifting'), false,
    'no cross-fade over a cover nobody saw');
assert.equal(cover.classList.contains('is-waiting'), false, 'no caption flash');
assert.equal(canvas._cyreg.cy.fitted, 1, 'framed exactly once');
''')


def test_arriving_early_shows_the_caption_with_the_tab():
    """The caption must not wait on a timer. The wait it explains is main-thread
    work, and a timer can't fire during it — due at 400 ms, it fired at 915 ms,
    and arriving just before the payload was ingested pushed it past the layout
    entirely, leaving a blank canvas."""
    _run_contract(r'''
// Elements have landed but the layout has not run: every node at the origin.
const cy = makeCy([makeNode(0, 0), makeNode(0, 0)]);
attachCy(cy);

openTab();

// No clock advance at all.
assert.equal(cover.classList.contains('is-waiting'), true, 'caption shown in the reveal task');
assert.equal(cover.classList.contains('is-lifted'), false, 'nothing to show yet');
assert.equal(cy.fitted, 0, 'must not frame a graph that is still stacked');

advance(3000);
cy._nodes = [makeNode(-220, 90), makeNode(310, -40)];
cy.emit('layoutstop');

assert.equal(cy.fitted, 1, 'framed as soon as the layout settled');
assert.equal(cover.classList.contains('is-lifting'), true, 'an on-screen cover cross-fades');
assert.equal(cover.classList.contains('is-lifted'), false, 'not yet — mid-fade');

advance(300);
assert.equal(cover.classList.contains('is-lifted'), true, 'gone once the fade ends');
''')


def test_returning_after_the_layout_settled_lifts_instantly():
    """Open early, leave, come back once the graph is ready: the returning
    reveal has painted nothing of the cover, so there is nothing to fade."""
    _run_contract(r'''
const cy = makeCy([makeNode(0, 0)]);
attachCy(cy);

openTab();
assert.equal(cover.classList.contains('is-waiting'), true);

closeTab();
cy._nodes = [makeNode(80, 20)];
cy.emit('layoutstop');
assert.equal(cover.classList.contains('is-lifted'), false,
    'settled while hidden, with no size to frame against');

openTab();
assert.equal(cover.classList.contains('is-lifted'), true, 'lifted in the reveal task');
assert.equal(cover.classList.contains('is-lifting'), false, 'without a fade');
''')


def test_without_observers_the_poll_still_picks_up_the_reveal():
    _run_contract(r'''
attachCy(makeCy([makeNode(0, 0)]));

openTab();
assert.equal(cover.classList.contains('is-waiting'), false, 'nothing runs until the poll');

advance(100);
assert.equal(cover.classList.contains('is-waiting'), true, 'the poll picks the reveal up');
''', observers=False)


def test_a_graph_with_no_nodes_releases_the_cover():
    """No nodes means no layout and no `layoutstop`; the element payload is the
    only signal that the canvas is as ready as it will ever be."""
    _run_contract(r'''
attachCy(makeCy([]));
openTab();
advance(600);

assert.equal(cover.classList.contains('is-lifted'), false, 'still waiting on a signal');

window.SkillTree.notifyCanvasElements([]);
advance(300);
assert.equal(cover.classList.contains('is-lifted'), true, 'empty payload lifts the cover');
''')


def test_the_empty_mount_time_layout_is_not_mistaken_for_the_graph():
    """dash-cytoscape runs the layout prop once at mount, over no elements. That
    `layoutstop` says nothing about the payload still on its way."""
    _run_contract(r'''
const cy = makeCy([]);
attachCy(cy);
cy.emit('layoutstop');

openTab();
assert.equal(cover.classList.contains('is-lifted'), false, 'no payload has arrived yet');
assert.equal(cover.classList.contains('is-waiting'), true);
''')


def test_a_payload_with_nodes_does_not_release_the_cover_early():
    _run_contract(r'''
const cy = makeCy([makeNode(0, 0)]);
attachCy(cy);
openTab();

window.SkillTree.notifyCanvasElements([
    {data: {id: 'A'}},
    {data: {id: 'B'}},
    {data: {id: 'A->B', source: 'A', target: 'B'}},
]);
advance(900);

assert.equal(cover.classList.contains('is-lifted'), false,
    'nodes still have to be laid out before the cover can lift');
assert.equal(cy.fitted, 0);

cy.emit('layoutstop');
advance(300);
assert.equal(cover.classList.contains('is-lifted'), true);
''')


def test_the_cover_lifts_even_when_the_canvas_never_gets_a_size():
    """A stranded cover is worse than an unframed graph, so the backstop is
    unconditional — and it is timed from the reveal, not from page load."""
    _run_contract(r'''
attachCy(makeCy([makeNode(0, 0)]));
pane.style.display = 'flex';   // opened, but the canvas never resolves a size
advance(14000);

assert.equal(cover.classList.contains('is-lifted'), false, 'still inside the grace period');

advance(2000);
assert.equal(cover.classList.contains('is-lifted'), true, 'backstop released the canvas');
''')


def test_a_closed_tab_never_starts_the_backstop_clock():
    _run_contract(r'''
attachCy(makeCy([makeNode(0, 0)]));
advance(60000);

assert.equal(cover.classes().length, 0,
    'a tab nobody opened is a tab nobody is waiting on');
''')


def test_later_payloads_never_re_cover_the_canvas():
    """Filter changes re-run the layout for the life of the session. Covering
    the graph the user is looking at would be worse than any transition."""
    _run_contract(r'''
const cy = makeCy([makeNode(120, 40)]);
attachCy(cy);
openTab();
assert.equal(cover.classList.contains('is-lifted'), true);

const framedOnce = cy.fitted;
window.SkillTree.notifyCanvasElements([]);
cy._nodes = [makeNode(0, 0)];
cy.emit('layoutstop');
advance(2000);

assert.equal(cover.classList.contains('is-lifting'), false, 'no second cover');
assert.equal(cy.fitted, framedOnce, 'and no second fit stealing the viewport');
''')


def test_a_reveal_right_after_the_canvas_mounts_is_caught_in_its_task():
    """Dash renders the layout after the module loads. Waiting for the canvas on
    a timer left a window in which the tab could open with nothing watching it,
    so the caption waited on the poll. An observer attaches as soon as the
    canvas is inserted."""
    _run_contract(r'''
mountCanvas();
attachCy(makeCy([makeNode(0, 0)]));

// No clock advance between the mount and the reveal.
openTab();
assert.equal(cover.classList.contains('is-waiting'), true, 'caption shown in the reveal task');
''', mounted=False)


# --- The cold-start layout ---------------------------------------------------

def test_the_cold_start_randomizes_without_animating():
    """Incremental from a pile at the origin, fCoSE left 547 of 568 sandbox
    nodes within 12 px of a neighbor; a randomized seed left none. Animating
    that run behind the cover would only hold the cover up another second."""
    _run_contract(r'''
const cy = makeCy([makeNode(0, 0), makeNode(0, 0)]);
attachCy(cy);

cy.layout({name: 'fcose', animate: true, randomize: false, animationDuration: 1000}).run();

const first = cy.layouts[0];
assert.equal(first.randomize, true, 'a pile has no shape to keep');
assert.equal(first.animate, false, 'nobody can watch it glide behind the cover');
assert.equal(first.animationDuration, 1000, 'the rest of the prop passes through');
''')


def test_transitions_and_settle_keep_the_layout_prop():
    _run_contract(r'''
const cy = makeCy([makeNode(-40, 10), makeNode(90, 60)]);
attachCy(cy);

const filterChange = {name: 'fcose', animate: true, randomize: false};
cy.layout(filterChange).run();
assert.deepEqual(cy.layouts[0], filterChange, 'keeps positions and follows Smooth');

const settle = {name: 'fcose', animate: true, randomize: true};
cy.layout(settle).run();
assert.deepEqual(cy.layouts[1], settle, 'Settle still reshuffles');

const smoothOff = {name: 'fcose', animate: false, randomize: false};
cy.layout(smoothOff).run();
assert.deepEqual(cy.layouts[2], smoothOff, 'Smooth off still snaps');
''')


def test_a_cold_start_after_first_paint_animates_its_arrival():
    """Filters that emptied the graph and then brought nodes back leave every
    node at the origin again. It still has to randomize, but the cover is gone,
    so Smooth applies."""
    _run_contract(r'''
const cy = makeCy([makeNode(40, 40)]);
attachCy(cy);
openTab();
assert.equal(cover.classList.contains('is-lifted'), true);

cy._nodes = [makeNode(0, 0), makeNode(0, 0)];
cy.layout({name: 'fcose', animate: true, randomize: false}).run();

const arrival = cy.layouts[cy.layouts.length - 1];
assert.equal(arrival.randomize, true);
assert.equal(arrival.animate, true, 'with the cover gone, Smooth applies');
''')


def test_the_empty_graph_layout_passes_through():
    _run_contract(r'''
const cy = makeCy([]);
attachCy(cy);

const prop = {name: 'fcose', animate: true, randomize: false};
cy.layout(prop).run();
assert.deepEqual(cy.layouts[0], prop);
''')
