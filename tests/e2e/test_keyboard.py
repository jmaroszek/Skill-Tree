"""Keyboard workflows against a real sandbox server and Chromium."""
import json

import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _welcome, _new_node, _idle, _close_editor  # noqa: E402


def _tab_to(page, selector, limit=160):
    """Find a visible control through the actual sequential focus order."""
    trail = []
    for _ in range(limit):
        if page.evaluate("s => document.activeElement.matches(s)", selector):
            return
        trail.append(page.evaluate("document.activeElement.id || document.activeElement.className || document.activeElement.tagName"))
        page.keyboard.press("Tab")
    raise AssertionError(f"{selector} never reached through Tab: {trail[-20:]}; errors={page.console_errors}")


def _card_to(page, selector):
    """Enter a card group through Tab, then use its roving arrow order."""
    kind = selector.split("[", 1)[0].split(" ", 1)[0]
    _tab_to(page, kind)
    count = page.locator(kind).count()
    for _ in range(count):
        if page.evaluate("s => document.activeElement.matches(s)", selector):
            return
        page.keyboard.press("ArrowDown")
    raise AssertionError(f"{selector} never reached through card arrows")


def _seed(page):
    _welcome(page)
    _new_node(page, "Alpha", "Learn")
    _new_node(page, "Beta", "Learn")
    _new_node(page, "Goal", "Goal", needs_hard=["Alpha", "Beta"])
    _close_editor(page)
    _idle(page)


def _menu_action(page, item_id):
    page.keyboard.press("Shift+F10")
    page.wait_for_function("document.activeElement.classList.contains('ctx-menu-item')")
    for _ in range(20):
        if page.evaluate("document.activeElement.id") == item_id:
            page.keyboard.press("Enter")
            _idle(page)
            return
        page.keyboard.press("ArrowDown")
    raise AssertionError(f"{item_id} never reached through menu arrows")


def test_keyboard_home_actions_sidebar_and_save(page, server):
    _seed(page)
    assert page.locator("#sidebar-editor-container").evaluate("el => el.inert")
    row = '.suggestion-bar-row[data-node-menu="Alpha"]'
    _card_to(page, row)
    assert page.locator(row).evaluate("el => getComputedStyle(el).outlineStyle") == "solid"
    page.keyboard.press("Enter")
    page.keyboard.press("Shift+F10")
    page.wait_for_function("document.activeElement.id === 'ctx-menu-edit'")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.id") == "ctx-menu-toggle-now"
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelector('.now-card[data-node-menu=Alpha]') !== null")
    assert server.query("SELECT now FROM Nodes WHERE name='Alpha'")[0][0] > 0
    _idle(page)
    _card_to(page, '.now-card[data-node-menu="Alpha"]')
    page.keyboard.press("Shift+F10")
    page.keyboard.press("Enter")
    page.wait_for_function("!document.getElementById('sidebar-editor-container').inert")
    _idle(page)
    _tab_to(page, "#node-desc")
    page.keyboard.press("Control+A")
    page.keyboard.type("Edited using the keyboard")
    page.keyboard.press("Control+s")
    page.wait_for_function("document.querySelector('#save-output').innerText.includes('Updated node')")
    assert server.query("SELECT description FROM Nodes WHERE name='Alpha'") == [("Edited using the keyboard",)]
    _idle(page)
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('sidebar-editor-container').inert", timeout=10000)
    assert not page.locator("#sidebar-editor-container").evaluate("el => el.contains(document.activeElement)")
    assert page.console_errors == []


def test_keyboard_graph_selection_menu_and_scoped_delete(page):
    _seed(page)
    _tab_to(page, "a.nav-link", limit=160)
    # Navigate through the actual tab links to Nodes.
    for _ in range(20):
        if page.evaluate("document.activeElement.textContent.trim()") == "Nodes":
            break
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    page.wait_for_function("window.SkillTree.getCy(document.getElementById('cytoscape-graph'))?.nodes().length === 3")
    _idle(page)
    _tab_to(page, "#cytoscape-graph")
    page.keyboard.press("Home")
    assert "Alpha" in page.inner_text(".keyboard-feedback")
    page.keyboard.press("Enter")
    page.wait_for_function("window.SkillTree.getCy(document.getElementById('cytoscape-graph')).$('node:selected').map(n=>n.id()).join() === 'Alpha'")
    page.keyboard.press("PageDown")
    page.keyboard.press("Shift+Enter")
    assert page.evaluate("window.SkillTree.getCy(document.getElementById('cytoscape-graph')).$('node:selected').length") == 2
    page.keyboard.press("Shift+F10")
    page.wait_for_function("document.activeElement.id === 'ctx-menu-edit'")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == "cytoscape-graph"
    # Delete must not act on the retained graph selection from a toolbar control.
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Delete")
    _idle(page)
    assert not page.is_visible("#modal-group-delete-confirm")
    _tab_to(page, "#cytoscape-graph")
    page.keyboard.press("Delete")
    page.wait_for_selector("#modal-group-delete-confirm", state="visible")
    page.keyboard.press("Escape")
    page.wait_for_selector("#modal-group-delete-confirm", state="hidden")
    assert page.console_errors == []


