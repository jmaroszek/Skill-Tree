"""When the tab content makes room for a sidebar, and what it must not do."""
import json
import shutil
import subprocess

import pytest

from support.paths import ROOT, asset_file

ASSET = asset_file("content_room.js")
EDITOR = "sidebar-editor-container"
EVENTS = "events-sidebar-container"


def _room(left, right_open, width):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the content room rule")
    script = (
        "global.window = {};"
        "require(process.argv[1]);"
        "const args = JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(window.SkillTree.contentRoom.roomFor(...args)));"
    )
    result = subprocess.run(
        [node, "-e", script, str(ASSET), json.dumps([left, right_open, width])],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("left, right_open, width, expected", [
    (None, False, 2194, {"left": "", "right": False}),
    (EDITOR, False, 1250, {"left": "all", "right": False}),
    (None, True, 1250, {"left": "", "right": True}),
    (EDITOR, True, 1600, {"left": "all", "right": True}),
    # Too narrow for both: the left panel keeps its room and Filters covers.
    (EDITOR, True, 1599, {"left": "all", "right": False}),
    # Too narrow for one: everything covers, except the Events list.
    (EDITOR, False, 1249, {"left": "", "right": False}),
    (None, True, 1249, {"left": "", "right": False}),
    (EVENTS, False, 1249, {"left": "events", "right": False}),
])
def test_the_room_each_window_width_gives(left, right_open, width, expected):
    assert _room(left, right_open, width) == expected


def test_no_transform_rests_on_the_content():
    """A resting transform misplaces every position: fixed dropdown inside it."""
    css = (ROOT / "assets" / "css" / "theme.css").read_text(encoding="utf-8")
    rules = css[css.index(".stage-pane {"):css.index(".events-tab-inner {")]
    assert "transform" not in rules
    assert "fill: 'both'" in ASSET.read_text(encoding="utf-8")
    assert "animation.cancel()" in ASSET.read_text(encoding="utf-8")


def test_a_chart_redraws_with_the_box_rather_than_after_it():
    """Plots.resize waits 100 ms, which shows as a second jump."""
    source = ASSET.read_text(encoding="utf-8")
    assert "Plotly.relayout" in source
    assert "Plots.resize" not in source.replace("Plots.resize waits", "")


def test_the_canvases_are_not_named_by_hand():
    source = ASSET.read_text(encoding="utf-8")
    assert "window.SkillTree.canvases" in source
    assert "cytoscape-graph" not in source
