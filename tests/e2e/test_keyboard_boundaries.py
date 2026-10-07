"""Keyboard acceptance checks for containment, visibility and shortcut scope."""
import pytest

pytest.importorskip("playwright.sync_api")
from test_journeys import _welcome, _idle, _open_in_editor  # noqa: E402
from test_keyboard import _tab_to, _seed  # noqa: E402
from test_journeys import _new_node, _close_editor  # noqa: E402


def _activate_tab(page, name):
    _tab_to(page, "#main-tabs .nav-link")
    for _ in range(5):
        if page.evaluate("document.activeElement.textContent.trim()") == name:
            page.keyboard.press("Enter")
            _idle(page)
            return
        page.keyboard.press("ArrowRight")
    raise AssertionError(f"Tab {name} not found")


@pytest.mark.parametrize("toggle,panel,entry", [
    ("btn-add", "sidebar-editor-container", "search-node"),
    ("btn-goals-toggle", "details-goal-sidebar", "details-goal-search"),
    ("btn-events-sidebar-toggle", "events-sidebar-container", "events-search-input"),
    ("btn-filters-toggle", "sidebar-filters-container", "filter-context-picker-trigger"),
])
def test_sidebar_entry_wrap_and_escape(page, toggle, panel, entry):
    _welcome(page)
    _tab_to(page, f"#{toggle}")
    page.keyboard.press("Enter")
    page.wait_for_function("id => !document.getElementById(id).inert", arg=panel)
    _idle(page)
    # Node search may immediately open its native dropdown on Enter; Escape
    # dismisses just that dropdown before checking the panel boundary.
    if page.get_attribute(f"#{entry}", "aria-expanded") == "true":
        page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == entry
    controls = page.locator(f"#{panel}").evaluate("""root => Array.from(root.querySelectorAll(
        'button, a[href], input:not([type=hidden]), select, textarea, [tabindex]'
    )).filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length
        && !el.closest('[inert]')).map(el => el.id)""")
    assert controls[0] and controls[-1]
    _tab_to(page, f"#{controls[0]}")
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.activeElement.id") == controls[-1]
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == controls[0]
    for _ in range(len(controls) + 2):
        page.keyboard.press("Tab")
        assert page.locator(f"#{panel}").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    page.wait_for_function("id => document.getElementById(id).inert", arg=panel)
    assert page.evaluate("document.activeElement.id") == toggle
    assert page.console_errors == []


def test_editor_focus_scrolls_above_sticky_footer_and_field_help(page):
    _welcome(page)
    page.set_viewport_size({"width": 1100, "height": 650})
    _tab_to(page, "#btn-add")
    page.keyboard.press("Enter")
    _idle(page)
    _tab_to(page, "#node-type")
    assert "node-type-label-hint" in page.get_attribute("#node-type", "aria-describedby")
    page.wait_for_timeout(600)
    assert page.locator(".tooltip.show").count() == 0
    _tab_to(page, "#edge-helps")
    assert page.locator("#sidebar-editor-container").evaluate("el => el.scrollTop") > 0
    assert page.evaluate("""() => {
        const field = document.activeElement.getBoundingClientRect();
        const panel = document.getElementById('sidebar-editor-container').getBoundingClientRect();
        const footer = document.getElementById('node-editor-actions').getBoundingClientRect();
        return field.top >= panel.top && field.bottom <= footer.top;
    }""")
    assert "node-helps-label-hint" in page.get_attribute("#edge-helps", "aria-describedby")
    assert page.console_errors == []


def test_mouse_opened_panels_accept_keyboard_entry_and_escape(page):
    _welcome(page)
    page.click("#btn-add")
    _idle(page)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "search-node"
    _tab_to(page, "#btn-ratings-info")
    page.click("#btn-ratings-info")
    page.wait_for_selector("#ratings-popup", state="visible")
    page.keyboard.press("Escape")
    page.wait_for_selector("#ratings-popup", state="hidden")
    assert page.evaluate("document.activeElement.id") == "btn-ratings-info"
    assert not page.locator("#sidebar-editor-container").evaluate("el => el.inert")
    page.click("#btn-ratings-info")
    page.wait_for_selector("#ratings-popup", state="visible")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "btn-ratings-close"
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.wait_for_function("document.activeElement.id === 'btn-add'")
    assert page.console_errors == []