def test_keyboard_goal_submenu_and_panel_resize(page, server):
    _seed(page)
    assert server.query("SELECT source FROM Edges WHERE target='Goal' AND type='Needs_Hard' ORDER BY source") == [("Alpha",), ("Beta",)]
    _tab_to(page, "#btn-goals-toggle")
    page.keyboard.press("Enter")
    page.wait_for_function("!document.getElementById('details-goal-sidebar').inert")
    _idle(page)
    _card_to(page, '.goal-card[data-goal-name="Goal"]')
    page.keyboard.press("Shift+F10")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.id") == "ctx-menu-priority"
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.id") == "ctx-menu-priority-1"
    page.keyboard.press("Enter")
    _idle(page)
    assert json.loads(server.query("SELECT value FROM Settings WHERE key='PRIORITY_GOALS'")[0][0]) == ["Goal"]
    _card_to(page, '.goal-card[data-goal-name="Goal"]')
    page.keyboard.press("Enter")
    page.wait_for_selector("#details-v-drag-upper", state="visible")
    page.wait_for_function("document.getElementById('details-node-name').textContent === 'Goal'")
    page.wait_for_selector(".details-subtask-name-link", state="visible")
    _idle(page)
    handles = page.locator('.split-handle:visible')
    assert handles.count() > 0
    handle_id = handles.first.get_attribute("id")
    _tab_to(page, f"[id={json.dumps(handle_id)}]")
    before = handles.first.evaluate("el => el.previousElementSibling.getBoundingClientRect().width")
    page.keyboard.press("ArrowRight")
    after = handles.first.evaluate("el => el.previousElementSibling.getBoundingClientRect().width")
    assert after > before
    _tab_to(page, ".details-subtask-name-link")
    name = page.evaluate("document.activeElement.textContent")
    page.keyboard.press("Enter")
    page.wait_for_function("name => document.getElementById('details-node-name').textContent === name", arg=name)
    assert page.console_errors == []


def test_keyboard_now_reordering_persists_and_keeps_focus(page, server):
    _seed(page)
    for name in ("Alpha", "Beta"):
        _card_to(page, f'.suggestion-bar-row[data-node-menu="{name}"]')
        _menu_action(page, "ctx-menu-toggle-now")
    before = server.query("SELECT name FROM Nodes WHERE now > 0 ORDER BY now")
    last = before[-1][0]
    _card_to(page, f'.now-card[data-node-menu="{last}"]')
    page.keyboard.press("Alt+ArrowLeft")
    _idle(page)
    assert server.query("SELECT name FROM Nodes WHERE now > 0 ORDER BY now") == list(reversed(before))
    assert page.evaluate("document.activeElement.getAttribute('data-node-menu')") == last
    assert page.console_errors == []


def test_keyboard_settings_context_reorder_and_save(page, server):
    _welcome(page)
    _tab_to(page, "#btn-settings-toggle")
    page.keyboard.press("Enter")
    page.wait_for_selector("#settings-modal", state="visible")
    _idle(page)
    _tab_to(page, "#settings-modal .nav-link")
    for _ in range(12):
        if page.evaluate("document.activeElement.textContent.trim()") == "Contexts":
            break
        page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Contexts"
    page.keyboard.press("Enter")
    _idle(page)
    names = page.locator('.ctx-row-name').evaluate_all("els => els.map(el => el.value)")
    assert len(names) > 1
    _tab_to(page, '.ctx-drag-handle:not(.ctx-drag-disabled)')
    page.keyboard.press("Alt+ArrowDown")
    _idle(page)
    expected = [names[1], names[0], *names[2:]]
    assert page.locator('.ctx-row-name').evaluate_all("els => els.map(el => el.value)") == expected
    assert page.evaluate("document.activeElement.matches('.ctx-drag-handle')")
    _tab_to(page, "#btn-settings-save")
    saves = []
    def record_save(request):
        if not request.url.endswith("/_dash-update-component"):
            return
        body = request.post_data_json
        if "settings-save-status.children" in body.get("output", "") and "btn-settings-save.n_clicks" in body.get("changedPropIds", []):
            saves.append(body)
    page.on("request", record_save)
    page.keyboard.press("Control+s")
    _idle(page)
    # The save shortcut must issue exactly one save request.
    assert len(saves) == 1
    assert json.loads(server.query("SELECT value FROM Settings WHERE key='CONTEXTS'")[0][0]) == expected
    page.keyboard.press("Escape")
    page.wait_for_selector("#settings-modal", state="hidden")
    assert page.console_errors == []


