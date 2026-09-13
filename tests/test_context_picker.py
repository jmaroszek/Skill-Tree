"""Contracts for the shared Context / Subcontext picker layer."""

from pathlib import Path
import json
import shutil
import subprocess

import pytest

from context_picker import (
    build_context_taxonomy,
    build_multi_context_picker,
    build_single_context_picker,
)
from layout import build_app_layout


def _walk(component):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    yield component
    children = getattr(component, "children", None)
    if children is not None:
        yield from _walk(children)


def _by_id(component, component_id):
    return next(item for item in _walk(component)
                if getattr(item, "id", None) == component_id)


def test_single_picker_keeps_legacy_value_components():
    picker = build_single_context_picker(
        "test-context-picker",
        "test-context",
        "test-subcontext",
        context_options=[{"label": "STEM", "value": "STEM"}],
        context_value="STEM",
        subcontext_value="Computers",
    )

    assert _by_id(picker, "test-context").value == "STEM"
    assert _by_id(picker, "test-subcontext").value == "Computers"
    assert "context-picker-bridge" in _by_id(picker, "test-context").className
    assert _by_id(picker, "test-context-picker-trigger").children.children == "STEM › Computers"


def test_multi_picker_keeps_encoded_filter_values():
    encoded = "STEM\x1fComputers"
    picker = build_multi_context_picker(
        "test-filter-picker",
        "test-filter-context",
        "test-filter-subcontext",
        context_value=["STEM"],
        subcontext_value=[encoded],
    )

    assert _by_id(picker, "test-filter-context").value == ["STEM"]
    assert _by_id(picker, "test-filter-subcontext").value == [encoded]
    state = json.loads(_by_id(picker, "test-filter-picker-state").children)
    assert state["context"] == ["STEM"]
    assert state["subcontext"] == [encoded]


def test_every_ordinary_context_selection_surface_uses_the_shared_picker():
    layout = build_app_layout([], env="sandbox")
    picker_ids = {
        "node-context-picker",
        "filter-context-picker",
        "details-add-context-picker",
        "dormant-node-context-picker",
        "hub-history-context-picker",
    }
    found = {getattr(item, "id", None) for item in _walk(layout)}

    assert picker_ids <= found
    assert "context-taxonomy-store" in found
    assert "context-picker-portal" in found


def test_taxonomy_keeps_no_subcontext_out_of_user_defined_options(monkeypatch):
    monkeypatch.setattr(
        "context_picker.ConfigManager.get_contexts",
        lambda: ["STEM"],
    )
    monkeypatch.setattr(
        "context_picker.ConfigManager.get_subcontexts",
        lambda: {"STEM": ["Math", "Computers"]},
    )
    monkeypatch.setattr(
        "context_picker.ConfigManager.get_context_sort_mode",
        lambda: "definition",
    )
    monkeypatch.setattr(
        "context_picker.ConfigManager.get_subcontext_sort_mode",
        lambda: "definition",
    )

    assert build_context_taxonomy() == [{
        "context": "STEM",
        "subcontexts": ["Math", "Computers"],
    }]


def test_browser_state_contract_preserves_order_and_summary_format():
    node_binary = shutil.which("node")
    if node_binary is None:
        pytest.skip("Node.js is required for the picker state contract")

    asset = Path(__file__).resolve().parents[1] / "assets" / "context_picker.js"
    script = r'''
const assert = require('node:assert/strict');
global.window = {};
require(process.argv[1]);
const picker = window.SkillTreeContextPicker;
const taxonomy = [
    {context: 'Wisdom', subcontexts: ['Stoicism']},
    {context: 'STEM', subcontexts: ['Math', 'Computers']},
    {context: 'Self', subcontexts: ['Identity']},
];

assert.deepEqual(
    picker.decodeSubcontextValue(picker.encodeSubcontextValue('STEM', 'Computers')),
    {context: 'STEM', subcontext: 'Computers'}
);
assert.deepEqual(
    picker.decodeSubcontextValue(picker.encodeSubcontextValue('Self', picker.NO_SUBCONTEXT)),
    {context: 'Self', subcontext: picker.NO_SUBCONTEXT}
);

const state = {
    context: ['Self', 'STEM', 'Wisdom'],
    subcontext: ['STEM\u001fComputers', 'Self\u001fIdentity'],
};
assert.equal(
    picker.multiSummary(state, taxonomy, 'All contexts').label,
    'Wisdom · STEM (1) +1'
);

const selected = new Set(['Self', 'STEM']);
const partial = new Map([
    ['STEM', new Set(['Computers'])],
    ['Self', new Set([picker.NO_SUBCONTEXT])],
]);
assert.deepEqual(
    picker.canonicalMultiState(taxonomy, selected, partial),
    {
        context: ['STEM', 'Self'],
        subcontext: ['STEM\u001fComputers', 'Self\u001f'],
    }
);
'''
    result = subprocess.run(
        [node_binary, "-e", script, str(asset)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_multi_picker_bridges_do_not_prune_values_against_options():
    # A dcc.Dropdown drops values missing from its current options, which
    # erased a subcontext picked in a context that was not selected yet.
    picker = build_multi_context_picker(
        "test-filter-picker", "test-filter-context", "test-filter-subcontext",
    )

    assert type(_by_id(picker, "test-filter-context")).__name__ == "Checklist"
    assert type(_by_id(picker, "test-filter-subcontext")).__name__ == "Checklist"


def test_empty_single_picker_trigger_is_a_placeholder():
    picker = build_single_context_picker("p", "c", "s")
    label = _by_id(picker, "p-trigger").children

    assert label.children == "Select context..."
    assert "is-placeholder" in label.className


def test_history_filter_keeps_whole_contexts_beside_partial_ones():
    from types import SimpleNamespace
    from review_hub_callbacks import _filter_history_nodes

    nodes = [
        SimpleNamespace(name="a", context="Health", subcontext="Sleep"),
        SimpleNamespace(name="b", context="STEM", subcontext="Math"),
        SimpleNamespace(name="c", context="STEM", subcontext="Computers"),
        SimpleNamespace(name="d", context="STEM", subcontext=None),
        SimpleNamespace(name="e", context="Self", subcontext=None),
    ]
    kept = _filter_history_nodes(
        nodes, "", ["Health", "STEM"], ["STEM\x1fMath", "STEM\x1f"],
    )

    assert [n.name for n in kept] == ["a", "b", "d"]
