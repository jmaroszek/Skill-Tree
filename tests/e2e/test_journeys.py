"""What a new user does in their first hour, in a real browser (P6.5)."""
import json

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
PlaywrightTimeout = sync_api.TimeoutError


def _welcome(page, choice="#btn-welcome-suggested"):
    page.wait_for_selector("#welcome-modal", state="visible", timeout=15000)
    page.click(choice)
    page.wait_for_selector("#welcome-modal", state="hidden", timeout=15000)


def _dropdown_pick(page, dropdown, option):
    """Choose an option in a Dash dropdown by typing it."""
    page.click(dropdown)
    page.keyboard.type(option)
    page.locator("[role=option]", has_text=option).first.click()
    page.keyboard.press("Escape")
    _idle(page)


_EDITOR_LEFT = "document.querySelector('#sidebar-editor-container').getBoundingClientRect().left"


def _idle(page):
    """Wait for Dash to finish updating: a component it is still writing
    carries data-dash-is-loading. Typing into a field whose reset is still in
    flight loses the typing."""
    page.wait_for_timeout(150)
    page.wait_for_function(
        "!document.querySelector('[data-dash-is-loading=\"true\"]')", timeout=20000)


def _open_editor(page):
    """The editor slides in from the left; it's open once it has arrived."""
    if page.evaluate(_EDITOR_LEFT) < -1:
        page.click("#btn-add")
    page.wait_for_function(f"{_EDITOR_LEFT} >= -1", timeout=10000)
    _idle(page)


def _new_node(page, name, node_type="Learn", needs_hard=(), expected_hours="2"):
    """Create a node through the editor, the way a person would. Names are in
    Title Case, which the default name formatting leaves as they are."""
    _open_editor(page)
    page.click("#btn-editor-new")
    _idle(page)
    page.fill("#node-name", name)
    page.select_option("#node-type", node_type)
    page.click("#node-context-picker-trigger")
    page.click("button.context-picker-menu-row[data-context='Mind']")
    page.click("[role=option]:has-text('No subcontext')")
    if page.is_visible("#node-time-m"):
        page.fill("#node-time-m", expected_hours)
    for prerequisite in needs_hard:
        _dropdown_pick(page, "#edge-needs-hard", prerequisite)
    page.click("#btn-save")
    page.wait_for_function(
        "document.querySelector('#save-output').innerText.includes('Added node')",
        timeout=15000)


def _open_in_editor(page, name):
    _open_editor(page)
    _dropdown_pick(page, "#search-node", name)
    page.wait_for_function(
        f"document.querySelector('#node-name').value === {json.dumps(name)}", timeout=15000)


def _reflect(page, actual_hours=None):
    """Marking something Done asks how long it really took (Reflection).
    Answer it, or skip it."""
    try:
        page.wait_for_selector("#btn-time-calibration-skip", state="visible", timeout=5000)
    except PlaywrightTimeout:
        return False
    if actual_hours is None:
        page.click("#btn-time-calibration-skip")
    else:
        # The unit starts at the estimate's; the database keeps hours.
        page.select_option("#time-calibration-unit", "hours")
        page.fill("#time-calibration-point", str(actual_hours))
        page.click("#btn-time-calibration-submit")
    page.wait_for_selector("#btn-time-calibration-skip", state="hidden", timeout=15000)
    return True


def _set_done(page, name, done=True, actual_hours=None):
    _open_in_editor(page, name)
    switch = page.locator("#node-status-done input")
    if switch.is_checked() != done:
        switch.click()
    page.click("#btn-save")
    if done:
        _reflect(page, actual_hours)


def test_a_first_launch_is_welcomed_and_guided(page):
    _welcome(page)
    page.wait_for_selector("#getting-started .card", timeout=15000)
    assert "Your graph is empty" in page.inner_text("#suggestions-table")
    page.reload()
    page.wait_for_selector("#startup-cover.is-lifted", state="attached", timeout=60000)
    page.wait_for_timeout(1000)
    assert not page.is_visible("#welcome-modal")
    assert page.console_errors == []


