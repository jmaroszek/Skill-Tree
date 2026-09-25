"""Regression tests for the Details interaction critical path."""

import inspect
from pathlib import Path
from types import SimpleNamespace

import dash
from dash import html
from dash.development.base_component import Component

import details_callbacks
from config import ConfigManager
from details_callbacks import register_details_callbacks
from event_callbacks import register_event_callbacks
from graph_manager import GraphManager
from models import EDGE_NEEDS_HARD, Node
import style_tokens as tokens


THEME_CSS = Path(__file__).resolve().parents[1] / "assets" / "theme.css"


def _app_with(*registrars):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    for registrar in registrars:
        registrar(app)
    return app


def _spec_for_output(app, output):
    return next(
        spec for key, spec in app.callback_map.items()
        if key == output or output in key
    )


def _input_ids(spec):
    return {item["id"] for item in spec["inputs"]}


def _state_ids(spec):
    return {item["id"] for item in spec["state"]}


def _raw_callback(spec):
    callback = spec["callback"]
    while hasattr(callback, "__wrapped__"):
        callback = callback.__wrapped__
    return callback


def _walk_components(component):
    if isinstance(component, Component):
        yield component
        children = getattr(component, "children", None)
        if children is not None:
            yield from _walk_components(children)
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk_components(child)


def test_hidden_heavy_callbacks_do_not_subscribe_to_every_tab_switch():
    app = _app_with(register_details_callbacks, register_event_callbacks)

    details_options = _spec_for_output(app, "details-node-select.options")
    assert "main-tabs" not in _input_ids(details_options)

    for output in (
        "events-list-container.children",
        "events-search-datalist.children",
        "event-trigger-node.options",
    ):
        spec = _spec_for_output(app, output)
        assert "main-tabs" not in _input_ids(spec)
        assert "events-active-store" in _input_ids(spec)


def test_empty_suggestions_do_not_rebuild_after_selection():
    app = _app_with(register_details_callbacks)
    spec = _spec_for_output(app, "details-suggestions-container.children")
    assert "details-selected-node-store" not in _input_ids(spec)
    assert _input_ids(spec) >= {
        "graph-version-store",
        "filter-context",
        "filter-subcontext",
        "filter-done",
        "filter-value",
        "filter-interest",
        "filter-time",
        "filter-time-unit",
        "filter-difficulty",
        "filter-node-type",
        "filter-dormant",
        "settings-save-status",
    }


def _suggestion_node(**overrides):
    fields = dict(
        name="Sleep", type="Goal", description="",
        value=8, time_o=1, time_m=2, time_p=3,
        interest=8, difficulty=4, status="Open",
        context="Health", subcontext="Sleep",
    )
    fields.update(overrides)
    return Node(**fields)


def test_details_suggestion_is_a_native_button_with_name_and_context():
    from details_layout import _build_suggestion_row

    row = _build_suggestion_row(_suggestion_node())

    assert type(row).__name__ == "Button"
    assert row.type == "button"
    assert row.className == "details-suggestion-row"
    assert row.id == {"type": "details-suggestion-item", "index": "Sleep"}
    # Every suggestion is a Goal, so no type strip or label: just the name and
    # the context alone, with no corner badge when there is no priority.
    (copy,) = row.children
    assert copy.children[0].children == "Sleep"
    assert copy.children[1].children == "Health"
    assert getattr(row, "aria-label") == "View Sleep. Health"


def test_every_subtask_row_has_edit_action_and_no_remove_action():
    from details_layout import build_details_subtasks_table

    manager = GraphManager()
    parent = _suggestion_node(name="Parent")
    child = _suggestion_node(name="Child", type="Learn")
    grandchild = _suggestion_node(name="Grandchild", type="Learn")
    for node in (parent, child, grandchild):
        manager.add_node(node)
    manager.add_edge("Child", "Parent", EDGE_NEEDS_HARD)
    manager.add_edge("Grandchild", "Child", EDGE_NEEDS_HARD)

    table = build_details_subtasks_table(
        [child, grandchild], manager, manager.get_edges(), "Parent")
    ids = [getattr(component, "id", None)
           for component in _walk_components(table)]

    assert {item["index"] for item in ids
            if isinstance(item, dict)
            and item.get("type") == "details-subtask-edit"} == {
                "Child", "Grandchild",
            }
    assert not any(isinstance(item, dict)
                   and item.get("type") == "details-subtask-remove"
                   for item in ids)

    assert "details-subtasks-table" in table.className
    for row in table.children[1].children:
        assert row.className == "details-subtask-row"
        action_group = row.children[-1].children
        assert action_group.className == "details-subtask-actions"
        assert action_group.children[0].children[0].className == "bi bi-pencil"


