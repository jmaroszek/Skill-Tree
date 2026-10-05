"""Now's ambient border follows the graph without animating its renderer."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _idle, _node_menu  # noqa: E402
from test_keyboard import _seed  # noqa: E402


def test_now_pulse_tracks_shapes_viewport_selection_and_locate(page, server):
    _seed(page)
    _node_menu(page, "Alpha", "ctx-menu-toggle-now")
    path = page.locator('#cytoscape-graph .now-pulse-layer path[data-node-id="Alpha"]')
    path.wait_for(state="attached")
    page.wait_for_function("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        return !cy.elements().some(node => node.animated());
    }""")
    assert server.query("SELECT now FROM Nodes WHERE name='Alpha'")[0][0] > 0
    assert page.locator("#cytoscape-graph .now-pulse-layer").get_attribute("aria-hidden") == "true"
    assert path.evaluate("el => getComputedStyle(el).pointerEvents") == "none"

    # Every configurable shape fits the same node body, independently of the
    # pulse stroke. A pan/zoom must carry that outline with the canvas.
    previous = None
    for shape in ("ellipse", "triangle", "rectangle", "star", "pentagon", "hexagon",
                  "diamond", "octagon", "round-rectangle", "vee"):
        page.evaluate("""shape => {
            const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
            cy.getElementById('Alpha').style('shape', shape);
        }""", shape)
        page.wait_for_function("""previous => {
            const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
            const node = cy.getElementById('Alpha');
            const path = document.querySelector('#cytoscape-graph .now-pulse-layer path[data-node-id="Alpha"]');
            const box = path.getBBox();
            return (!previous || path.getAttribute('d') !== previous) &&
                Math.abs(box.width - node.width()) < 0.01 &&
                Math.abs(box.height - node.height()) < 0.01;
        }""", arg=previous)
        previous = path.get_attribute('d')
    page.evaluate("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        cy.zoom(1.5); cy.center(cy.getElementById('Alpha'));
    }""")
    page.wait_for_timeout(400)
    alignment = page.evaluate("""() => {
        const root = document.getElementById('cytoscape-graph'), cy = SkillTree.getCy(root);
        const node = cy.getElementById('Alpha');
        const path = root.querySelector('.now-pulse-layer path[data-node-id="Alpha"]');
        const point = new DOMPoint(0, 0).matrixTransform(path.getScreenCTM());
        const pos = node.renderedPosition(), box = root.getBoundingClientRect();
        return {dx: point.x - box.left - root.clientLeft - pos.x,
            dy: point.y - box.top - root.clientTop - pos.y};
    }""")
    assert abs(alignment['dx']) < 1 and abs(alignment['dy']) < 1, alignment
    page.evaluate("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        cy.nodes(':selected').unselect();
        cy.getElementById('Alpha').select();
    }""")
    page.wait_for_function("""() => {
        const root = document.getElementById('cytoscape-graph'), cy = SkillTree.getCy(root);
        return root.querySelector('.now-pulse-layer path[data-node-id="Alpha"]').getAttribute('stroke') ===
            cy.getElementById('Alpha').style('border-color');
    }""")

    # A real CSS animation changes the outline. It starts no Cytoscape node
    # animation, and the canvas remains cached while the ambient pulse runs.
    opacity = []
    group = page.locator('#cytoscape-graph .now-pulse-layer > g')
    for time in (0, 1000):
        opacity.append(group.evaluate("""(el, time) => {
            el.getAnimations().forEach(a => { a.pause(); a.currentTime = time; });
            return parseFloat(getComputedStyle(el).opacity);
        }""", time))
    assert opacity == [0, 1]
    group.evaluate("el => el.getAnimations().forEach(a => a.play())")
    _idle(page)
    redraws = page.evaluate("""async () => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        let count = 0;
        const render = () => count++;
        cy.on('render', render);
        await new Promise(resolve => setTimeout(resolve, 1100));
        cy.off('render', render);
        return count;
    }""")
    assert redraws == 0
    page.evaluate("locateNodeOnGraph('Alpha', 'cytoscape-graph')")
    path.wait_for(state="detached")
    path.wait_for(state="attached", timeout=10000)
    page.wait_for_function("""() => {
        const node = SkillTree.getCy(document.getElementById('cytoscape-graph')).getElementById('Alpha');
        return !node.hasClass('locate-pulse') && node.width() === 60 && !node.animated();
    }""")

    page.click("a.nav-link:has-text('Home')")
    page.wait_for_function("getComputedStyle(document.querySelector('#cytoscape-graph .now-pulse-layer')).display === 'none'")
    page.click("a.nav-link:has-text('Nodes')")
    page.wait_for_function("getComputedStyle(document.querySelector('#cytoscape-graph .now-pulse-layer')).display !== 'none'")
    page.emulate_media(reduced_motion="reduce")
    assert group.evaluate("el => getComputedStyle(el).animationName") == "none"
    _node_menu(page, "Alpha", "ctx-menu-toggle-now")
    path.wait_for(state="detached")
    assert server.query("SELECT now FROM Nodes WHERE name='Alpha'")[0][0] == 0
    assert page.console_errors == []
