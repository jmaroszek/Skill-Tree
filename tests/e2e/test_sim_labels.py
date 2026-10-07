"""The Time Simulation's P labels never overlap, at any panel width."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _idle  # noqa: E402
from test_keyboard import _seed  # noqa: E402

GAP_PX = 6   # sim_label_rows.js keeps labels in a row this far apart

_LABELS = """() => {
    const gd = document.querySelector('#details-sim-chart .js-plotly-plot');
    if (!gd || !gd.layout) return [];
    return [...gd.querySelectorAll('.annotation')].map(el => {
        const box = el.getBoundingClientRect();
        const note = gd.layout.annotations[+el.dataset.index];
        // A row is one label tall.
        return {text: note.text, row: Math.round((note.yshift || 0) / box.height),
                left: box.left, right: box.right, top: box.top, bottom: box.bottom};
    });
}"""


def _labels_at(page, width):
    page.evaluate(f"document.getElementById('details-sim-section').style.width = '{width}px'")
    # Settled once two reads a frame pair apart agree.
    page.wait_for_function(f"""async () => {{
        const read = {_LABELS};
        const before = JSON.stringify(read());
        await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
        await new Promise(r => setTimeout(r, 150));
        return read().length === 3 && JSON.stringify(read()) === before;
    }}""", timeout=10000)
    return page.evaluate(_LABELS)


def _apart(a, b):
    return a["right"] + GAP_PX <= b["left"] or b["right"] + GAP_PX <= a["left"]


def _check(labels):
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            # Drawn boxes never touch.
            assert (a["right"] <= b["left"] or b["right"] <= a["left"]
                    or a["bottom"] <= b["top"] or b["bottom"] <= a["top"]), labels
            if a["row"] == b["row"]:
                assert _apart(a, b), labels
        # A label is lifted only past rows it would overlap.
        for row in range(int(a["row"])):
            assert any(b["row"] == row and not _apart(a, b) for b in labels), labels


def test_percentile_labels_lift_only_when_they_would_overlap(page):
    _seed(page)
    page.click("a.nav-link:has-text('Details')")
    _idle(page)
    page.evaluate("SkillTree.menus.send('details-navigate-trigger-input', 'Goal|' + Date.now())")
    page.wait_for_selector("#details-sim-chart .annotation", timeout=30000)

    wide = _labels_at(page, 1000)
    _check(wide)
    assert [label["row"] for label in wide] == [0, 0, 0], wide

    narrow = _labels_at(page, 250)
    _check(narrow)
    assert max(label["row"] for label in narrow) >= 1, narrow

    # Widening again drops the labels back into one row.
    assert [label["row"] for label in _labels_at(page, 1000)] == [0, 0, 0]
    assert page.console_errors == []
