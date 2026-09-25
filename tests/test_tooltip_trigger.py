"""Tooltips open on hover only, never on focus.

``dbc.Tooltip`` defaults to ``trigger="hover focus"``. A modal returns focus to
the button that opened it when it closes, so the default made that button's
tooltip pop open with the cursor elsewhere and stay until the next click.
Everything goes through ``ui_kit.Tooltip``, which fixes the trigger in one place.
"""

import dash_bootstrap_components as dbc
from pathlib import Path
import shutil
import subprocess

import dash
import pytest

from events_layout import build_dormant_nodes_table
from models import Node
from sidebars_callbacks import register_sidebars_callbacks
from sidebars_layout import build_node_editor_content
from ui_kit import Tooltip, add_button, edit_button, info_button

ROOT = Path(__file__).resolve().parents[1]


def _tooltips(component):
    """Every dbc.Tooltip in a component tree."""
    found = []
    if isinstance(component, dbc.Tooltip):
        found.append(component)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            found.extend(_tooltips(child))
    elif children is not None and not isinstance(children, str):
        found.extend(_tooltips(children))
    return found


def test_the_factory_is_hover_only_by_default():
    tip = Tooltip("Hello", target="some-button", placement="left")

    assert tip.trigger == "hover"
    assert tip.target == "some-button"
    assert tip.placement == "left"
    assert set(tip.delay) == {"show", "hide"}


def test_the_trigger_can_still_be_overridden_per_call():
    assert Tooltip("Hello", target="x", trigger="click").trigger == "click"


def test_ui_kit_buttons_build_hover_only_tooltips():
    for button in (add_button("a", "Add"), edit_button("b"), info_button("c", "Info")):
        (tip,) = _tooltips(button)
        assert tip.trigger == "hover"


def test_dormant_node_row_actions_are_hover_only():
    node = Node(name="Audio Engineering", type="Learn", description="", value=5,
                time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                status="Open", dormant=1)
    table = build_dormant_nodes_table(
        [{"node": node, "delay_days": 0, "activated": False}])

    tips = _tooltips(table)

    assert len(tips) == 3
    assert all(tip.trigger == "hover" for tip in tips)


def test_no_module_builds_a_raw_dbc_tooltip():
    """A raw ``dbc.Tooltip(`` silently brings the focus trigger back."""
    offenders = [
        path.name for path in sorted(ROOT.glob("*.py"))
        if path.name != "ui_kit.py"
        and "dbc.Tooltip(" in path.read_text(encoding="utf8")
    ]

    assert offenders == [], f"use ui_kit.Tooltip instead of dbc.Tooltip in {offenders}"


def test_editor_action_tooltips_dismiss_when_sidebar_closes():
    tips = {tip.id: tip for tip in _tooltips(build_node_editor_content())
            if getattr(tip, 'id', None) and tip.id.startswith('editor-')}
    expected = {
        'editor-revert-tooltip', 'editor-save-tooltip',
        'editor-save-close-tooltip', 'editor-delete-tooltip',
        'editor-new-node-tooltip',
    }
    assert set(tips) == expected
    assert all(tip.trigger == 'hover' for tip in tips.values())

    app = dash.Dash(__name__)
    register_sidebars_callbacks(app)
    callback = next(c for c in app._callback_list
                    if all(f'{tip}.is_open' in c['output'] for tip in expected))
    assert callback['inputs'] == [{'id': 'sidebar-editor-container', 'property': 'style'}]

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required for the editor tooltip browser contract')
    asset = ROOT / 'assets' / 'editor_sidebar.js'
    script = r'''
const assert = require('node:assert/strict');
global.window = {dash_clientside: {no_update: 'NO'}};
const events = [];
global.MouseEvent = class { constructor(type) { this.type = type; } };
global.document = {getElementById: id => ({
    dispatchEvent: event => events.push([id, event.type]),
})};
require(process.argv[1]);
const dismiss = window.dash_clientside.editor.dismiss_tooltips;
assert.deepEqual(dismiss({transform: 'translateX(0px)'}), Array(5).fill('NO'));
assert.deepEqual(events, []);
assert.deepEqual(dismiss({transform: 'translateX(-350px)'}), Array(5).fill(false));
assert.deepEqual(events, ['btn-revert', 'btn-save', 'btn-save-close',
    'btn-delete', 'btn-new-node'].map(id => [id, 'mouseout']));
'''
    result = subprocess.run([node, '-e', script, str(asset)], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stderr
