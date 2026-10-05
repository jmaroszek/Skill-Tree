"""The browser drops only Dash's empty callback-bookkeeping dispatches."""
from pathlib import Path
import shutil
import subprocess

import pytest


ASSET = Path(__file__).resolve().parents[1] / 'assets' / '00_dash_noop_dispatch.js'


def test_only_all_null_aggregates_are_dropped_from_the_store_dash_assigns_later():
    node_binary = shutil.which('node')
    if node_binary is None:
        pytest.skip('Node.js is required for the dispatch filter contract')
    script = r'''
const assert = require('node:assert/strict');
global.window = {};
require(process.argv[1]);
// Dash creates its store after assets load.
const seen = [];
window.store = {dispatch(action) { seen.push(action); return 'dispatched'; }};
const store = window.store;

assert.equal(store.dispatch({type: 'Callbacks.Aggregate', payload: [null, null]}).type,
             'Callbacks.Aggregate');
assert.equal(seen.length, 0);

const real = [
    {type: 'Callbacks.Aggregate', payload: [null, {type: 'x'}]},
    {type: 'Callbacks.Aggregate', payload: 'not a list'},
    {type: 'ON_PROP_CHANGE', payload: [null]},
];
real.forEach(action => assert.equal(store.dispatch(action), 'dispatched'));
assert.deepEqual(seen, real);

// Reassigning the same store doesn't wrap it twice.
const wrapped = store.dispatch;
window.store = store;
assert.equal(window.store.dispatch, wrapped);
'''
    result = subprocess.run([node_binary, '-e', script, str(ASSET)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
