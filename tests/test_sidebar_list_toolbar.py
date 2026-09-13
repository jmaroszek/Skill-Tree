"""Goals/Events sidebar toolbar: the sort menus and the triggered-events divider."""

import dash
import pytest
from dash.development.base_component import Component

import database
from event_manager import EventManager
from list_toolbar import EVENTS_SORT, GOALS_SORT, SORT_MENUS
from models import Event


@pytest.fixture(autouse=True)
def temp_database(monkeypatch, tmp_path):
    tmp_db_path = str(tmp_path / "test_skilltree.db")
    monkeypatch.setattr(database, "get_db_path", lambda: tmp_db_path)
    database._initialized = False
    database.init_db()
    yield tmp_db_path


def _walk(component):
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(reversed(node))
            continue
        if not isinstance(node, Component):
            continue
        yield node
        children = getattr(node, "children", None)
        if children is not None:
            stack.append(children)


def _find(component, component_id):
    for node in _walk(component):
        if getattr(node, "id", None) == component_id:
            return node
    raise AssertionError(f"Missing component {component_id}")


def _text(component):
    parts = []
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            parts.append(node)
        elif isinstance(node, (list, tuple)):
            stack.extend(reversed(node))
        elif isinstance(node, Component):
            children = getattr(node, "children", None)
            if children is not None:
                stack.append(children)
    return "".join(parts)


def _has_class(component, class_name):
    return any(class_name in (getattr(node, "className", None) or "").split()
               for node in _walk(component))


@pytest.fixture
def layout():
    from layout import build_app_layout
    return build_app_layout([], env="sandbox")


@pytest.mark.parametrize("sort", SORT_MENUS, ids=lambda s: s.prefix)
def test_each_sidebar_has_a_sort_button_menu_and_store(layout, sort):
    button = _find(layout, sort.button_id)
    assert "sort-menu-button" in button.className
    assert getattr(button, "data-sort-menu") == sort.menu_id
    assert getattr(button, "data-sort-input") == sort.input_id

    menu = _find(layout, sort.menu_id)
    assert "ctx-menu" in menu.className
    items = [child for child in menu.children if "ctx-menu-item" in child.className]
    assert [item.id for item in items] == [sort.item_id(v) for v, _ in sort.options]
    assert [_text(item) for item in items] == [label for _, label in sort.options]

    _find(layout, sort.input_id)
    store = _find(layout, sort.store_id)
    assert store.storage_type == "local"
    assert store.data == sort.default
    assert _find(layout, sort.tooltip_id).children == f"Sort: {sort.label(sort.default)}"


def test_sort_options_match_the_list_callbacks():
    assert [v for v, _ in GOALS_SORT.options] == ["priority", "time-desc", "manual", "alpha-asc"]
    assert [v for v, _ in EVENTS_SORT.options] == ["manual", "az", "type", "impact"]


def test_hide_triggered_switch_is_gone(layout):
    with pytest.raises(AssertionError):
        _find(layout, "events-hide-triggered-toggle")
    assert _find(layout, "events-show-triggered-store").data is False


def _render_events_list():
    from event_callbacks import register_event_callbacks
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_event_callbacks(app)
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None and fn.__name__ == "render_events_list":
            return fn
    raise LookupError("render_events_list")


@pytest.fixture
def render():
    em = EventManager()
    em.add_event(Event(name="Alpha", description="plant the garden"))
    em.add_event(Event(name="Beta", status="Triggered"))
    em.add_event(Event(name="Gamma", description="garden shed", status="Triggered"))
    fn = _render_events_list()

    def _call(search="", shown=False, sort="az"):
        return fn(None, None, None, None, search, shown, sort, None)
    return _call


def _card_names(children):
    return [node.id["index"] for node in _walk(children)
            if isinstance(getattr(node, "id", None), dict)
            and node.id.get("type") == "event-card"]


def test_triggered_events_hide_behind_a_counted_divider(render):
    children = render()
    assert _card_names(children) == ["Alpha"]
    assert "2 triggered events hidden · Show" in _text(children)


def test_showing_triggered_events_lists_them_under_the_divider(render):
    children = render(shown=True)
    assert _card_names(children) == ["Alpha", "Beta", "Gamma"]
    assert "2 triggered events · Hide" in _text(children)
    # Active and triggered cards sort in separate groups.
    groups = [node for node in children if "events-sort-group" in (node.className or "")]
    assert [_card_names(group) for group in groups] == [["Alpha"], ["Beta", "Gamma"]]


def test_hidden_count_only_counts_search_matches(render):
    children = render(search="garden")
    assert _card_names(children) == ["Alpha"]
    assert "1 triggered event hidden · Show" in _text(children)


def test_divider_stays_when_search_matches_only_triggered_events(render):
    children = render(search="shed")
    assert _card_names(children) == []
    text = _text(children)
    assert "No matching events." in text
    assert "1 triggered event hidden · Show" in text


def test_no_divider_without_triggered_events(render):
    children = render(search="plant")
    assert _card_names(children) == ["Alpha"]
    assert not _has_class(children, "events-triggered-divider")