def test_ratings_keeps_focus_and_escape_returns_to_editor(page):
    _welcome(page)
    _tab_to(page, "#btn-add")
    page.keyboard.press("Enter")
    _idle(page)
    _tab_to(page, "#btn-ratings-info")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.id === 'btn-ratings-close'")
    for key in ("Tab", "Tab", "Shift+Tab", "Shift+Tab"):
        page.keyboard.press(key)
        assert page.locator("#ratings-popup").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == "btn-ratings-info"
    assert not page.locator("#sidebar-editor-container").evaluate("el => el.inert")
    page.keyboard.press("Tab")
    assert page.locator("#sidebar-editor-container").evaluate("el => el.contains(document.activeElement)")
    assert page.console_errors == []


def test_tab_leaves_open_dropdown_and_advances_one_form_control(page):
    _seed(page)
    _tab_to(page, "#btn-add")
    page.keyboard.press("Enter")
    _idle(page)
    _tab_to(page, "#search-node")
    if page.get_attribute("#search-node", "aria-expanded") != "true":
        page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.matches('.dash-dropdown-search')")
    page.keyboard.press("Tab")
    page.wait_for_function("document.activeElement.id === 'btn-alias-add'")
    assert page.get_attribute("#search-node", "aria-expanded") == "false"
    assert page.console_errors == []


def test_manual_tab_activation_and_closed_details_filters(page):
    _welcome(page)
    _tab_to(page, "#main-tabs .nav-link")
    assert page.locator("#main-tabs .nav-link[tabindex='0']").count() == 1
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Details"
    assert page.locator("#main-tabs .nav-link.active").inner_text() == "Home"
    page.keyboard.press("Enter")
    _idle(page)
    assert page.locator("#details-filters-sidebar").evaluate("el => el.inert")
    page.wait_for_function("document.activeElement.id === 'details-node-select'")
    page.focus("#main-tabs .nav-link.active")
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.textContent.trim()") == "Events"
    assert page.locator("#events-sidebar-container").evaluate("el => el.inert")
    page.keyboard.press("Tab")
    for _ in range(40):
        assert not page.evaluate("!!document.activeElement.closest('[inert]')")
        assert page.evaluate("document.documentElement.scrollLeft") == 0
        page.keyboard.press("Tab")
    assert page.console_errors == []


def test_graph_layout_and_fullscreen_escape_owns_one_layer(page):
    _seed(page)
    _activate_tab(page, "Nodes")
    _tab_to(page, "#btn-graph-settings")
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('graph-settings-panel').contains(document.activeElement)")
    _idle(page)
    for _ in range(15):
        page.keyboard.press("Tab")
        assert page.locator("#graph-settings-panel").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('graph-settings-panel').inert")
    assert page.evaluate("document.activeElement.id") == "btn-graph-settings"
    _tab_to(page, "#btn-fullscreen")
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('canvas-container').classList.contains('canvas-fullscreen')")
    _idle(page)
    for _ in range(12):
        page.keyboard.press("Tab")
        assert page.locator("#canvas-container").evaluate("el => el.contains(document.activeElement)"), page.evaluate("""() => ({
            active:document.activeElement.outerHTML.slice(0,200),
            canvas:document.getElementById('canvas-container').className,
            settings:document.getElementById('graph-settings-panel').getAttribute('aria-hidden')
        })""")
    _tab_to(page, "#cytoscape-graph")
    page.keyboard.press("Home")
    page.keyboard.press("Alt+Enter")
    page.wait_for_function("document.activeElement.id === 'ctx-menu-edit'")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == "cytoscape-graph"
    assert page.locator("#canvas-container").evaluate("el => el.classList.contains('canvas-fullscreen')")
    page.keyboard.press("Escape")  # Clear the graph cursor.
    page.keyboard.press("Escape")  # Then leave fullscreen.
    page.wait_for_function("!document.getElementById('canvas-container').classList.contains('canvas-fullscreen')")
    assert page.evaluate("document.activeElement.id") == "btn-fullscreen"
    assert page.console_errors == []


