"""Browser contract for the Events sidebar's contextual default behavior."""

import shutil
import subprocess

import pytest

from support.paths import asset_file


ASSET = asset_file("events_sidebar.js")


def _run_browser_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Events sidebar contract")

    script = r'''
const assert = require('node:assert/strict');
const setProps = [];
global.window = {
    dash_clientside: {
        no_update: 'NO',
        callback_context: {triggered: []},
        set_props: (id, props) => setProps.push([id, props]),
    }
};
// Timers run only when the test says the slide has finished.
let timers = [];
global.setTimeout = fn => { timers.push(fn); return fn; };
global.clearTimeout = fn => { timers = timers.filter(t => t !== fn); };
const finishSlide = () => {
    const due = timers;
    timers = [];
    due.forEach(fn => fn());
};
require(process.argv[1]);
const follow = window.dash_clientside.events.follow_left_panel;

// The list refresh waits for the slide to finish.
follow('events');
assert.deepEqual(setProps, []);
finishSlide();
assert.deepEqual(setProps.map(call => call[0]), ['events-ui-refresh-trigger']);
setProps.length = 0;

// Nothing changed, nothing starts.
follow('events');
finishSlide();
assert.deepEqual(setProps, []);

// Closing before the slide finishes drops the pending refresh.
follow(null);
follow('events');
follow('goals');
finishSlide();
assert.deepEqual(setProps, []);
'''
    result = subprocess.run(
        [node, "-e", script, str(ASSET)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_events_list_follows_the_left_panel():
    _run_browser_contract()
