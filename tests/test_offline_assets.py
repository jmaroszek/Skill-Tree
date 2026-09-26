"""The app renders offline: every stylesheet, font and script is served locally.

The theme, its Lato font, the icon font and SortableJS came from jsDelivr and
Google Fonts. Offline, or behind a firewall that blocks them, the app was
unstyled, its icon-only toolbar blank and drag-to-reorder dead. They now live
in assets/vendor.
"""
import re
from pathlib import Path

import pytest

import app as app_module

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
VENDOR = ASSETS / "vendor"
REMOTE = re.compile(r"""(?:src|href)\s*=\s*["']?(https?:)?//""", re.I)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    app = app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False))
    return app.server.test_client()


def test_the_page_loads_nothing_from_another_host(client):
    page = client.get("/").get_data(as_text=True)
    tags = re.findall(r"<(?:link|script)\b[^>]*>", page)
    assert tags, "the page should link its assets"
    remote = [tag for tag in tags if REMOTE.search(tag)]
    assert remote == []


def test_the_theme_loads_once_and_before_the_apps_own_css(client):
    page = client.get("/").get_data(as_text=True)
    for sheet in app_module.VENDOR_STYLESHEETS:
        assert page.count(sheet) == 1, sheet
    assert page.index("bootswatch-darkly/bootstrap.min.css") < page.index("theme.css")
    # Loaded on demand by the sortables, not by Dash's automatic includes.
    assert "Sortable.min.js" not in page


def test_every_vendored_file_the_page_needs_is_served(client):
    needed = list(app_module.VENDOR_STYLESHEETS) + ["/assets/vendor/sortablejs/Sortable.min.js"]
    for sheet in app_module.VENDOR_STYLESHEETS:
        css = (ROOT / sheet.lstrip("/")).read_text(encoding="utf-8")
        folder = sheet.rsplit("/", 1)[0]
        for ref in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
            if ref.startswith("data:"):
                continue
            needed.append(f"{folder}/{ref.split('?')[0].lstrip('./')}")
    for url in needed:
        response = client.get(url)
        assert response.status_code == 200 and response.data, url


def test_no_asset_reaches_for_a_remote_url():
    offenders = []
    for path in sorted(ASSETS.rglob("*")):
        if path.suffix not in {".js", ".css"} or VENDOR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        # SVG data URIs name the SVG namespace; that isn't a fetch.
        text = text.replace("http://www.w3.org/2000/svg", "")
        if re.search(r"https?://", text):
            offenders.append(path.name)
    assert offenders == []


def test_the_vendored_theme_no_longer_imports_google_fonts():
    css = (VENDOR / "bootswatch-darkly" / "bootstrap.min.css").read_text(encoding="utf-8")
    assert "@import" not in css and "fonts.googleapis.com" not in css


def test_each_vendored_package_carries_its_license():
    for package in ("bootswatch-darkly", "bootstrap-icons", "lato", "sortablejs"):
        assert (VENDOR / package / "LICENSE").is_file(), package