def test_graph_spatial_navigation_pan_and_selection_feedback(page):
    _seed(page)
    _activate_tab(page, "Nodes")
    # Deterministic geometry intentionally differs from the name order.
    page.evaluate("""() => {
        const cy = window.SkillTree.getCy(document.getElementById('cytoscape-graph'));
        cy.getElementById('Alpha').position({x:200, y:200});
        cy.getElementById('Beta').position({x:200, y:400});
        cy.getElementById('Goal').position({x:450, y:200});
        cy.zoom(1); cy.pan({x:0,y:0});
    }""")
    _tab_to(page, "#cytoscape-graph")
    page.keyboard.press("Home")
    page.keyboard.press("Enter")
    pan = page.evaluate("window.SkillTree.getCy(document.getElementById('cytoscape-graph')).pan()")
    page.keyboard.press("ArrowRight")
    assert "Focus: Goal" in page.inner_text(".keyboard-feedback")
    assert "Selected: Alpha" in page.inner_text(".keyboard-feedback")
    assert page.evaluate("window.SkillTree.getCy(document.getElementById('cytoscape-graph')).pan()") == pan
    page.keyboard.press("PageUp")
    assert "Focus: Beta" in page.inner_text(".keyboard-feedback")
    page.keyboard.press("Escape")
    assert page.evaluate("window.SkillTree.getCy(document.getElementById('cytoscape-graph')).$('node:selected').length") == 0
    assert page.evaluate("window.SkillTree.getCy(document.getElementById('cytoscape-graph')).$('.keyboard-current').length") == 0
    assert page.console_errors == []


def test_event_save_shortcut_and_modified_save_scope(page, server):
    _welcome(page)
    _tab_to(page, "#btn-events-sidebar-toggle")
    page.keyboard.press("Enter")
    _tab_to(page, "#btn-new-event")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.id === 'event-name'")
    _idle(page)
    page.keyboard.type("Keyboard Event")
    page.keyboard.press("Control+s")
    _idle(page)
    assert server.query("SELECT name FROM Events") == [("Keyboard Event",)]
    # Observe whether our handler consumed the key, then suppress the browser's
    # own Save dialog so the test can inspect shortcut scope safely.
    page.evaluate("""() => document.addEventListener('keydown', e => {
        if (e.ctrlKey && e.key.toLowerCase() === 's') {
            window.saveConsumed = e.defaultPrevented; e.preventDefault();
        }
    })""")
    page.keyboard.press("Control+Shift+s")
    assert page.evaluate("window.saveConsumed") is False
    page.locator("#btn-settings-toggle").focus()
    page.keyboard.press("Control+s")
    assert page.evaluate("window.saveConsumed") is False
    assert page.console_errors == []


def test_context_enter_retains_focus_and_help_dialog_returns_it(page):
    _welcome(page)
    _tab_to(page, "#btn-settings-toggle")
    page.keyboard.press("Enter")
    page.wait_for_selector("#settings-modal", state="visible")
    _tab_to(page, "#settings-modal .nav-link")
    for _ in range(12):
        if page.evaluate("document.activeElement.textContent.trim()") == "Contexts":
            break
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    _idle(page)
    _tab_to(page, ".ctx-row-name")
    page.keyboard.press("Enter")
    assert page.evaluate("document.activeElement.matches('.ctx-row-name')")
    page.keyboard.press("Control+/")
    page.wait_for_selector("dialog.keyboard-help[open]", state="visible")
    assert page.locator("dialog.keyboard-help").evaluate("el => el.scrollTop") == 0
    assert page.evaluate("document.activeElement.id") == "keyboard-help-title"
    page.keyboard.press("Tab")
    assert page.locator("dialog.keyboard-help").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    page.wait_for_selector("dialog.keyboard-help[open]", state="hidden")
    assert page.evaluate("document.activeElement.matches('.ctx-row-name')")
    assert page.console_errors == []


def test_reflection_reference_and_editor_own_focus_above_modal(page):
    _seed(page)
    _open_in_editor(page, "Alpha")
    page.check("#node-status-done input")
    page.click("#btn-save")
    page.wait_for_selector("#modal-time-calibration", state="visible")
    _idle(page)
    _tab_to(page, "#btn-reflection-ratings-info")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.id === 'btn-reflection-ratings-close'")
    for key in ("Tab", "Shift+Tab"):
        page.keyboard.press(key)
        assert page.locator("#reflection-ratings-popup").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    assert page.evaluate("document.activeElement.id") == "btn-reflection-ratings-info"
    assert page.is_visible("#modal-time-calibration")
    page.keyboard.press("Enter")
    _tab_to(page, "#btn-reflection-ratings-edit")
    page.keyboard.press("Enter")
    page.wait_for_selector("#modal-reflection-ratings-editor", state="visible")
    _idle(page)
    for _ in range(36):
        page.keyboard.press("Tab")
        assert page.locator("#modal-reflection-ratings-editor").evaluate("el => el.contains(document.activeElement)")
    for _ in range(36):
        page.keyboard.press("Shift+Tab")
        assert page.locator("#modal-reflection-ratings-editor").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Escape")
    page.wait_for_selector("#modal-reflection-ratings-editor", state="hidden")
    assert page.is_visible("#modal-time-calibration")
    assert page.console_errors == []