def test_subtask_name_column_is_capped_and_keeps_full_name_on_hover():
    from details_layout import build_details_subtasks_table

    manager = GraphManager()
    parent = _suggestion_node(name="Parent")
    long_name = "A long but still useful subtask name that must not crowd metadata"
    child = _suggestion_node(name=long_name, type="Learn")
    for node in (parent, child):
        manager.add_node(node)
    manager.add_edge(long_name, "Parent", EDGE_NEEDS_HARD)

    table = build_details_subtasks_table(
        [child], manager, manager.get_edges(), "Parent"
    )
    heading = table.children[0].children.children[0]
    name_cell = table.children[1].children[0].children[0]
    name_link = name_cell.children

    assert heading.className == "details-subtask-name-heading"
    assert name_cell.className == "details-subtask-name-cell"
    assert name_link.className == "details-subtask-name-link"
    assert name_link.children == long_name
    assert name_link.title == f"{long_name} — open in Details"

    css = THEME_CSS.read_text(encoding="utf-8")
    assert "width: 360px;" in css
    assert "max-width: 360px;" in css
    assert "text-overflow: ellipsis;" in css
    assert "white-space: nowrap;" in css


def test_subtasks_header_leaves_a_block_gap_before_the_table():
    from details_layout import build_details_tab_content

    content = build_details_tab_content()
    header = next(
        component for component in _walk_components(content)
        if isinstance(getattr(component, "children", None), list)
        and "details-subtask-toggles-bottom" in {
            getattr(child, "id", None) for child in component.children
        }
    )

    assert header.style["marginBottom"] == tokens.SPACE_BLOCK


def test_subtask_edit_actions_reveal_on_row_intent_and_remain_available_on_touch():
    css = THEME_CSS.read_text(encoding="utf-8")

    assert ".details-subtasks-table .details-subtask-actions" in css
    assert ".details-subtask-row:hover .details-subtask-actions" in css
    assert ".details-subtask-actions:focus-within" in css
    assert "@media (hover: none), (pointer: coarse)" in css


def test_subtask_pencil_opens_that_node_in_editor(monkeypatch):
    app = _app_with(register_details_callbacks)
    callback = _raw_callback(_spec_for_output(
        app, "details-edit-trigger-input.value"))
    monkeypatch.setattr(
        details_callbacks, "ctx",
        SimpleNamespace(triggered_id={
            "type": "details-subtask-edit", "index": "Child",
        }))
    monkeypatch.setattr("time.time_ns", lambda: 123)

    assert callback(0, [1], "Parent") == "Child|123"


def test_details_suggestion_without_context_keeps_an_empty_second_line():
    from details_layout import _build_suggestion_row

    row = _build_suggestion_row(_suggestion_node(context=None, subcontext=None),
                                priority=12)

    copy, badge = row.children
    assert copy.children[1].children == ""
    assert getattr(row, "aria-label") == "View Sleep. Priority score 12"


def test_priority_rank_badges_share_the_orange_rank_color():
    """Regression: the Details rank badge once borrowed the Goal yellow."""
    from details_layout import _build_suggestion_row, build_goal_card

    row = _build_suggestion_row(_suggestion_node(), priority_rank=2)
    badge = row.children[-1]
    assert badge.children == "2"
    assert badge.style["backgroundColor"] == "#f39c12"
    assert getattr(row, "aria-label") == "View Sleep. Priority 2, Health"

    card = build_goal_card("Sleep", "Open", {"total": 0}, 0, priority_rank=2)
    rank_trigger = card.children[1].children[1].children[0]
    assert rank_trigger.children.style["backgroundColor"] == "#f39c12"


