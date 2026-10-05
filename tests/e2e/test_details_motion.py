"""The Details graph stays where its opening layout puts it."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _idle  # noqa: E402
from test_keyboard import _seed  # noqa: E402


def test_nodes_stay_where_the_opening_layout_settles(page):
    _seed(page)
    page.click("a.nav-link:has-text('Details')")
    _idle(page)
    result = page.evaluate("""async () => {
        const cy = SkillTree.getCy(document.getElementById('details-mini-graph'));
        const positions = () => Object.fromEntries(
            cy.nodes().map(n => [n.id(), {...n.position()}]));
        let settled = null;
        const stopped = new Promise(resolve => cy.on('layoutstop', function onStop() {
            if (!cy.getElementById('Goal').length || cy.nodes().length < 3) return;
            settled = positions();
            cy.off('layoutstop', onStop);
            resolve();
        }));
        SkillTree.menus.send('details-navigate-trigger-input', 'Goal|' + Date.now());
        await stopped;
        // The canvas reports its elements back to Dash after the layout.
        // That report must not move anything.
        await new Promise(resolve => setTimeout(resolve, 1500));
        const later = positions();
        let moved = 0;
        for (const id in settled) {
            moved = Math.max(moved, Math.hypot(later[id].x - settled[id].x,
                                               later[id].y - settled[id].y));
        }
        const xs = Object.values(settled).map(p => p.x);
        return {nodes: Object.keys(settled).length, moved,
                spread: Math.max(...xs) - Math.min(...xs)};
    }""")
    assert result["nodes"] == 3
    assert result["spread"] > 50
    assert result["moved"] < 1, result
    assert page.console_errors == []
