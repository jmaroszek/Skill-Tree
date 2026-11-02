"""The Goals sidebar: how its list follows the left panel, and how it's built."""

from contextvars import copy_context
import shutil
import subprocess

import dash
from dash._callback_context import context_value
from dash._utils import AttributeDict
import dash_bootstrap_components as dbc
import pytest

from skilltree.store import database
from skilltree.features.goals import callbacks as sidebars_callbacks
from skilltree.store.graph.manager import GraphManager
from skilltree.domain.models import Node
from skilltree.features.goals.layout import build_goals_sidebar
from skilltree.services import AppServices
from support.paths import asset_file
from support.layout import find


ASSET = asset_file("goals_sidebar.js")


def test_goals_list_follows_the_left_panel():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Goals sidebar contract")

    script = r'''
const assert = require('node:assert/strict');
const setProps = [];
global.window = {
    dash_clientside: {
        no_update: 'NO',
        callback_context: {triggered: []},
        set_props: (id, props) => setProps.push([id, props]),
    }
};
const listeners = {};
let shownCards = false;
global.document = {
    addEventListener: (type, fn) => { listeners[type] = fn; },
    getElementById: () => ({querySelector: () => (shownCards ? {} : null)}),
};
// Timers run only when the test says the slide has finished.
let timers = [];
global.setTimeout = fn => { timers.push(fn); return fn; };
global.clearTimeout = fn => { timers = timers.filter(t => t !== fn); };
const finishSlide = () => {
    const due = timers;
    timers = [];
    due.forEach(fn => fn());
};
require(process.argv[1]);
const follow = window.dash_clientside.goals.follow_left_panel;

const fired = () => setProps.map(call => call[0]);

// Opening waits for the slide to finish before it refreshes the list.
follow('goals');
assert.deepEqual(setProps, []);
finishSlide();
assert.deepEqual(fired(), ['goals-ui-refresh-trigger']);
setProps.length = 0;

// Another panel opening, or the same one, starts nothing new.
follow('goals');
finishSlide();
assert.deepEqual(setProps, []);

// Closing before the slide finishes drops the pending refresh.
follow(null);
follow('goals');
follow('editor');
finishSlide();
assert.deepEqual(setProps, []);

// A finished close slide, whoever closed it, asks for the list to clear.
const slideEnd = (id, property, isOpen) => listeners.transitionend(
    {target: {id: id, classList: {contains: () => isOpen}}, propertyName: property});
slideEnd('details-goal-sidebar', 'transform', false);
assert.equal(setProps.length, 1);
assert.equal(setProps[0][0], 'goals-ui-refresh-trigger');
setProps.length = 0;
// An open slide, another element's slide, or another property doesn't.
slideEnd('details-goal-sidebar', 'transform', true);
slideEnd('events-sidebar-container', 'transform', false);
slideEnd('details-goal-sidebar', 'opacity', false);
assert.deepEqual(setProps, []);

// A reopen shows the last built list at once if nothing it came from has
// changed. The rebuild still follows the slide.
const remember = window.dash_clientside.goals.remember_list;
const cards = [{type: 'Div', namespace: 'dash_html_components', props: {id: 'a'}}];
const cover = {type: 'Div', namespace: 'dash_html_components',
               props: {className: 'loading-cover'}};
const sources = [7, 2, '', 'manual', null];
remember(cards, ...sources);
remember(cover, ...sources);  // the cover is never remembered
follow('goals', ...sources);
finishSlide();
assert.deepEqual(fired(), ['details-goal-list-container', 'goals-ui-refresh-trigger']);
assert.deepEqual(setProps[0][1], {children: cards});
setProps.length = 0;
follow(null, ...sources);

// Cards still showing (a close reversed mid-slide) are left alone.
shownCards = true;
follow('goals', ...sources);
finishSlide();
assert.deepEqual(fired(), ['goals-ui-refresh-trigger']);
setProps.length = 0;
follow(null, ...sources);
shownCards = false;

// A change to the graph, priorities, search, sort or order waits for the
// rebuild.
[[8, 2, '', 'manual', null], [7, 3, '', 'manual', null], [7, 2, 'x', 'manual', null],
 [7, 2, '', 'priority', null], [7, 2, '', 'manual', ['a']]].forEach(changed => {
    follow('goals', ...changed);
    finishSlide();
    assert.deepEqual(fired(), ['goals-ui-refresh-trigger']);
    setProps.length = 0;
    follow(null, ...changed);
});
'''
    result = subprocess.run(
        [node, "-e", script, str(ASSET)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_goal_list_shows_a_spinner_until_its_first_render():
    container = find(build_goals_sidebar(), "details-goal-list-container")
    cover = container.children
    assert cover.className == "loading-cover"
    assert isinstance(cover.children[0], dbc.Spinner)


def _render_goal_list(trigger, left_panel):
    """Run render_goal_list as Dash would for a single triggering input."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_goals_callbacks(app, AppServices())
    render = next(
        spec["callback"].__wrapped__ for spec in app.callback_map.values()
        if getattr(spec.get("callback"), "__wrapped__", None) is not None
        and spec["callback"].__wrapped__.__name__ == "render_goal_list"
    )

    def run():
        context_value.set(AttributeDict(triggered_inputs=[{"prop_id": trigger, "value": 1}]))
        return render("tab-next", None, None, None, None, "priority", None, None,
                      left_panel)
    return copy_context().run(run)


def _add_goals(*names):
    manager = GraphManager()
    for name in names:
        manager.add_node(Node(name=name, type="Goal", description="", value=5,
                              interest=5, difficulty=5, time_o=1, time_m=2,
                              time_p=4, context="Mind", status="Open"))


def test_goal_list_builds_from_one_database_snapshot(monkeypatch):
    _add_goals("Alpha", "Beta", "Gamma")
    built = []

    class CountingSnapshot(database.ReadSnapshot):
        def __init__(self):
            built.append(self)
            super().__init__()

    monkeypatch.setattr(database, "ReadSnapshot", CountingSnapshot)
    cards = _render_goal_list("goals-ui-refresh-trigger.data", "goals")
    assert len(cards) == 3
    assert len(built) == 1


def test_closed_goal_list_never_builds_and_clears_after_its_slide():
    """Hidden cards cost every Dash store update, so a closed sidebar holds
    only the cover: graph changes leave it alone, and a finished close slide
    swaps the cards out for it."""
    _add_goals("Alpha")
    assert _render_goal_list("graph-version-store.data", None) is dash.no_update
    cover = _render_goal_list("goals-ui-refresh-trigger.data", "editor")
    assert cover.className == "loading-cover"


def test_nothing_builds_the_goal_list_at_startup(services):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    sidebars_callbacks.register_goals_callbacks(app, services)
    render = next(c for c in app._callback_list
                  if c["output"] == "details-goal-list-container.children")
    assert "elements-pending-store" not in [i["id"] for i in render["inputs"]]
    assert all("goals-prewarm-store" not in c["output"] for c in app._callback_list)


def test_analyze_does_not_render_at_startup(services):
    """Its charts cost about 0.6 s of browser work, and the startup cover
    waited for them. Only the Analyze tab's own hover prewarm writes the
    store now."""
    from skilltree.features.analyze import callbacks as analyze_callbacks

    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    analyze_callbacks.register_analyze_callbacks(app, services)
    assert not any(c["output"].startswith("analyze-prewarm-store")
                   for c in app._callback_list)


def _listed(cards):
    return [card.id["index"] for card in cards] if isinstance(cards, list) else []


def test_a_goal_with_all_its_work_done_stays_while_it_holds_a_rank():
    from skilltree.domain.models import EDGE_NEEDS_HARD, STATUS_DONE
    from skilltree.features.goals.callbacks import _goal_list
    from skilltree.store import settings
    from skilltree.store.graph.manager import GraphManager
    from support.graphs import make_node

    manager = GraphManager()
    for name, kind in (("Ranked", "Goal"), ("Plain", "Goal"), ("Work A", "Learn"), ("Work B", "Learn")):
        manager.add_node(make_node(name, type=kind))
    manager.add_edge("Work A", "Ranked", EDGE_NEEDS_HARD)
    manager.add_edge("Work B", "Plain", EDGE_NEEDS_HARD)
    for name in ("Work A", "Work B"):
        node = manager.get_node(name)
        node.status = STATUS_DONE
        manager.update_node(node)
    settings.PRIORITY_GOALS.set(["Ranked"])

    assert _listed(_goal_list(manager, "", "priority", [], None)) == ["Ranked"]

    settings.PRIORITY_GOALS.set([])
    assert _listed(_goal_list(manager, "", "priority", [], None)) == []


def test_the_goals_search_covers_aliases_and_descriptions():
    from skilltree.features.goals.callbacks import _goal_list
    from skilltree.store.graph.manager import GraphManager
    from support.graphs import make_node

    manager = GraphManager()
    manager.add_node(make_node("Sleep", type="Goal", description="Rest well"))
    manager.add_node(make_node("Cooking", type="Goal", description="Food"))
    manager.set_aliases("Sleep", ["Shuteye"])
    assert _listed(_goal_list(manager, "shut", "priority", [], None)) == ["Sleep"]
    assert _listed(_goal_list(manager, "rest", "priority", [], None)) == ["Sleep"]
    assert _listed(_goal_list(manager, "food", "priority", [], None)) == ["Cooking"]
