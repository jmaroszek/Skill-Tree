"""What a new user does in their first hour, in a real browser (P6.5)."""
import json
import re

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
PlaywrightTimeout = sync_api.TimeoutError


def _welcome(page, choice="#btn-welcome-suggested"):
    page.wait_for_selector("#welcome-modal", state="visible", timeout=15000)
    page.click(choice)
    page.wait_for_selector("#welcome-modal", state="hidden", timeout=15000)


def _dropdown_pick(page, dropdown, option):
    """Choose an option in a Dash dropdown: open it, search in its own
    popover, and click the match there. Other dropdowns' options are in the
    page too, and focus stays on the dropdown's button, where a multi-select
    takes keys of its own, so nothing here goes by keyboard focus. A callback
    that resends a dropdown's options re-renders it and closes an open menu;
    a pick that loses its menu that way starts again."""
    exactly = re.compile(rf"^\s*{re.escape(option)}\s*$")
    for _attempt in range(3):
        _idle(page)
        page.click(dropdown)
        try:
            page.wait_for_selector(f"{dropdown}[aria-expanded=true]", timeout=5000)
            popover = page.locator(f"[id={json.dumps(page.get_attribute(dropdown, 'aria-controls'))}]")
            popover.locator("input.dash-dropdown-search").fill(option, timeout=5000)
            popover.locator("[role=option]", has_text=exactly).first.click(timeout=5000)
        except PlaywrightTimeout:
            page.keyboard.press("Escape")
            continue
        page.keyboard.press("Escape")
        _idle(page)
        return
    raise AssertionError(f"{option!r} never became choosable in {dropdown}")


_EDITOR_LEFT = "document.querySelector('#sidebar-editor-container').getBoundingClientRect().left"


_QUIET = """quietMs => {
    const now = performance.now();
    if (document.querySelector('[data-dash-is-loading="true"]')
            || window.__skillTreeQuietSince === undefined) {
        window.__skillTreeQuietSince = now;
        return false;
    }
    return now - window.__skillTreeQuietSince >= quietMs;
}"""


def _idle(page, quiet_ms=400):
    """Wait for Dash to finish updating: a component it is still writing
    carries data-dash-is-loading. A chained callback starts only once the one
    before it returns, so one quiet instant isn't enough; this waits for a
    quiet stretch. Typing into a field whose reset is still coming loses the
    typing."""
    page.evaluate("window.__skillTreeQuietSince = undefined")
    page.wait_for_function(_QUIET, arg=quiet_ms, polling=50, timeout=30000)


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


def _close_editor(page):
    page.click("#btn-close-editor")
    page.wait_for_function(f"{_EDITOR_LEFT} < -1", timeout=10000)


_NODE_POSITION = """name => {
    const el = document.getElementById('cytoscape-graph');
    const cy = window.SkillTree.getCy(el);
    const node = cy && cy.getElementById(name);
    if (!node || !node.length || !node.visible()) return null;
    const p = node.renderedPosition(), r = el.getBoundingClientRect();
    return {x: r.left + p.x, y: r.top + p.y};
}"""


def _node_menu(page, name, item):
    """Right-click a node on the Nodes canvas and choose from its menu."""
    page.click("a.nav-link:has-text('Nodes')")
    page.wait_for_function(_NODE_POSITION, arg=name, timeout=20000)
    _idle(page)
    at = page.evaluate(_NODE_POSITION, name)
    page.mouse.click(at["x"], at["y"], button="right")
    page.click(f"#{item}")


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
    page.locator("[role=option]", has_text="(manual)").first.click()
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


def test_rename_and_delete_carry_the_relationships(page, server):
    _welcome(page)
    _new_node(page, "Draft", "Learn")
    _new_node(page, "Publish", "Action", needs_hard=["Draft"])

    _open_in_editor(page, "Draft")
    page.fill("#node-name", "First Draft")
    page.click("#btn-save")
    page.wait_for_function(
        "document.querySelector('#save-output').innerText.includes(\"Updated node 'First Draft'\")",
        timeout=15000)
    assert server.query("SELECT source, target, type FROM Edges") == [
        ("First Draft", "Publish", "Needs_Hard")]

    _open_in_editor(page, "Publish")
    page.click("#btn-delete")
    page.click("#btn-node-delete-confirm")
    page.wait_for_function(
        "document.querySelector('#save-output').innerText.includes('Deleted')", timeout=15000)
    assert server.query("SELECT name FROM Nodes") == [("First Draft",)]
    assert server.query("SELECT COUNT(*) FROM Edges") == [(0,)]
    assert page.console_errors == []


def test_now_holds_what_is_in_progress_until_it_is_done(page, server):
    _welcome(page)
    _new_node(page, "Stretching", "Action")
    page.locator("#node-now input").click()
    page.wait_for_function(
        "document.querySelector('#now-cards-container') !== null", timeout=15000)
    assert server.query("SELECT now > 0 FROM Nodes WHERE name = 'Stretching'") == [(1,)]
    assert "Stretching" in page.inner_text("#now-cards-container")

    _set_done(page, "Stretching")
    page.wait_for_timeout(1500)
    assert server.query("SELECT now, status FROM Nodes") == [(0, "Done")]
    assert page.console_errors == []


