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


def test_element_echo_waits_for_the_running_layout(page):
    _welcome(page)
    _idle(page)
    page.evaluate("""() => {
        const host = document.createElement('div');
        document.body.appendChild(host);
        const probe = window.echoProbe = {changes: [], root: ReactDOM.createRoot(host)};
        probe.root.render(React.createElement(dash_cytoscape.Cytoscape, {
            id: 'echo-hold-probe', style: {width: '200px', height: '200px'},
            elements: [{data: {id: 'a'}, position: {x: 0, y: 0}}],
            layout: {name: 'preset', fit: false}, autoRefreshLayout: false,
            setProps: changes => probe.changes.push(changes)
        }));
    }""")
    page.wait_for_function("SkillTree.getCy(document.getElementById('echo-hold-probe')) !== null")
    page.wait_for_timeout(400)
    result = page.evaluate("""async () => {
        const probe = echoProbe;
        const cy = SkillTree.getCy(document.getElementById('echo-hold-probe'));
        const echoes = () => probe.changes.filter(x => 'elements' in x);
        const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
        probe.changes = [];
        // Adding nodes starts a layout; the component echoes its elements
        // 100 ms later, while the layout is still moving them.
        cy.add([{data: {id: 'b'}}, {data: {id: 'c'}}]);
        const stopped = new Promise(resolve => cy.one('layoutstop', resolve));
        cy.layout({name: 'grid', animate: true, animationDuration: 700}).run();
        await wait(400);
        const during = echoes().length;
        const tap = (cy.getElementById('a').emit('tap'),
                     probe.changes.some(x => x.tapNodeData && x.tapNodeData.id === 'a'));
        await stopped;
        await wait(50);
        const after = echoes();
        const ids = after.length ? after[after.length - 1].elements.map(e => e.data.id).sort() : [];
        // With no layout running the echo goes straight through.
        probe.changes = [];
        cy.remove('#c');
        await wait(250);
        const idle = echoes().length;
        probe.root.unmount();
        return {during, tap, after: after.length, ids, idle};
    }""")
    assert result == {"during": 0, "tap": True, "after": 1,
                      "ids": ["a", "b", "c"], "idle": 1}
    assert page.console_errors == []
