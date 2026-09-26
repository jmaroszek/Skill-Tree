"""Every plain callback id is in the page from the start.

Dash can't wire an Input or State to an id that isn't in the layout, and it
says so only in the browser console ("ID not found in layout"). A component
that comes and goes, like a button inside a card that's only sometimes
shown, needs a pattern-matching id instead.
"""
import app as app_module


def _ids(component, found):
    if isinstance(component, (list, tuple)):
        for child in component:
            _ids(child, found)
        return found
    if not hasattr(component, "to_plotly_json"):
        return found
    component_id = getattr(component, "id", None)
    if isinstance(component_id, str):
        found.add(component_id)
    return _ids(getattr(component, "children", None), found)


def test_every_plain_callback_id_is_in_the_initial_layout(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    dash_app = app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False))
    layout = dash_app.layout() if callable(dash_app.layout) else dash_app.layout
    present = _ids(layout, set())
    missing = sorted({
        dep["id"]
        for spec in dash_app.callback_map.values()
        for dep in spec.get("inputs", []) + spec.get("state", [])
        # Pattern-matching ids arrive as JSON ('{"index": ...}'); they may be absent.
        if isinstance(dep["id"], str) and not dep["id"].startswith("{")
        and dep["id"] not in present
    })
    assert missing == []