def test_a_small_graph_turns_into_suggestions(page, server):
    _welcome(page)
    _new_node(page, "Sleep Science", "Learn")
    _new_node(page, "Sleep Hygiene", "Action", needs_hard=["Sleep Science"])
    _new_node(page, "Sleep", "Goal", needs_hard=["Sleep Hygiene"])

    edges = set(server.query("SELECT source, target, type FROM Edges"))
    assert ("Sleep Science", "Sleep Hygiene", "Needs_Hard") in edges
    assert ("Sleep Hygiene", "Sleep", "Needs_Hard") in edges
    statuses = dict(server.query("SELECT name, status FROM Nodes"))
    assert statuses["Sleep Hygiene"] == "Blocked"

    page.keyboard.press("Escape")
    page.click("a.nav-link:has-text('Home')")
    page.wait_for_function(
        "document.querySelector('#suggestions-table').innerText.includes('Sleep Science')",
        timeout=20000)
    assert page.console_errors == []


def test_done_unblocks_and_undoing_it_asks_first(page, server):
    _welcome(page)
    _new_node(page, "Basics", "Learn")
    _new_node(page, "Advanced", "Learn", needs_hard=["Basics"])

    _set_done(page, "Basics", actual_hours=3)
    page.wait_for_timeout(1500)
    assert dict(server.query("SELECT name, status FROM Nodes"))["Advanced"] == "Open"
    # The reflection was kept.
    assert server.query("SELECT actual_time_point FROM Nodes WHERE name = 'Basics'") == [(3.0,)]

    _set_done(page, "Advanced")
    page.wait_for_timeout(1500)
    # Un-marking Basics would re-block the Done node after it: the app asks.
    # Cancel keeps it Done, and the editor's switch goes back on.
    _open_in_editor(page, "Basics")
    switch = page.locator("#node-status-done input")
    switch.click()
    page.click("#btn-save")
    page.wait_for_selector("#modal-undo-done-confirm", state="visible", timeout=15000)
    page.click("#btn-undo-done-cancel")
    page.wait_for_selector("#modal-undo-done-confirm", state="hidden", timeout=15000)
    _idle(page)
    assert switch.is_checked()
    assert dict(server.query("SELECT name, status FROM Nodes"))["Basics"] == "Done"

    # Un-mark, this time for real.
    switch.click()
    page.click("#btn-save")
    page.wait_for_selector("#modal-undo-done-confirm", state="visible", timeout=15000)
    page.click("#btn-undo-done-confirm")
    page.wait_for_timeout(2000)
    statuses = dict(server.query("SELECT name, status FROM Nodes"))
    assert statuses == {"Basics": "Open", "Advanced": "Blocked"}
    assert page.console_errors == []


def test_backup_export_and_restore(page, server):
    _welcome(page)
    _new_node(page, "Keep Me", "Learn")
    page.click("#btn-settings-toggle")
    page.click("a.nav-link:has-text('Data')")
    page.click("#btn-backup-now")
    page.wait_for_function(
        "document.querySelector('#data-status').innerText.includes('Backed up')", timeout=15000)
    with page.expect_download(timeout=15000) as download:
        page.click("#btn-export-json")
    exported = json.loads(open(download.value.path(), encoding="utf-8").read())
    assert any(row["name"] == "Keep Me" for row in exported["tables"]["Nodes"])

    server.query("DELETE FROM Nodes WHERE name = 'Keep Me'")  # losing it by accident
    page.click("#restore-backup-select")
    page.locator("[role=option]", has_text="made by hand").first.click()
    page.click("#btn-restore-backup")
    page.click("#btn-restore-confirm")
    page.wait_for_selector("#startup-cover.is-lifted", state="attached", timeout=60000)
    page.wait_for_timeout(1500)
    assert server.query("SELECT name FROM Nodes") == [("Keep Me",)]


def test_a_restart_keeps_everything(open_app, server):
    first = open_app(server)
    _welcome(first)
    _new_node(first, "Persistent", "Learn")
    first.context.close()

    server.stop()
    server.start()
    again = open_app(server)
    again.wait_for_timeout(1000)
    assert not again.is_visible("#welcome-modal")
    again.wait_for_function(
        "document.querySelector('#suggestions-table').innerText.includes('Persistent')",
        timeout=20000)


def test_nothing_leaves_this_computer(page):
    _welcome(page)
    _new_node(page, "Offline", "Learn")
    for tab in ("Nodes", "Details", "Events", "Analyze", "Home"):
        page.click(f"a.nav-link:has-text('{tab}')")
        page.wait_for_timeout(1200)
    assert page.hosts == {"127.0.0.1"}
