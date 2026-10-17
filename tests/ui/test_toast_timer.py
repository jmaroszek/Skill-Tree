"""Contract for assets/components/toast_timer.js: a message stays its full time.

A dcc.Interval cleared the editor's messages, and resetting its n_intervals
doesn't restart its clock, so a message that followed another was cleared at
the next tick of the old rhythm: a "Deleted node" message vanished 370 ms
after it appeared. The timer restarts on every message instead.
"""

import shutil
import subprocess

import pytest
from support.paths import asset_file


def _run_contract(script):
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the toast timer contract")

    harness = r'''
const assert = require('node:assert/strict');

// A clock the test moves by hand.
let now = 0;
let pending = [];
global.setTimeout = (fn, ms) => { const t = {fn, at: now + ms, live: true}; pending.push(t); return t; };
global.clearTimeout = t => { if (t) t.live = false; };
global.advance = ms => {
    const end = now + ms;
    for (;;) {
        const due = pending.filter(t => t.live && t.at <= end).sort((a, b) => a.at - b.at)[0];
        if (!due) break;
        due.live = false;
        now = due.at;
        due.fn();
    }
    now = end;
};

global.cleared = [];
global.window = {dash_clientside: {set_props: (id, props) => cleared.push([id, props])}};
require(process.argv[1]);
global.arm = (id, ms, text) => window.dash_clientside.toast_timer.arm(id, ms, text);

''' + script
    result = subprocess.run(
        [node_binary, "-e", harness, str(asset_file("toast_timer.js"))],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout


def test_a_message_clears_after_its_time():
    _run_contract(r'''
arm('m', 3000, 'Saved.');
advance(2999);
assert.equal(cleared.length, 0);
advance(1);
assert.deepEqual(cleared, [['m', {children: ''}]]);
''')


def test_a_second_message_gets_its_full_time():
    _run_contract(r'''
arm('m', 3000, 'Saved.');
advance(2630);
arm('m', 3000, "Deleted node 'X'");
advance(2999);
assert.equal(cleared.length, 0, 'the second message was cleared early');
advance(1);
assert.equal(cleared.length, 1);
''')


def test_the_same_text_again_restarts_the_timer():
    _run_contract(r'''
arm('m', 3000, 'Saved.');
advance(2000);
arm('m', 3000, 'Saved.');
advance(2000);
assert.equal(cleared.length, 0);
advance(1000);
assert.equal(cleared.length, 1);
''')


def test_an_emptied_message_cancels_the_timer_and_ids_are_independent():
    _run_contract(r'''
arm('a', 3000, 'one');
arm('b', 4000, 'two');
arm('a', 3000, '');
advance(5000);
assert.deepEqual(cleared, [['b', {children: ''}]]);
''')
