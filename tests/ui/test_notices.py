"""A notice says what kind of thing happened, so nothing reads its words."""
import shutil
import subprocess

import pytest

from skilltree.ui.notices import error, info
from support.paths import ROOT


def test_an_error_reads_the_way_it_always_has():
    assert error("Node name is required.")["text"] == "Error: Node name is required."
    assert error("Node name is required.")["kind"] == "error"
    assert info("Changes reverted.")["text"] == "Changes reverted."
    assert info("Changes reverted.")["kind"] == "info"


NODE_TEST = """
const assert = require('assert');
const NO = {};
global.window = {dash_clientside: {no_update: NO, callback_context: {triggered: []}}};
require(process.argv[1]);
const show = window.dash_clientside.notices.show;
const fired = (id) => {
    window.dash_clientside.callback_context.triggered = [{prop_id: id}];
};
const error = {kind: 'error', text: 'Error: no', ts: 1};
const info = {kind: 'info', text: 'Saved', ts: 2};

fired('notice-store.data');
assert.deepStrictEqual(show(error, 0), ['Error: no', true, 'Error: no']);
assert.deepStrictEqual(show(info, 0), ['Saved', NO, NO]);
// No notice blanks the line, and leaves a dialog the user hasn't closed.
assert.deepStrictEqual(show(null, 0), ['', NO, NO]);
fired('btn-close-error.n_clicks');
assert.deepStrictEqual(show(error, 1), [NO, false, NO]);
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node")
def test_only_an_error_opens_the_dialog():
    script = ROOT / "assets" / "components" / "notices.js"
    result = subprocess.run(["node", "-e", NODE_TEST, str(script)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