def test_explore_suggestion_shows_the_goal_score_like_the_sidebar_card():
    from details_layout import _build_suggestion_row, build_goal_card

    row = _build_suggestion_row(_suggestion_node(), priority=54)
    badge = row.children[-1]
    assert badge.children == "54"
    assert getattr(row, "aria-label") == "View Sleep. Priority score 54, Health"

    card = build_goal_card("Sleep", "Open", {"total": 0}, 0, corner_text="54")
    sidebar_badge = card.children[1].children[1].children[1]
    assert badge.style == sidebar_badge.style


def test_details_suggestions_use_explore_copy_and_filter_aware_empty_state():
    from details_layout import build_details_suggestions

    row = html.Div("Area")
    section = build_details_suggestions([], [row])[0]
    assert section.children[0].children == "Goals"
    assert build_details_suggestions([], []).children == "No areas to explore yet."
    assert build_details_suggestions(
        [], [], filters_active=True
    ).children == "No areas match the current filters."

    sections = build_details_suggestions([row], [], filters_active=True)
    assert sections[1].children[0].children == "Goals"
    assert sections[1].children[1].children[0].children == (
        "No areas match the current filters."
    )


def test_empty_suggestion_callback_keeps_priorities_pinned_and_filters_explore():
    manager = details_callbacks.graph_manager
    for node in (
        Node(
            name="Priority", type="Goal", description="", value=8,
            time_o=1, time_m=2, time_p=3, interest=8, difficulty=5,
            status="Open", context="Mind",
        ),
        Node(
            name="Priority child", type="Learn", description="", value=8,
            time_o=1, time_m=2, time_p=3, interest=8, difficulty=5,
            status="Open", context="Mind",
        ),
        Node(
            name="Explore", type="Goal", description="", value=7,
            time_o=1, time_m=2, time_p=3, interest=7, difficulty=5,
            status="Open", context="Body",
        ),
        Node(
            name="Explore child", type="Learn", description="", value=7,
            time_o=1, time_m=2, time_p=3, interest=7, difficulty=5,
            status="Open", context="Body",
        ),
    ):
        manager.add_node(node)
    manager.add_edge("Priority child", "Priority", EDGE_NEEDS_HARD)
    manager.add_edge("Explore child", "Explore", EDGE_NEEDS_HARD)
    ConfigManager.set_priority_goals(["Priority"])

    app = _app_with(register_details_callbacks)
    callback = _raw_callback(_spec_for_output(
        app, "details-suggestions-container.children"))

    def suggestion_names(component):
        names = []
        stack = [component]
        while stack:
            current = stack.pop()
            if isinstance(current, (list, tuple)):
                stack.extend(current)
                continue
            if not isinstance(current, Component):
                continue
            component_id = getattr(current, "id", None)
            if (isinstance(component_id, dict)
                    and component_id.get("type") == "details-suggestion-item"):
                names.append(component_id["index"])
            children = getattr(current, "children", None)
            if children is not None:
                stack.append(children)
        return set(names)

    def render(context):
        return callback(
            0, 0, context, [], [], 1, 1, None, "hours", 10, [], [], ""
        )

    assert suggestion_names(render([])) == {"Priority", "Explore"}
    filtered = render(["Mind"])
    assert suggestion_names(filtered) == {"Priority"}
    assert "No areas match the current filters." in str(filtered)


def test_event_selection_does_not_refresh_unrelated_data(monkeypatch):
    from types import SimpleNamespace
    import event_callbacks
    from models import Event

    app = _app_with(register_event_callbacks)
    monkeypatch.setattr(event_callbacks, 'ctx', SimpleNamespace(
        triggered_id={'type': 'event-card', 'index': 'Music'}))
    monkeypatch.setattr(event_callbacks.event_manager, 'get_event',
                        lambda name: Event(name=name))
    monkeypatch.setattr(event_callbacks.event_manager, 'get_event_nodes',
                        lambda name: [])
    for spec in app.callback_map.values():
        if 'callback' not in spec:
            continue
        callback = _raw_callback(spec)
        if callback.__name__ == 'select_event':
            result = callback([1], 'tab-events')
            assert result[0] == 'Music'
            assert result[1] is dash.no_update
        elif callback.__name__ == 'handle_event_context_action':
            result = callback('Music|edit', 'tab-events')
            assert result[0] == 'Music'
            assert result[1] is dash.no_update


