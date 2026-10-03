"""Editor feedback deadlines on a real Dash page."""
import pytest

pytest.importorskip("playwright.sync_api")


def test_feedback_expires_while_hidden_and_new_messages_restart_deadline(page):
    def message(text):
        page.evaluate(
            "text => window.dash_clientside.set_props('save-output', {children: text})",
            text,
        )
        page.wait_for_function(
            "text => document.getElementById('save-output').textContent === text",
            arg=text,
        )

    message("Logged actuals for 'First'.")
    page.wait_for_timeout(3000)
    message("Saved 'Second'.")
    # The first message's deadline must not erase the second message.
    page.wait_for_timeout(2500)
    assert page.locator("#save-output").text_content() == "Saved 'Second'."
    page.wait_for_function(
        "document.getElementById('save-output').textContent === ''",
        timeout=4000,
    )
    # It expires even though the editor starts closed, then stays empty on open.
    page.evaluate(
        "window.dash_clientside.set_props('sidebar-editor-container', "
        "{style: {transform: 'translateX(0px)'}})"
    )
    assert page.locator("#save-output").text_content() == ""
