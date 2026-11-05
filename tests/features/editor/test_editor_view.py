"""A node load sends everything the editor shows with the values (view.py).

The editor used to draw a load in up to eight frames: the values first, then
each callback that follows them. Some of those rules run in the browser, for the
user's own clicks, and view.py has a Python twin of each. These tests run the
JavaScript in Node and check the twins agree, so a change to one that misses the
other fails here instead of flickering in the app.
"""
import itertools
import json
import shutil
import subprocess

import dash
import pytest

from skilltree.domain.models import Node
from skilltree.features.editor import view
from skilltree.features.editor.callbacks import _filled, register_editor_callbacks
from skilltree.features.editor.form import NEW_NODE_SNAPSHOT, build_editor_snapshot
from skilltree.store import settings
from skilltree.store.resources import get_sections
from skilltree.ui.components.context_picker import (
    build_context_taxonomy,
    picker_state,
    register_context_picker_callbacks,
)
from support.callbacks import registered
from support.clientside import clientside_source
from support.paths import asset_file


def _app(services):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_editor_callbacks(app, services)
    register_context_picker_callbacks(app, services)
    return app


def _source(app, output):
    try:
        return clientside_source(app, output)
    except LookupError:
        # time_hour_hints sets its functions as one object, which the shared
        # lookup doesn't match.
        spec = next(c for c in app._callback_list
                    if c.get("clientside_function") and output in c["output"])
        function = spec["clientside_function"]
        source = asset_file("time_hour_hints.js").read_text(encoding="utf-8")
        assert f"dash_clientside.{function['namespace']} =" in source
        return source, function["namespace"], function["function_name"]


def _run_js(app, output, cases, tmp_path):
    """The clientside function writing ``output``, called with each case's args."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to run the editor's clientside rules")
    source, namespace, name = _source(app, output)
    script = f"""