def test_event_graph_nodes_carry_shared_tooltip_attributes(monkeypatch):
    import event_callbacks

    node = Node(
        name="Dormant", type="Action", description="A future action",
        value=8, time_o=2, time_m=4, time_p=8,
        interest=7, difficulty=6, status="Open",
        context="Self", subcontext="Projects", dormant=1,
        time_mode="manual", value_mode="manual",
    )
    app = _app_with(register_event_callbacks)
    monkeypatch.setattr(
        event_callbacks.event_manager, "get_event_nodes",
        lambda _event: [{"node": node}],
    )
    monkeypatch.setattr(event_callbacks.graph_manager, "get_edges", lambda: [])
    monkeypatch.setattr(
        event_callbacks.graph_manager, "get_node",
        lambda name: node if name == node.name else None,
    )
    monkeypatch.setattr(
        event_callbacks.event_manager, "get_trigger_node_names", lambda: set(),
    )

    callback = next(
        _raw_callback(spec)
        for spec in app.callback_map.values()
        if spec.get("callback")
        and _raw_callback(spec).__name__ == "render_event_graph"
    )
    elements = callback("Future", 0)
    data = next(
        element["data"] for element in elements
        if "source" not in element["data"]
    )

    assert data["id"] == "Dormant"
    assert data["label"] == "Dormant"
    assert data["dormant"] == 1
    assert {
        key: data[key]
        for key in (
            "type", "status", "value", "interest", "difficulty",
            "context", "subcontext", "time", "time_mode", "value_mode",
        )
    } == {
        key: node.to_dict()[key]
        for key in (
            "type", "status", "value", "interest", "difficulty",
            "context", "subcontext", "time", "time_mode", "value_mode",
        )
    }


def test_selection_callback_no_longer_serializes_subtasks_table():
    app = _app_with(register_details_callbacks)
    spec = _spec_for_output(app, "details-empty.style")
    output_key = next(
        key for key in app.callback_map if "details-empty.style" in key
    )
    assert "details-subtasks-table-container.children" not in output_key

    callback = _raw_callback(spec)
    arity = len(inspect.signature(callback).parameters)
    result = callback(*[None] * arity)
    assert len(result) == 24


def test_subtasks_table_waits_for_current_layout(monkeypatch):
    app = _app_with(register_details_callbacks)
    spec = _spec_for_output(app, "details-subtasks-table-container.children")
    assert _input_ids(spec) >= {
        "details-selected-node-store",
        "details-layout-settled-trigger-input",
    }
    callback = _raw_callback(spec)
    args = [
        "Current", "", 0, 0,
        ["include"], [], 6,
        None, None, [], 1, 1, None, "All", [], [], [], False,
    ]

    monkeypatch.setattr(
        details_callbacks, "get_trigger_id",
        lambda: "details-selected-node-store")
    loading = callback(*args)
    assert loading.children == "Loading subtasks…"

    monkeypatch.setattr(
        details_callbacks, "get_trigger_id",
        lambda: "details-layout-settled-trigger-input")
    args[1] = '{"root":"Superseded","settledAt":1}'
    assert callback(*args) is dash.no_update


def test_simulation_waits_for_its_layout_signal_unless_frozen():
    app = _app_with(register_details_callbacks)
    spec = _spec_for_output(app, "details-sim-request.data")

    assert "details-simulation-settled-trigger-input" in _input_ids(spec)
    assert "details-layout-settled-trigger-input" not in _input_ids(spec)
    assert "details-freeze-rerender-store" in _state_ids(spec)


def test_frozen_selection_renders_without_waiting_for_layout(monkeypatch):
    manager = GraphManager()
    manager.add_node(Node(
        name="Current", type="Goal", description="", value=5,
        time_o=1, time_m=2, time_p=3, interest=5, difficulty=5,
        status="Open", context="Mind", time_mode="inherited"))
    manager.add_node(Node(
        name="Child", type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=3, interest=5, difficulty=5,
        status="Open", context="Mind"))
    manager.add_edge("Child", "Current", EDGE_NEEDS_HARD)

    app = _app_with(register_details_callbacks)
    callback = _raw_callback(_spec_for_output(
        app, "details-subtasks-table-container.children"))
    monkeypatch.setattr(
        details_callbacks, "get_trigger_id",
        lambda: "details-selected-node-store")
    result = callback(
        "Current", "", 0, 0,
        ["include"], [], 6,
        None, None, [], 1, 1, None, "All", [], [], [], True,
    )

    assert "Child" in str(result)
    assert "Loading subtasks" not in str(result)


