"""Settle lays out what the Nodes canvas shows, on the client, over its whole tween."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _idle, _seed  # noqa: E402

_WATCH_LAYOUT = """() => {
    const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
    const watch = window.settleWatch = {start: null, firstDraw: null, stop: null};
    cy.on('layoutstart', () => { if (watch.start === null) watch.start = performance.now(); });
    cy.on('render', () => {
        if (watch.start !== null && watch.firstDraw === null) watch.firstDraw = performance.now();
    });
    cy.on('layoutstop', () => {
        if (watch.start !== null && watch.stop === null) watch.stop = performance.now();
    });
}"""


def _open_nodes(page):
    _seed(page)
    page.click("a.nav-link:has-text('Nodes')")
    page.wait_for_function("SkillTree.canvasFirstPaintDone()")
    _idle(page)
    page.wait_for_timeout(1200)


def _settle(page):
    page.click("#btn-graph-settings")
    page.click("#graph-settings-relayout")
    page.wait_for_function("window.settleWatch.stop !== null", timeout=15000)
    return page.evaluate("window.settleWatch")


def test_settle_asks_the_server_for_nothing(page):
    """The core engine used to rebuild the whole canvas for a Settle. Its
    response, and the callbacks chained to it, landed inside the animation."""
    _open_nodes(page)
    page.evaluate(_WATCH_LAYOUT)
    requests = []

    def record(request):
        if request.url.endswith("/_dash-update-component"):
            body = request.post_data_json or {}
            requests.append({"output": body.get("output", ""),
                             "changed": body.get("changedPropIds", [])})
    page.on("request", record)
    _settle(page)
    _idle(page)
    page.wait_for_timeout(500)
    assert not [r for r in requests
                if "graph-settings-relayout.n_clicks" in r["changed"]
                or "elements-pending-store.data" in r["output"]], requests
    assert page.console_errors == []


def test_a_tween_runs_its_whole_duration_after_a_long_task(page):
    """Chrome stamps a frame with the time it was scheduled. A layout's own
    computation is a long task, and Cytoscape started the tween's clock at
    the stale stamp, so the tween skipped ahead by that much."""
    _open_nodes(page)
    page.evaluate(_WATCH_LAYOUT)
    # Stand in for a large graph's layout computation.
    page.evaluate("""() => {
        const cy = SkillTree.getCy(document.getElementById('cytoscape-graph'));
        cy.one('layoutstart', () => {
            const until = performance.now() + 400;
            while (performance.now() < until) { /* busy */ }
        });
    }""")
    watch = _settle(page)
    assert watch["firstDraw"] - watch["start"] >= 400, watch
    # The Settle's tween is 1 s long, from its first frame.
    assert watch["stop"] - watch["firstDraw"] >= 900, watch
    assert page.console_errors == []