def test_keyboard_create_node_and_preserve_draft_guard(page, server):
    _welcome(page)
    _tab_to(page, "#btn-add")
    page.keyboard.press("Enter")
    page.wait_for_function("!document.getElementById('sidebar-editor-container').inert")
    _idle(page)
    _tab_to(page, "#node-name")
    page.keyboard.type("Keyboard Node")
    _tab_to(page, "#node-type")
    page.keyboard.press("l")
    assert page.input_value("#node-type") == "Learn"
    _tab_to(page, "#node-context-picker-trigger")
    page.keyboard.press("Enter")
    page.keyboard.type("Mind")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowUp")
    page.keyboard.press("Enter")
    _tab_to(page, "#node-time-m")
    page.keyboard.press("Control+A")
    page.keyboard.type("2")
    _tab_to(page, "#btn-save")
    page.keyboard.press("Space")
    _idle(page)
    assert "Added node" in page.inner_text("#save-output"), page.inner_text("#save-output")
    page.wait_for_function("document.querySelector('#save-output').innerText.includes('Added node')")
    _idle(page)
    assert server.query("SELECT name, context FROM Nodes") == [("Keyboard Node", "Mind")]
    _tab_to(page, "#btn-ratings-info")
    page.wait_for_selector('.tooltip.show', state="visible")
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.id") == "btn-ratings-close"
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == "btn-ratings-info"
    _tab_to(page, "#node-desc")
    page.keyboard.type("Unsaved draft")
    page.keyboard.press("Escape")
    page.wait_for_selector("#modal-unsaved-changes", state="visible")
    _tab_to(page, "#btn-unsaved-discard")
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('sidebar-editor-container').inert")
    page.wait_for_function("document.activeElement.id === 'btn-add'")
    assert server.query("SELECT description FROM Nodes") == [("",)]
    assert page.console_errors == []


def test_keyboard_events_create_select_menu_and_reorder(page, server):
    _welcome(page)
    for name in ("First Event", "Second Event"):
        _tab_to(page, "#btn-events-sidebar-toggle")
        page.keyboard.press("Enter")
        page.wait_for_function("!document.getElementById('events-sidebar-container').inert")
        _tab_to(page, "#btn-new-event")
        page.keyboard.press("Enter")
        _idle(page)
        _tab_to(page, "#event-name")
        page.keyboard.type(name)
        _tab_to(page, "#btn-event-save")
        page.keyboard.press("Enter")
        _idle(page)
        assert server.query("SELECT name FROM Events WHERE name=?", name) == [(name,)]
    _tab_to(page, "#btn-events-sidebar-toggle")
    page.keyboard.press("Enter")
    _tab_to(page, "#events-sort-button")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.id === 'events-sort-menu-manual'")
    page.keyboard.press("Enter")
    _idle(page)
    cards = page.locator('.event-card').evaluate_all("els => els.map(el => el.dataset.eventName)")
    last = cards[-1]
    _card_to(page, f'.event-card[data-event-name="{last}"]')
    _tab_to(page, f'.event-card[data-event-name="{last}"] .event-drag-handle')
    page.keyboard.press("Alt+ArrowUp")
    _idle(page)
    assert json.loads(server.query("SELECT value FROM Settings WHERE key='EVENT_ORDER'")[0][0]) == list(reversed(cards))
    page.wait_for_function("""name => document.activeElement.matches('.event-drag-handle') &&
        document.activeElement.closest('.event-card').getAttribute('data-event-name') === name""", arg=last)
    _card_to(page, f'.event-card[data-event-name="{last}"]')
    page.keyboard.press("Space")
    _idle(page)
    assert page.input_value("#event-name") == last
    assert page.evaluate("document.activeElement.id") == "event-name"
    _tab_to(page, "#btn-events-sidebar-toggle")
    page.keyboard.press("Enter")
    _card_to(page, f'.event-card[data-event-name="{last}"]')
    page.keyboard.press("Shift+F10")
    page.wait_for_function("document.activeElement.id === 'event-ctx-edit'")
    page.keyboard.press("End")
    assert page.evaluate("document.activeElement.id") == "event-ctx-delete"
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.dataset.eventName") == last
    assert page.console_errors == []