def test_details_layout_declares_settled_trigger():
    from details_layout import build_details_tab_content

    def collect_ids(component):
        found = set()
        stack = [component]
        while stack:
            node = stack.pop()
            if isinstance(node, (list, tuple)):
                stack.extend(node)
                continue
            if not isinstance(node, Component):
                continue
            component_id = getattr(node, "id", None)
            if isinstance(component_id, str):
                found.add(component_id)
            children = getattr(node, "children", None)
            if children is not None:
                stack.append(children)
        return found

    assert "details-layout-settled-trigger-input" in collect_ids(
        build_details_tab_content())
    assert "details-simulation-settled-trigger-input" in collect_ids(
        build_details_tab_content())


def test_explain_chart_starts_hidden_behind_a_quiet_placeholder():
    from details_layout import build_details_tab_content

    def by_id(component, component_id):
        stack = [component]
        while stack:
            node = stack.pop()
            if isinstance(node, (list, tuple)):
                stack.extend(node)
                continue
            if not isinstance(node, Component):
                continue
            if getattr(node, "id", None) == component_id:
                return node
            children = getattr(node, "children", None)
            if children is not None:
                stack.append(children)
        raise AssertionError(f"Missing component {component_id}")

    content = build_details_tab_content()
    chart = by_id(content, "details-explain-chart")
    placeholder = by_id(content, "details-explain-chart-placeholder")

    assert chart.style == {"display": "none"}
    assert placeholder.children == "Preparing explanation…"
    assert placeholder.role == "status"
    assert getattr(placeholder, "aria-live") == "polite"


def test_explain_chart_waits_for_the_selected_nodes_contributors():
    app = _app_with(register_details_callbacks)
    spec = _spec_for_output(app, "details-explain-chart.figure")
    callback = _raw_callback(spec)
    contributor = {
        "name": "Current",
        "contribution": 4.0,
        "via": "Self",
        "pct_of_tv": 100.0,
        "depth": 0,
        "weight": 1.0,
        "iv": 4.0,
    }

    waiting = callback(10, [contributor], None, True, "Current")
    assert waiting[0] is dash.no_update
    assert waiting[1] == {"display": "none"}
    assert waiting[3] == "Preparing explanation…"

    stale = callback(10, [contributor], "Previous", True, "Current")
    assert stale[1] == {"display": "none"}

    ready = callback(10, [contributor], "Current", True, "Current")
    assert len(ready[0].data) == 1
    assert ready[1] == {}
    assert ready[2] == {"display": "none"}
    assert ready[3] == ""


def test_refresh_does_not_rewrite_an_unchanged_selection(monkeypatch):
    """A same-value store write would re-fire render_details_subtasks with a
    `details-selected-node-store` trigger, stranding the table on its
    placeholder: a same-root refresh produces no layout settle to release it.
    """
    manager = GraphManager()
    manager.add_node(Node(
        name="Current", type="Goal", description="", value=5,
        time_o=1, time_m=2, time_p=3, interest=5, difficulty=5,
        status="Open", context="Mind", time_mode="inherited"))

    app = _app_with(register_details_callbacks)
    spec = _spec_for_output(app, "details-selected-node-store.data")
    assert "details-selected-node-store" in _state_ids(spec)

    callback = _raw_callback(spec)
    arity = len(inspect.signature(callback).parameters)
    store_slot = 2

    def call(node_name, current_selection):
        args = [None] * arity
        args[0] = node_name
        args[-1] = current_selection
        return callback(*args)

    assert call("Current", "Current")[store_slot] is dash.no_update
    assert call("Current", "Other")[store_slot] == "Current"
    assert call(None, None)[store_slot] is dash.no_update
    assert call(None, "Current")[store_slot] is None
