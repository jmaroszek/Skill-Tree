"""The alias rows slide open and shut on the compositor (assets/editor/alias_fold.js)."""
import json
import shutil
import subprocess

import pytest

from support.layout import walk
from support.paths import asset_file

ASSET = asset_file("alias_fold.js")


def _plans(cases):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the alias slide rule")
    script = (
        "global.window = {};"
        "require(process.argv[1]);"
        "const cases = JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(cases.map(c => window.SkillTree.aliasFold.plan(...c))));"
    )
    result = subprocess.run([node, "-e", script, str(ASSET), json.dumps(cases)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_opening_reveals_the_rows_and_pushes_what_follows():
    assert _plans([[0, 158]]) == [{"follow": -158, "reveal": 158, "cover": 0}]


def test_closing_covers_a_copy_of_the_rows():
    # The form has already reset the rows, so only the copy shows what shuts.
    assert _plans([[158, 0]]) == [{"follow": 158, "reveal": 0, "cover": 158}]


def test_a_row_more_reveals_only_that_row():
    assert _plans([[74, 116]]) == [{"follow": -42, "reveal": 42, "cover": 0}]


def test_fewer_rows_still_open_only_close_the_gap():
    assert _plans([[158, 74]]) == [{"follow": 84, "reveal": 0, "cover": 0}]


def test_no_change_plays_nothing():
    assert _plans([[74, 74], [0, 0]]) == [None, None]


def test_the_copy_has_a_place_of_its_own_after_the_rows():
    from skilltree.features.editor.layout import build_node_editor_content
    parent = next(node for node in walk(build_node_editor_content())
                  if isinstance(getattr(node, "children", None), list)
                  and any(getattr(child, "id", None) == "collapse-aliases"
                          for child in node.children))
    ids = [getattr(child, "id", None) for child in parent.children]
    after = parent.children[ids.index("collapse-aliases") + 1]
    assert after.id == "aliases-fold-ghost"
    # The script owns what is inside it.
    assert after.children is None


def test_bootstrap_no_longer_tweens_the_height():
    css = asset_file("theme.css").read_text(encoding="utf-8")
    assert "#collapse-aliases.collapsing { transition: none; }" in css
