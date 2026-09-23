"""The startup cover: the app stays covered until it can act on what it shows.

The Home tab is in the initial layout, so it painted half a second after load,
while about 85 startup callbacks kept Dash busy for roughly five more seconds.
Inside that window a click on a Home row was held behind the cascade or
dropped when the table was rebuilt, and the Node Editor's search opened empty,
because its options arrive with the core engine's first payload.

`layout.build_index_string` paints a cover before Dash renders anything, and
`assets/startup_cover.js` lifts it once that payload has landed and Dash has
then had nothing pending for a quiet window, confirmed at idle.
"""
from pathlib import Path
import re
import shutil
import subprocess

import dash
import pytest

from config import LOADING_SPINNER_STYLE
from layout import build_index_string


DASH_PLACEHOLDERS = ("{%metas%}", "{%title%}", "{%favicon%}", "{%css%}",
                     "{%app_entry%}", "{%config%}", "{%scripts%}", "{%renderer%}")

ASSET = Path(__file__).resolve().parents[1] / "assets" / "startup_cover.js"


def _constant(name):
    """A timing constant from the module, so the contracts follow a retune."""
    return int(re.search(rf"var {name} = (\d+);", ASSET.read_text(encoding="utf-8")).group(1))


# --- The page template -------------------------------------------------------

def test_the_template_keeps_everything_dash_fills_in():
    page = build_index_string()

    for placeholder in DASH_PLACEHOLDERS:
        assert placeholder in page, placeholder


def test_the_cover_is_painted_before_the_app():
    """It comes ahead of the entry point, so it is on screen in the first
    paint rather than after Dash renders the layout, and React never owns it."""
    page = build_index_string()

    assert page.index('id="startup-cover"') < page.index("{%app_entry%}")


def test_the_cover_draws_its_spinner_like_every_other_cover():
    page = build_index_string()

    for prop, value in LOADING_SPINNER_STYLE.items():
        assert f"{prop}: {value}" in page


def test_the_canvas_bridge_reports_the_first_payload_to_the_cover():
    """The core engine's first response carries the canvas payload together
    with the editor's search options and every other dropdown it fills, and
    Dash applies them all at once. So the payload is the sign they're in."""
    from callbacks import register_callbacks

    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_callbacks(app)

    bridge = next(c for c in app._callback_list
                  if c["output"] == "canvas-payload-stamp.data")
    name = bridge["clientside_function"]["function_name"]
    source = next(s for s in app._inline_scripts if name in s)

    assert "notifyStartupPayload" in source


# --- The browser contract ----------------------------------------------------

