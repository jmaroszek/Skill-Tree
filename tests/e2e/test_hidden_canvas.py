"""A hidden canvas lays out its newest graph when its tab opens."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _idle  # noqa: E402
from test_keyboard import _seed  # noqa: E402

_DETAILS_NODES = ("SkillTree.getCy(document.getElementById('details-mini-graph'))"
                  ".nodes().length")
_HELD_NODES = """(() => {
    const held = SkillTree.heldPayload('details-mini-graph');
    return held ? held.filter(e => e.data.source == null).length : null;
})()"""


def test_a_filter_change_waits_for_the_hidden_canvas_to_open(page):
    _seed(page)
    page.click("a.nav-link:has-text('Details')")
    _idle(page)
    page.evaluate("SkillTree.menus.send('details-navigate-trigger-input', 'Goal|' + Date.now())")
    page.wait_for_function(f"{_DETAILS_NODES} === 3")
    _idle(page)

    page.click("a.nav-link:has-text('Home')")
    _idle(page)
    page.evaluate("dash_clientside.set_props('filter-node-type', {value: ['Goal']})")
    _idle(page)
    # The filtered graph waits. Laying it out here would compete with
    # whatever the open tab is animating.
    assert page.evaluate(_DETAILS_NODES) == 3
    assert page.evaluate(_HELD_NODES) == 1
    assert page.evaluate("SkillTree.canvasHasNode('details-mini-graph', 'Alpha')") is False

    page.click("a.nav-link:has-text('Details')")
    page.wait_for_function(f"{_DETAILS_NODES} === 1")
    assert page.evaluate(_HELD_NODES) is None
    assert page.console_errors == []