def test_a_sleeping_node_wakes_with_its_event(page, server):
    _welcome(page)
    _new_node(page, "Pack Bags", "Action")
    page.locator("#node-dormant input").click()
    page.select_option("#node-dormant-event", "__new__")
    page.fill("#node-dormant-event-name", "Trip Booked")
    page.click("#btn-save")
    page.wait_for_function(
        "document.querySelector('#save-output').innerText.includes('Updated node')",
        timeout=15000)
    assert server.query("SELECT dormant FROM Nodes") == [(1,)]
    assert server.query("SELECT event_name, node_name FROM EventNodes") == [
        ("Trip Booked", "Pack Bags")]

    page.keyboard.press("Escape")
    page.click("a.nav-link:has-text('Events')")
    page.click("[id*='\"type\":\"event-card\"']")
    page.click("#btn-trigger-event")
    page.click("#btn-trigger-confirm")
    page.wait_for_timeout(2000)
    assert server.query("SELECT dormant FROM Nodes") == [(0,)]
    assert page.console_errors == []


def test_an_export_fills_a_new_install(page, server, start_server, open_app, tmp_path):
    """Moving to another computer: export here, import into a fresh install."""
    _welcome(page)
    _new_node(page, "Carry Over", "Learn")
    _new_node(page, "Next Step", "Action", needs_hard=["Carry Over"])
    page.keyboard.press("Escape")
    page.click("#btn-settings-toggle")
    page.click("a.nav-link:has-text('Data')")
    with page.expect_download(timeout=15000) as download:
        page.click("#btn-export-json")
    exported = tmp_path / "moving.json"
    download.value.save_as(exported)

    fresh = start_server("elsewhere")
    other = open_app(fresh)
    _welcome(other, "#btn-welcome-import")
    other.set_input_files("#upload-import input[type=file]", str(exported))
    other.wait_for_function(
        "document.querySelector('#suggestions-table') &&"
        " document.querySelector('#suggestions-table').innerText.includes('Carry Over')",
        timeout=60000)
    assert set(fresh.query("SELECT name, status FROM Nodes")) == {
        ("Carry Over", "Open"), ("Next Step", "Blocked")}
    assert fresh.query("SELECT source, target, type FROM Edges") == [
        ("Carry Over", "Next Step", "Needs_Hard")]
    assert not other.is_visible("#welcome-modal")
    assert other.console_errors == []


def test_the_editor_follows_done_from_the_node_menu(page, server):
    """The editor keeps the last node it held. Marked Done from its menu in
    the meantime, it shows Done there too, so saving an edit keeps it Done."""
    _welcome(page)
    _new_node(page, "Warm Up", "Action")
    _close_editor(page)

    _node_menu(page, "Warm Up", "ctx-menu-toggle-done")
    _reflect(page)
    page.wait_for_timeout(1000)
    assert server.query("SELECT status FROM Nodes") == [("Done",)]

    _open_editor(page)
    assert page.input_value("#node-name") == "Warm Up"
    assert page.locator("#node-status-done input").is_checked()
    page.fill("#node-desc", "every morning")
    page.click("#btn-save")
    page.wait_for_function(
        "document.querySelector('#save-output').innerText.includes('Updated node')",
        timeout=15000)
    assert server.query("SELECT status, description FROM Nodes") == [
        ("Done", "every morning")]
    assert page.console_errors == []


_INPUT_HOLDING = """([kind, value]) => {
    const rows = document.querySelectorAll(`[id*='"type":"${kind}"']`);
    const row = [...rows].find(el => el.value === value);
    return row ? row.id : null;
}"""


def test_renaming_a_context_in_settings_moves_its_nodes(page, server):
    _welcome(page)
    _new_node(page, "Meditation", "Action")
    _close_editor(page)
    page.click("#btn-settings-toggle")
    page.click("a.nav-link:has-text('Contexts')")
    page.wait_for_function(_INPUT_HOLDING, arg=["ctx-row-name", "Mind"], timeout=15000)
    row = page.evaluate(_INPUT_HOLDING, ["ctx-row-name", "Mind"])
    page.fill(f"[id={json.dumps(row)}]", "Intellect")
    _idle(page)
    page.click("#btn-settings-save")
    deadline = 20
    while deadline and server.query("SELECT context FROM Nodes") != [("Intellect",)]:
        page.wait_for_timeout(500)
        deadline -= 0.5
    assert server.query("SELECT context FROM Nodes") == [("Intellect",)]
    contexts = json.loads(server.query(
        "SELECT value FROM Settings WHERE key = 'CONTEXTS'")[0][0])
    assert "Intellect" in contexts and "Mind" not in contexts
    assert page.console_errors == []
