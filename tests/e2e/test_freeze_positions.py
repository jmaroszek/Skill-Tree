"""Freeze preserves the live graph through edits and Cytoscape's auto-refresh."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_keyboard import _seed  # noqa: E402
from test_journeys import (  # noqa: E402
    _idle, _open_in_editor, _new_node, _close_editor, _dropdown_pick, _welcome
)
from canvases import CANVASES  # noqa: E402


def _watch_frozen_positions(page):
    page.evaluate("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        const probe = window.freezeProbe = {
            positions: Object.fromEntries(cy.nodes().map(n => [n.id(), {...n.position()}])),
            zoom: cy.zoom(), pan: {...cy.pan()}, moved: 0
        };
        cy.on('position', 'node', event => {
            const before = probe.positions[event.target.id()];
            if (!before) return;
            const after = event.target.position();
            probe.moved = Math.max(probe.moved,
                Math.hypot(after.x - before.x, after.y - before.y));
        });
    }""")


def _assert_frozen(page):
    # Include the component's debounced auto-refresh and element echo.
    _idle(page)
    page.wait_for_timeout(1400)
    result = page.evaluate("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        return {moved: freezeProbe.moved, zoom: cy.zoom() - freezeProbe.zoom,
                pan: Math.hypot(cy.pan().x - freezeProbe.pan.x,
                               cy.pan().y - freezeProbe.pan.y)};
    }""")
    assert result == {"moved": 0, "zoom": 0, "pan": 0}, result


def test_freeze_preserves_positions_while_editing_nodes_and_edges(page, server):
    _seed(page)
    page.click("a.nav-link:has-text('Nodes')")
    page.wait_for_function("SkillTree.canvasFirstPaintDone()")
    _idle(page)
    page.wait_for_timeout(1200)
    page.click("#btn-graph-settings")
    # A Settle before Freeze must not grant a future edit permission to move.
    page.click("#graph-settings-relayout")
    _idle(page)
    page.wait_for_timeout(1400)
    page.click("#graph-settings-freeze-rerender")
    page.wait_for_function("SkillTree.isFrozen('main')")
    page.click("#btn-close-graph-settings")
    _watch_frozen_positions(page)

    _open_in_editor(page, "Beta")
    page.click("#btn-delete")
    page.click("#btn-node-delete-confirm")
    page.wait_for_function("document.querySelector('#save-output').innerText.includes('Deleted')")
    assert server.query("SELECT name FROM Nodes ORDER BY name") == [("Alpha",), ("Goal",)]
    _assert_frozen(page)

    _new_node(page, "Gamma", "Learn", needs_hard=["Alpha"])
    _close_editor(page)
    page.wait_for_function("SkillTree.getCy(document.getElementById('cytoscape-graph')).getElementById('Gamma').length === 1")
    # Once the new node appears, it must also stay put through later edits.
    page.evaluate("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        freezeProbe.positions.Gamma = {...cy.getElementById('Gamma').position()};
    }""")
    _assert_frozen(page)

    _open_in_editor(page, "Goal")
    for expected_edges in (1, 0):
        # Choosing the multi-select option again removes that prerequisite.
        _dropdown_pick(page, "#edge-needs-soft", "Gamma")
        page.click("#btn-save")
        page.wait_for_function("document.querySelector('#save-output').innerText.includes('Updated node')")
        _assert_frozen(page)
        assert server.query("SELECT COUNT(*) FROM Edges WHERE source='Gamma' AND target='Goal' AND type='Needs_Soft'") == [(expected_edges,)]
    assert page.console_errors == []


@pytest.mark.parametrize("canvas", CANVASES, ids=lambda canvas: canvas.key)
def test_settle_permission_is_scoped_to_one_frozen_interval(page, canvas):
    _welcome(page)
    _idle(page)
    result = page.evaluate("""({key, cyId}) => {
        const cy = SkillTree.getCy(document.getElementById(cyId));
        cy.add(['a', 'b', 'c'].map((id, i) => ({
            data: {id}, position: {x: i * 100 + 50, y: i * 50 + 50}
        })));
        const positions = () => cy.nodes().map(n => ({...n.position()}));
        const layout = name => cy.layout({name, fit: false, animate: false}).run();
        // Settle while unfrozen cannot authorize a layout after Freeze.
        SkillTree.allowOneLayout(key);
        layout('grid');
        SkillTree.setFreezeActive(key, true);
        const before = positions();
        layout('circle');
        const afterAutomatic = positions();
        // A pending Settle also expires when Freeze is toggled off and on.
        SkillTree.allowOneLayout(key);
        SkillTree.setFreezeActive(key, false);
        SkillTree.setFreezeActive(key, true);
        layout('circle');
        const afterToggle = positions();
        // Explicit Settle still works while frozen and establishes new locks.
        SkillTree.allowOneLayout(key);
        layout('circle');
        const afterSettle = positions();
        layout('grid');
        const afterNext = positions();
        SkillTree.setFreezeActive(key, false);
        return {before, afterAutomatic, afterToggle, afterSettle, afterNext};
    }""", {"key": canvas.key, "cyId": canvas.cytoscape_id})
    assert result["afterAutomatic"] == result["before"], result
    assert result["afterToggle"] == result["before"], result
    assert result["afterSettle"] != result["before"], result
    assert result["afterNext"] == result["afterSettle"], result
    assert page.console_errors == []
