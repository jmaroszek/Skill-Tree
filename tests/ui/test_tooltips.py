"""Every tooltip is a hidden source that assets/components/hover_tips.js shows.

``dbc.Tooltip`` decided for itself when to open and close. It missed a pointer
that left before React had re-rendered it open, so the tooltip stayed up
wherever the pointer went, and it opened on keyboard focus, which a closing
modal hands back to the button that opened it. ``ui_kit.Tooltip`` now renders
only the content, and one script decides for every tooltip (test_hover_tips.py).
"""

import re

from skilltree.app import AppSettings, create_app
from skilltree.features.editor.layout import build_node_editor_content
from skilltree.features.events.layout import build_dormant_nodes_table
from skilltree.domain.models import Node
from skilltree.shell import build_app_layout
from skilltree.store.graph.manager import GraphManager
from skilltree.ui.kit import Tooltip, add_button, dom_id, edit_button, info_button
from support.paths import ROOT


def _walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    if component is None or isinstance(component, (str, int, float)):
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _sources(component):
    """Every tooltip source in a component tree."""
    return [c for c in _walk(component)
            if "tooltip-source" in (getattr(c, "className", None) or "").split()]


def _target(source):
    return getattr(source, "data-tooltip-for")


def test_a_tooltip_is_hidden_content_that_names_its_target():
    tip = Tooltip("Hello", target="some-button", placement="left")

    assert tip.children == "Hello"
    assert tip.hidden is True
    assert tip.className == "tooltip-source"
    assert _target(tip) == "some-button"
    assert getattr(tip, "data-placement") == "left"


def test_a_tooltip_sits_on_top_unless_told_otherwise():
    tip = Tooltip("Hello", target="x", id="x-tooltip", className="wide-tooltip")

    assert getattr(tip, "data-placement") == "top"
    assert tip.id == "x-tooltip"
    assert getattr(tip, "data-tooltip-class") == "wide-tooltip"


def test_a_pattern_matching_target_is_named_by_the_id_dash_renders():
    # Dash renders a dict id as JSON with sorted keys and no spaces, the way
    # JavaScript's JSON.stringify writes each part.
    target = {"type": "hub-history-sort-column", "index": "estimated"}

    assert _target(Tooltip("Sort", target=target)) == \
        '{"index":"estimated","type":"hub-history-sort-column"}'
    assert dom_id({"type": "row", "index": 3}) == '{"index":3,"type":"row"}'
    assert dom_id({"index": "Café \"Noir\""}) == '{"index":"Café \\"Noir\\""}'
    assert dom_id("plain-id") == "plain-id"


def test_ui_kit_buttons_carry_a_tooltip_on_their_button():
    for button_id, button in [("a", add_button("a", "Add")), ("b", edit_button("b")),
                              ("c", info_button("c", "Info"))]:
        (tip,) = _sources(button)
        assert _target(tip) == button_id


def test_dormant_node_row_actions_each_have_a_tooltip():
    node = Node(name="Audio Engineering", type="Learn", description="", value=5,
                time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
                status="Open", dormant=1)
    table = build_dormant_nodes_table(
        [{"node": node, "delay_days": 0, "activated": False}])

    assert len(_sources(table)) == 3


def test_every_tooltip_in_the_layout_targets_an_element_in_it():
    """A tooltip whose target id is gone, or misspelled, never shows."""
    layout = build_app_layout(GraphManager(), env="sandbox")
    ids = {dom_id(c.id) for c in _walk(layout) if getattr(c, "id", None) is not None}
    sources = _sources(layout)

    assert len(sources) > 30
    assert [_target(s) for s in sources if _target(s) not in ids] == []


def test_callbacks_only_rewrite_a_tooltips_content():
    """A source is a Div: dbc.Tooltip's ``is_open`` would set nothing."""
    tips = {s.id for s in _sources(build_node_editor_content()) if getattr(s, "id", None)}
    assert {"editor-revert-tooltip", "editor-save-tooltip"} <= tips

    app = create_app(AppSettings(environment="sandbox", configure_logging=False))
    layout = build_app_layout(GraphManager(), env="sandbox")
    tip_ids = {s.id for s in _sources(layout) if getattr(s, "id", None)}
    outputs = []
    for callback in app._callback_list:
        # "..a.children...b.style.." for several outputs; "@<hash>" marks a
        # duplicate output, and a callback with none has only a hash.
        spec = callback["output"]
        parts = spec.strip(".").split("...") if spec.startswith("..") else [spec]
        outputs += [part.split("@")[0].rsplit(".", 1) for part in parts if "." in part]
    written = {prop for component, prop in outputs if component in tip_ids}

    assert "editor-save-tooltip" in {component for component, _ in outputs}
    assert written == {"children"}


def test_no_module_builds_a_raw_dbc_tooltip():
    """A raw ``dbc.Tooltip(`` opens and closes by its own rules."""
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in sorted((ROOT / "skilltree").rglob("*.py"))
        if "dbc.Tooltip(" in path.read_text(encoding="utf8")
    ]

    assert offenders == [], f"use ui_kit.Tooltip instead of dbc.Tooltip in {offenders}"


def test_no_component_carries_a_native_title_tooltip():
    """A ``title`` tooltip keeps Chromium's own delay and look and shows again
    after a click. Use ``ui_kit.hint`` or the ``overflow-hint`` class instead.
    Plotly axis titles are not tooltips."""
    pattern = re.compile(r"(?<![_\w])title=")
    offenders = [
        f"{path.relative_to(ROOT).as_posix()}:{number}"
        for path in sorted((ROOT / "skilltree").rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf8").splitlines(), 1)
        if pattern.search(line) and "dict(" not in line
    ]
    assert offenders == []


def test_no_script_sets_a_native_title_tooltip():
    from support.paths import app_asset_files
    offenders = [path.name for path in app_asset_files(".js")
                 if ".title =" in path.read_text(encoding="utf8")
                 or "'title'" in path.read_text(encoding="utf8")]
    assert offenders == []