def test_profile_reference_escape_keeps_settings_open(page):
    _welcome(page)
    _tab_to(page, "#btn-settings-toggle")
    page.keyboard.press("Enter")
    page.wait_for_selector("#settings-modal", state="visible")
    _idle(page)
    _tab_to(page, "#btn-hp-profile-info")
    page.keyboard.press("Enter")
    page.wait_for_selector("#popover-hp-profile-info", state="visible")
    _idle(page)
    assert page.evaluate("document.activeElement.id") == "popover-hp-profile-info"
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.id") == "popover-hp-profile-info"
    page.keyboard.press("Escape")
    page.wait_for_selector("#popover-hp-profile-info", state="hidden")
    assert page.evaluate("document.activeElement.id") == "btn-hp-profile-info"
    assert page.is_visible("#settings-modal")
    assert page.console_errors == []


def test_open_dropdown_escape_keeps_panel_and_value(page):
    _welcome(page)
    _tab_to(page, "#btn-add")
    page.keyboard.press("Enter")
    _idle(page)
    _tab_to(page, "#node-type")
    page.keyboard.press("Space")
    page.wait_for_function("document.getElementById('node-type').matches(':open')")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Escape")
    page.wait_for_function("!document.getElementById('node-type').matches(':open')")
    assert page.input_value("#node-type") == ""
    assert not page.locator("#sidebar-editor-container").evaluate("el => el.inert")
    page.keyboard.press("Escape")
    page.wait_for_function("document.getElementById('sidebar-editor-container').inert")
    assert page.console_errors == []


def test_enter_on_a_tab_moves_into_it(page):
    _seed(page)
    # Events last: its sidebar holds focus until Escape, like any open panel.
    for name, focused in [("Nodes", "#cytoscape-graph"), ("Details", "#details-node-select"),
                          ("Home", ".suggestion-bar-row"), ("Events", "#events-search-input")]:
        _activate_tab(page, name)
        page.wait_for_function("s => document.activeElement.matches(s)", arg=focused)
    assert page.console_errors == []


def test_home_tab_order_skips_stepper_and_arrows_cross_lists(page):
    _seed(page)
    _new_node(page, "Gamma", "Learn")
    _close_editor(page)
    _idle(page)
    for name in ("Alpha", "Beta"):
        page.click(f'.suggestion-bar-row[data-node-menu="{name}"]', button="right")
        page.click("#ctx-menu-toggle-now")
        _idle(page)
    _activate_tab(page, "Home")
    page.wait_for_function("document.activeElement.matches('.now-card')")
    first = page.evaluate("document.activeElement.getAttribute('data-node-menu')")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.matches('.now-card')")
    second = page.evaluate("document.activeElement.getAttribute('data-node-menu')")
    assert second != first
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.matches('.suggestion-bar-row')")
    page.keyboard.press("ArrowUp")
    assert page.evaluate("document.activeElement.getAttribute('data-node-menu')") == second
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.matches('.suggestion-bar-row')")
    assert page.console_errors == []


def test_sidebar_search_and_list_join_by_arrows(page):
    _seed(page)
    _tab_to(page, "#btn-goals-toggle")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.id === 'details-goal-search'")
    page.wait_for_selector("#details-goal-sidebar .goal-card[tabindex='0']")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.matches('.goal-card')")
    page.keyboard.press("ArrowUp")
    assert page.evaluate("document.activeElement.id") == "details-goal-search"
    _tab_to(page, "#btn-goals-sidebar-new")
    assert page.evaluate("getComputedStyle(document.activeElement).outlineStyle") == "solid"
    assert page.console_errors == []


def test_analyze_gear_opens_into_its_field(page):
    _seed(page)
    _activate_tab(page, "Analyze")
    page.wait_for_selector("#btn-analyze-goals-limit", state="visible")
    _tab_to(page, "#btn-analyze-goals-limit")
    page.keyboard.press("Enter")
    page.wait_for_function("document.activeElement.id === 'setting-analyze-goals'")
    page.keyboard.press("Escape")
    page.wait_for_function("document.activeElement.id === 'btn-analyze-goals-limit'")
    page.wait_for_selector("#popover-analyze-goals", state="detached")
    assert page.console_errors == []
