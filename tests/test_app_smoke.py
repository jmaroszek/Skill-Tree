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
    app_module.app = app_module.create_app(
        app_module.AppSettings(environment="sandbox", configure_logging=False))
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


def test_app_publishes_the_canvas_registry(isolated_app_import):
    app_module = isolated_app_import
    assert 'window.SkillTree.canvases' in app_module.app.index_string


def test_the_served_page_opens_behind_the_startup_cover(isolated_app_import):
    """What the browser receives, not just the template: the cover comes
    before the entry point, and the canvas registry still lands ahead of the
    asset scripts that read it."""
    page = isolated_app_import.app.server.test_client().get("/").get_data(as_text=True)

    assert page.index('id="startup-cover"') < page.index('id="react-entry-point"')
    assert page.index('window.SkillTree.canvases') < page.index('startup_cover.js')


def test_app_records_the_version_that_opened_the_database(isolated_app_import):
    from config import ConfigManager
    from version import __version__

    assert ConfigManager.get_last_app_version() == __version__


def test_app_title_reflects_environment(isolated_app_import):
    app_module = isolated_app_import
    assert app_module.app.title in {"Skill Tree", "Skill Tree (Sandbox)"}
