"""The Cytoscape facade preserves events and reports the settled viewport."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _welcome, _idle  # noqa: E402


def test_viewport_metadata_settles_without_delaying_node_events(page):
    _welcome(page)
    _idle(page)
    # Mount the same public component outside Dash with an observable setProps
    # consumer. Exercise real Cytoscape and React, without replacing handlers.
    page.evaluate("""() => {
        const host = document.createElement('div');
        document.body.appendChild(host);
        const probe = window.extentProbe = {changes: [], root: ReactDOM.createRoot(host)};
        probe.root.render(React.createElement(dash_cytoscape.Cytoscape, {
            id: 'extent-relay-probe', style: {width: '100px', height: '100px'},
            elements: [{data: {id: 'probe'}, position: {x: 0, y: 0}}],
            layout: {name: 'preset', fit: false}, autoRefreshLayout: false,
            setProps: changes => probe.changes.push(changes)
        }));
    }""")
    page.wait_for_function("SkillTree.getCy(document.getElementById('extent-relay-probe')) !== null")
    page.wait_for_timeout(400)
    result = page.evaluate("""async () => {
        const probe = extentProbe;
        const cy = SkillTree.getCy(document.getElementById('extent-relay-probe'));
        probe.changes = [];
        // Changes keep arriving faster than the quiet interval. None should
        // reach the consumer until movement stops.
        for (let i = 0; i < 10; i++) {
            cy.pan({x: i + 1, y: i + 2});
            await new Promise(resolve => setTimeout(resolve, 25));
        }
        const during = probe.changes.filter(x => 'extent' in x).length;
        cy.getElementById('probe').emit('tap');
        const immediateTap = probe.changes.some(x => x.tapNodeData && x.tapNodeData.id === 'probe');
        await new Promise(resolve => setTimeout(resolve, 250));
        const extents = probe.changes.filter(x => 'extent' in x);
        const settled = extents.length === 1 && JSON.stringify(extents[0].extent) === JSON.stringify(cy.extent());
        probe.changes = [];
        cy.pan({x: 50, y: 60});
        await new Promise(resolve => setTimeout(resolve, 20));
        probe.root.unmount();
        await new Promise(resolve => setTimeout(resolve, 250));
        return {during, immediateTap, settled, afterUnmount: probe.changes.length};
    }""")
    assert result == {"during": 0, "immediateTap": True, "settled": True, "afterUnmount": 0}
    assert page.console_errors == []
