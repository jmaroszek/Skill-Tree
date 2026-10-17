"""The page's asset scripts load in an order where each has what it uses.

Dash loads the files at the top of assets/ first, then each folder's, in
name order. The boot scripts sit at the top, so they run before any
feature's. Within that order, a script that calls another's SkillTree
function while it loads must come after it: support/asset_load.js runs every
script in Dash's order, against a stand-in for the browser, and reports any
that throws.
"""
import json
import shutil
import subprocess
from pathlib import Path

import dash
import pytest

from skilltree.app import AppSettings, create_app
from skilltree.ui.canvas.registry import client_registry
from support.paths import ASSETS, ROOT, app_asset_files

# Scripts that must run before every feature's: polyfill fixes, the bridge,
# the startup cover.
BOOT = {'00_browser_bridge.js', '00_cytoscape_extent.js', '00_dash_noop_dispatch.js',
        '01_keyboard_focus.js', 'native_builtins.js', 'startup_cover.js', 'store_mount.js',
        'window_chrome.js'}


@pytest.fixture
def load_order(temp_database):
    """The asset scripts as the app's Dash loads them, by file path."""
    app = create_app(AppSettings(environment="sandbox", configure_logging=False))
    probe = dash.Dash(__name__, assets_folder=app.config.assets_folder,
                      assets_path_ignore=app.config.assets_path_ignore,
                      assets_ignore=app.config.assets_ignore)
    probe._walk_assets_directory()
    return [resource["filepath"] for resource in probe.scripts._resources._resources]


def test_the_boot_scripts_load_first(load_order):
    first = {Path(path).name for path in load_order[:len(BOOT)]}
    assert first == BOOT
    top_level = {path.name for path in ASSETS.glob("*.js")} - {"hard_reload_on_restart.js"}
    assert top_level == BOOT


def test_every_script_loads_after_what_it_uses(tmp_path, load_order):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to load the asset scripts")
    order = tmp_path / "order.json"
    order.write_text(json.dumps({"canvases": client_registry(), "scripts": load_order}))
    result = subprocess.run(
        [node, str(ROOT / "tests" / "support" / "asset_load.js"), str(order)],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_the_stylesheets_keep_their_cascade():
    """All the app's CSS is in css/, which Dash loads in name order: the order
    the cascade was written for."""
    assert {path.parent for path in app_asset_files(".css")} == {ASSETS / "css"}


def test_only_the_vendor_folder_is_left_out():
    """Dash skips any folder whose name contains "vendor" (assets_path_ignore),
    so a feature folder can't be called that."""
    folders = [path for path in ASSETS.rglob("*") if path.is_dir()]
    skipped = [path for path in folders if "vendor" in path.relative_to(ASSETS).parts[0]]
    assert {path.relative_to(ASSETS).parts[0] for path in skipped} == {"vendor"}