global.document = {{getElementById: () => null}};
global.window = {{SkillTree: {{}}, dash_clientside: {{no_update: "NO_UPDATE",
    callback_context: {{triggered: []}}}}}};
{source}
const fn = window.dash_clientside[{json.dumps(namespace)}][{json.dumps(name)}];
console.log(JSON.stringify({json.dumps(cases)}.map(args => fn(...args))));
"""
    path = tmp_path / "rule.js"
    path.write_text(script, encoding="utf-8")
    result = subprocess.run([node, str(path)], capture_output=True, text=True,
                            encoding="utf-8", timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _same(python, javascript):
    """Python's tuples are the browser's arrays."""
    return json.loads(json.dumps(python)) == javascript


SWITCH = [None, [], ["inherited"]]
HABIT = [None, [], ["habit"]]
TYPES = ["", "Goal", "Learn", "Action", "Resource", "Milestone"]


def test_the_time_sections_follow_the_browsers_rule(services, tmp_path):
    cases = [list(c) for c in itertools.product(SWITCH, HABIT)]
    answers = _run_js(_app(services), "section-time-omp.style", cases, tmp_path)
    for (time_mode, habit_mode), answer in zip(cases, answers):
        assert _same(view.time_mode_styles(time_mode, habit_mode), answer), (time_mode, habit_mode)


def test_the_ratings_follow_the_browsers_rule(services, tmp_path):
    cases = [[mode] for mode in SWITCH]
    answers = _run_js(_app(services), "section-ratings.style", cases, tmp_path)
    for (mode,), answer in zip(cases, answers):
        assert _same(view.ratings_style(mode), answer), mode


def test_effort_follows_the_browsers_rule(services, tmp_path):
    cases = [list(c) for c in itertools.product(TYPES, SWITCH)]
    answers = _run_js(_app(services), "node-effort-row.style", cases, tmp_path)
    for (node_type, time_mode), answer in zip(cases, answers):
        assert _same(view.effort_styles(node_type, time_mode), answer), (node_type, time_mode)


def test_the_dormant_section_follows_the_browsers_rule(services, tmp_path):
    snapshots = [
        None,
        {},
        {"dormancy": {"dormant": True, "event": "Trip", "wake_date": "2026-12-01"}},
        {"dormancy": {"dormant": True, "event": None, "wake_date": None}},
        {"dormancy": {"dormant": False, "event": None, "wake_date": None}},
    ]
    cases = [list(c) for c in itertools.product(
        [[], ["dormant"]], [None, [], ["now"]], [[], ["Done"]],
        [None, "", "__new__", "Trip"], [[], ["on"]], snapshots)]
    answers = _run_js(_app(services), "node-now-wrapper.style", cases, tmp_path)
    for case, answer in zip(cases, answers):
        assert _same(view.dormancy_styles(*case), answer), case


def test_the_hour_hints_follow_the_browsers_rule(services, tmp_path):
    values = [None, 0, 0.01, 0.04, 0.05, 2, 2.25, 7, 1234.56, -1]
    brackets = [[o, m, p] for o, m, p in zip(values, values[3:] + values[:3], values[6:] + values[:6])]
    times = [settings.DEFAULT_TIME_SETTINGS,
             {**settings.DEFAULT_TIME_SETTINGS, "show_hour_equivalents": False},
             {"hours_per_week": 0, "hours_per_month": 40},
             {}]
    cases = [[*bracket, unit, time_settings] for bracket, unit, time_settings in itertools.product(
        brackets, ["hours", "days", "weeks", "months", "years", None], times)]
    answers = _run_js(_app(services), "node-time-o-hours.children", cases, tmp_path)
    for case, answer in zip(cases, answers):
        texts, styles, row_class = view.hour_hints(case[:3], case[3], case[4])
        assert _same([*texts, *styles, row_class], answer), case


def test_the_context_picker_state_is_the_browsers_to_the_letter(services, tmp_path):
    """Exactly what the mirror writes, so the mirror's later answer leaves the
    picker alone."""
    settings.CONTEXTS.set([*settings.CONTEXTS.get(), "Café"])
    taxonomy = build_context_taxonomy()
    context = taxonomy[0]["context"]
    subcontext = (taxonomy[0]["subcontexts"] or [""])[0]
    cases = [[taxonomy, None, None], [taxonomy, "", ""], [taxonomy, context, ""],
             [taxonomy, context, subcontext], [taxonomy, "Café", ""]]
    answers = _run_js(_app(services), "node-context-picker-state.children", cases, tmp_path)
    for (_taxonomy, ctx, sub), answer in zip(cases, answers):
        assert picker_state("single", ctx, sub) == answer


def test_only_tasks_offer_the_habit_switch():
    """A Goal's or Milestone's time is always inherited."""
    for node_type in TYPES:
        styles = view.type_section_styles(node_type)
        assert styles[3] == ({"display": "none"} if node_type in ("Goal", "Milestone") else {})


def test_every_view_output_has_a_callback_for_later_changes(services):
    """The load only sends what the callbacks would work out. They still answer
    the user's changes, so each output has a writer besides the load. The badge
    is the exception: nothing changes it while a node is open."""
    from skilltree.ui.canvas.callbacks import register_canvas_callbacks
    app = _app(services)
    register_canvas_callbacks(app, services)
    populate = next(spec["output"] for spec in app._callback_list
                    if spec["output"].startswith("..node-name.value"))
    others = " ".join(spec["output"] for spec in app._callback_list
                      if spec["output"] != populate)
    loaded_only = {"node-calibration-dismissed-badge"}
    for component, prop in view.VIEW_OUTPUTS.values():
        if component in loaded_only:
            continue
        assert f"{component}.{prop}" in others, (component, prop)


def _load(services, name):
    node = services.graph.get_node(name)
    snapshot = build_editor_snapshot(services.graph, services.events, name)
    return _filled(snapshot, [], status=node.status, original_name=name, node=node)


def test_a_loaded_goal_comes_with_its_sections_and_rows(services):
    services.graph.add_node(Node(name="Sleep", type="Goal", description="", value=5,
                                 time_o=None, time_m=None, time_p=None, interest=5,
                                 difficulty=5, status="Open", context="Health",
                                 time_mode="inherited"))
    services.graph.set_aliases("Sleep", ["Rest", "Shuteye"])
    out = _load(services, "Sleep")

    assert out["view_habit_toggle"] == {"display": "none"}
    assert out["view_time_omp"] == {"display": "none"}
    assert out["view_effort_row"] == {"display": "none"}
    assert len(out["view_alias_rows"]) == 2 and out["view_alias_label"] == "Aliases"
    assert out["view_save_disabled"] is False
    assert out["view_revert_disabled"] is False
    assert out["view_badge_style"] == {"display": "none"}


def test_a_loaded_task_shows_its_estimate_in_hours(services):
    services.graph.add_node(Node(name="Essay", type="Action", description="", value=5,
                                 time_o=10.0, time_m=20.0, time_p=40.0, interest=5,
                                 difficulty=5, status="Open", context="Mind"))
    out = _load(services, "Essay")

    assert out["view_habit_toggle"] == {}
    assert out["view_time_omp"] == {} and out["view_effort_row"] == {}
    snapshot = out["snapshot"]
    texts, _styles, row_class = view.hour_hints(
        [snapshot["time_o"], snapshot["time_m"], snapshot["time_p"]], snapshot["time_unit"],
        settings.TIME_SETTINGS.get())
    assert [out[f"view_hours_{f}_text"] for f in "omp"] == texts
    assert out["view_bracket_row"] == row_class


def test_a_node_left_out_of_calibration_says_where_to_undo_it(services):
    """The badge moved here from the review feature: the load is the only
    thing that changes it."""
    services.graph.add_node(Node(name="Skipped", type="Learn", description="", value=5,
                                 time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                                 status="Done", context="Mind", calibration_dismissed=1))
    out = _load(services, "Skipped")

    assert "restore in Reflection" in out["view_badge_text"]
    assert out["view_badge_style"] == {"display": "block"}


def test_a_blank_form_has_save_off_until_it_has_an_estimate():
    out = _filled(dict(NEW_NODE_SNAPSHOT), [], status="Open", original_name=None)

    assert out["view_save_disabled"] is True
    assert out["view_validation_ready"] == "false"
    assert out["view_revert_disabled"] is True and out["view_locate_disabled"] is True
    assert len(out["view_alias_rows"]) == 1


def test_a_load_draws_the_links_it_holds(services):
    services.graph.add_node(Node(name="Reading", type="Resource", description="", value=5,
                                 time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                                 status="Open", context="Mind",
                                 resource_links={get_sections()[0]["id"]: ["https://example.com"]}))
    assert "https://example.com" in repr(_load(services, "Reading")["resource_links"])


def test_nothing_draws_the_rows_from_their_store():
    """A callback that drew them from the store would draw a load's rows a pass
    after the rest, and draw them twice. Each writer of a store draws its rows."""
    handlers = registered(register_editor_callbacks)
    assert "render_aliases" not in handlers
    assert "render_resources" not in handlers
