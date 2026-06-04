"""Smoke test: the app module imports cleanly and registers its callbacks."""

import importlib
import sys

import pytest


@pytest.fixture
def isolated_app_import(monkeypatch):
    """Force a fresh `import app` inside a test, with browser/timer side effects neutralized."""
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")

    import threading
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **kw: None)

    class _NoopTimer:
        def __init__(self, *a, **kw): pass
        def start(self): pass
        def cancel(self): pass

    monkeypatch.setattr(threading, "Timer", _NoopTimer)

    for modname in ("app",):
        sys.modules.pop(modname, None)

    import app as app_module
    importlib.reload(app_module)
    return app_module


def test_app_module_imports_without_side_effects(isolated_app_import):
    app_module = isolated_app_import
    assert app_module.app is not None
    assert app_module.app.layout is not None


def test_app_callback_map_has_many_callbacks(isolated_app_import):
    app_module = isolated_app_import
    assert len(app_module.app.callback_map) >= 40, (
        f"expected >=40 registered callbacks, got {len(app_module.app.callback_map)}"
    )


def test_app_title_reflects_environment(isolated_app_import):
    app_module = isolated_app_import
    assert app_module.app.title in {"Skill Tree", "Skill Tree (Sandbox)"}


def test_parse_port_defaults_and_accepts_override(isolated_app_import):
    app_module = isolated_app_import
    assert app_module._parse_port(["app.py"]) == 8050
    assert app_module._parse_port(["app.py", "--port", "8060"]) == 8060
    assert app_module._parse_port(["app.py", "--port", "nope"]) == 8050


def test_existing_instance_running_checks_skill_tree_endpoint(monkeypatch, isolated_app_import):
    app_module = isolated_app_import

    # Occupied-port path: delegate the "is it actually us?" decision to the
    # boot-id endpoint check. Force the port to read as occupied so the fast
    # free-port short-circuit doesn't pre-empt the delegation (keeps the test
    # hermetic regardless of what's really bound to 8050 on this machine).
    monkeypatch.setattr(app_module, "_port_is_free", lambda port: False)
    monkeypatch.setattr(app_module, "_existing_skill_tree_server", lambda port: port == 8050)

    assert app_module._existing_instance_running(8050) is True
    assert app_module._existing_instance_running(8060) is False


def test_existing_instance_running_free_port_skips_endpoint_check(monkeypatch, isolated_app_import):
    app_module = isolated_app_import

    # Free port → no instance, and the (potentially slow) endpoint probe must
    # never run. This is the whole point of the bind-first fast path.
    monkeypatch.setattr(app_module, "_port_is_free", lambda port: True)

    def _should_not_be_called(port):
        raise AssertionError("endpoint probe should be skipped when the port is free")

    monkeypatch.setattr(app_module, "_existing_skill_tree_server", _should_not_be_called)

    assert app_module._existing_instance_running(8051) is False