def _run_contract(script, observers=True):
    """Run a browser contract for assets/startup_cover.js under Node.

    `setBusy` stands in for Dash adding or removing `._dash-loading-callback`,
    and delivers the observer callback the way the real MutationObserver
    would. Idle callbacks wait in a queue until `runIdle()`.
    """
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the startup-cover contract")

    harness = r'''
const assert = require('node:assert/strict');
const USE_OBSERVERS = __USE_OBSERVERS__;
const QUIET = __QUIET__;
const LIFT = __LIFT__;
const GIVE_UP = __GIVE_UP__;

const timers = [];
let clock = 0;
global.setTimeout = (fn, ms) => { timers.push({fn, at: clock + (ms || 0)}); return timers.length; };
global.clearTimeout = handle => { if (timers[handle - 1]) timers[handle - 1].cancelled = true; };
global.advance = ms => {
    const upTo = clock + ms;
    let next;
    while ((next = timers
        .filter(t => !t.cancelled && !t.done && t.at <= upTo)
        .sort((a, b) => a.at - b.at)[0])) {
        next.done = true;
        clock = next.at;
        next.fn();
    }
    clock = upTo;
};

const idleQueue = [];
global.runIdle = () => idleQueue.splice(0).forEach(fn => fn({didTimeout: false}));
global.idlePending = () => idleQueue.length;

const marks = [];
global.window = {
    requestIdleCallback: fn => { idleQueue.push(fn); return idleQueue.length; },
    performance: {mark: name => marks.push(name)},
};
global.marks = marks;

const observers = [];
global.MutationObserver = USE_OBSERVERS ? class {
    constructor(fn) { this.fn = fn; this.target = null; observers.push(this); }
    observe(target) { this.target = target; }
    disconnect() { this.target = null; }
} : undefined;

function makeElement(id) {
    return {
        id,
        attrs: {},
        setAttribute(name, value) { this.attrs[name] = value; },
        removeAttribute(name) { delete this.attrs[name]; },
        hasAttribute(name) { return name in this.attrs; },
        classList: {
            set: new Set(),
            add(c) { this.set.add(c); },
            contains(c) { return this.set.has(c); },
        },
        classes() { return [...this.classList.set]; },
    };
}

const cover = makeElement('startup-cover');
const app = makeElement('react-entry-point');
let busy = false;

global.document = {
    readyState: 'complete',
    visibilityState: 'visible',
    getElementById: id => ({'startup-cover': cover, 'react-entry-point': app})[id] || null,
    querySelector: selector => (selector === '._dash-loading-callback' && busy ? {} : null),
    addEventListener: () => {},
};

// Dash adding or removing its loading marker, seen by the module's observer.
global.setBusy = value => {
    busy = value;
    observers.forEach(o => { if (o.target === app) o.fn([]); });
};
global.cover = cover;
global.app = app;
global.lifted = () => cover.classList.contains('is-lifting') || cover.classList.contains('is-lifted');
global.payload = [{data: {id: 'A'}}, {data: {id: 'B'}}, {data: {source: 'A', target: 'B'}}];

require(process.argv[1]);
const notify = elements => window.SkillTree.notifyStartupPayload(elements);
global.notify = notify;
'''
    harness = (harness
               .replace("__USE_OBSERVERS__", "true" if observers else "false")
               .replace("__QUIET__", str(_constant("QUIET_MS")))
               .replace("__LIFT__", str(_constant("LIFT_MS")))
               .replace("__GIVE_UP__", str(_constant("GIVE_UP_MS"))))
    result = subprocess.run(
        [node_binary, "-e", harness + script, str(ASSET)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_the_app_underneath_is_inert_from_the_start():
    """The cover stops the pointer. Inert stops the keyboard from tabbing into
    the toolbar behind it."""
    _run_contract(r'''
assert.equal(app.hasAttribute('inert'), true);
assert.deepEqual(cover.classes(), []);
''')


def test_an_idle_dash_before_the_payload_is_not_ready():
    """Dash shows no loading marker before its layout has even loaded, so
    quiet alone means nothing until the core engine's payload is in."""
    _run_contract(r'''
advance(5000);
runIdle();
assert.equal(lifted(), false);
assert.equal(idlePending(), 0, 'no quiet window starts without the payload');
''')


def test_a_store_mounting_is_not_the_payload():
    """A dcc.Store whose data starts as None reports itself changed when it
    mounts, so the bridge runs once with no payload at all."""
    _run_contract(r'''
notify(undefined);
notify(null);
advance(5000);
runIdle();
assert.equal(lifted(), false);
''')


def test_it_lifts_once_dash_has_been_quiet_after_the_payload():
    _run_contract(r'''
setBusy(true);
notify(payload);
advance(5000);
runIdle();
assert.equal(lifted(), false, 'startup callbacks are still pending');

setBusy(false);
advance(QUIET - 1);
assert.equal(idlePending(), 0, 'still inside the quiet window');
advance(1);
assert.equal(lifted(), false, 'waits for the browser to go idle as well');

runIdle();
assert.equal(cover.classList.contains('is-lifting'), true, 'the cover fades out');
assert.equal(app.hasAttribute('inert'), false, 'the app responds from the first frame of the fade');
assert.deepEqual(marks, ['skill-tree-ready']);

advance(LIFT);
assert.equal(cover.classList.contains('is-lifted'), true, 'and is gone once the fade ends');
''')


def test_an_empty_graph_still_counts_as_a_payload():
    """A new user's graph has no nodes, and their core engine payload is an
    empty list. The cover must not wait on nodes that will never come."""
    _run_contract(r'''
notify([]);
advance(QUIET);
runIdle();
assert.equal(lifted(), true);
''')


def test_a_callback_inside_the_quiet_window_restarts_it():
    """dash-cytoscape echoes its elements about 100 ms after ingesting them,
    and that echo can start more callbacks. A window that has seen a callback
    must not lift the cover when it runs out."""
    _run_contract(r'''
notify(payload);
advance(QUIET - 50);
setBusy(true);
setBusy(false);
advance(100);
assert.equal(idlePending(), 0, 'the interrupted window does not count');
assert.equal(lifted(), false);

advance(QUIET - 100);
runIdle();
assert.equal(lifted(), true, 'a full window after the last callback');
''')


def test_work_that_starts_before_the_idle_callback_holds_the_cover():
    _run_contract(r'''
notify(payload);
advance(QUIET);
assert.equal(idlePending(), 1);

setBusy(true);
runIdle();
assert.equal(lifted(), false, 'Dash is busy again by the time the browser is idle');

setBusy(false);
advance(QUIET);
runIdle();
assert.equal(lifted(), true);
''')


def test_the_backstop_lifts_a_startup_that_never_settles():
    """A failed startup should still end with the UI on screen."""
    _run_contract(r'''
setBusy(true);
advance(GIVE_UP - 1);
assert.equal(lifted(), false);
advance(1);
assert.equal(cover.classList.contains('is-lifting'), true);
assert.equal(app.hasAttribute('inert'), false);
''')


def test_a_page_loaded_in_the_background_cuts_straight_to_the_app():
    """Nobody watched the cover, so there is nothing to fade."""
    _run_contract(r'''
document.visibilityState = 'hidden';
notify(payload);
advance(QUIET);
runIdle();
assert.equal(cover.classList.contains('is-lifted'), true);
assert.equal(cover.classList.contains('is-lifting'), false);
''')


def test_without_a_mutation_observer_it_looks_again():
    _run_contract(r'''
setBusy(true);
notify(payload);
advance(1000);
assert.equal(lifted(), false);
setBusy(false);
// One poll to notice, then a full quiet window.
advance(2 * QUIET);
runIdle();
assert.equal(lifted(), true);
''', observers=False)
