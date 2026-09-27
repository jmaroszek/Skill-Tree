"""An exception a callback lets escape is logged and shown, never swallowed.

In production Dash ran without dev tools, so a callback that raised simply
left the page as it was: the action didn't happen, and nothing on screen or in
the log said why. app.report_callback_error is the app-wide on_error hook.
"""
import logging

import pytest
from dash import Input, Output

import app as app_module
import callbacks


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    return app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False))


def _dispatch(app, output, input_id):
    client = app.server.test_client()
    component, prop = output.split(".")
    return client.post("/_dash-update-component", json={
        "output": output,
        "outputs": {"id": component, "property": prop},
        "inputs": [{"id": input_id, "property": "value", "value": 1}],
        "changedPropIds": [f"{input_id}.value"],
        "state": [],
    })


def test_an_escaping_exception_is_logged_and_opens_the_error_dialog(app, caplog):
    @app.callback(Output("test-sink", "children"), Input("test-source", "value"),
                  prevent_initial_call=True)
    def explode(_value):
        raise RuntimeError("kaboom")

    with caplog.at_level(logging.ERROR):
        response = _dispatch(app, "test-sink.children", "test-source")

    assert response.status_code == 200
    side = response.get_json()["sideUpdate"]
    assert side["modal-app-error"] == {"is_open": True}
    assert "log" in side["app-error-body"]["children"]
    assert "kaboom" in caplog.text
    assert "test-source.value" in caplog.text


def test_the_layout_carries_the_error_dialog(app):
    page = app.server.test_client().get("/_dash-layout").get_data(as_text=True)
    assert '"modal-app-error"' in page and '"btn-close-app-error"' in page


def test_an_unexpected_save_failure_is_logged_not_shown_raw(monkeypatch, caplog):
    """The core save path used to show str(exception) and log nothing."""
    def broken(*_args, **_kwargs):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(callbacks, "handle_save", broken)

    with caplog.at_level(logging.ERROR):
        message = _save_new_node(monkeypatch)

    assert message.startswith("Error: Saving the node failed unexpectedly")
    assert "database is locked" not in message
    assert "database is locked" in caplog.text


def _save_new_node(monkeypatch):
    import inspect
    import dash
    probe = dash.Dash(__name__)
    probe.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(probe)
    target = next(k for k in probe.callback_map
                  if k.startswith("..elements-pending-store.data"))
    core_engine = probe.callback_map[target]["callback"]
    while hasattr(core_engine, "__wrapped__"):
        core_engine = core_engine.__wrapped__
    monkeypatch.setattr(callbacks, "get_trigger_id", lambda: "btn-save")
    monkeypatch.setattr(callbacks, "get_all_triggered_ids", lambda: {"btn-save"})
    kwargs = dict.fromkeys(inspect.signature(core_engine).parameters)
    kwargs.update(name="Fresh", n_type="Learn", desc="", context="Mind",
                  status_done=[], val=5, interest=5, diff=5, time_o=1,
                  time_m=2, time_p=4, time_unit="hours", link_values=[],
                  link_ids=[], alias_values=[],
                  ed_style={"transform": "translateX(0px)"})
    return callbacks.CoreResponse(*core_engine(**kwargs)).message
