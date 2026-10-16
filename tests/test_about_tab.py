"""Settings > App controls, plus standalone diagnostic/build helpers."""
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from skilltree.features.settings import about
from skilltree.runtime import paths as app_paths
from skilltree.store import database
from skilltree.store.graph.manager import GraphManager
from skilltree.shell import build_app_layout
from skilltree.domain.models import Node
from skilltree.runtime.version import __version__
from skilltree.store import schema

ROOT = Path(__file__).resolve().parents[1]


def _ids(component, found=None):
    found = set() if found is None else found
    component_id = getattr(component, "id", None)
    if isinstance(component_id, str):
        found.add(component_id)
    children = getattr(component, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if hasattr(child, "children") or hasattr(child, "id"):
            _ids(child, found)
    return found


def test_app_and_data_keeps_only_version_and_update_preference():
    ids = _ids(build_app_layout([], env="sandbox"))
    assert {"about-version", "about-updates", "about-update-auto"} <= ids
    assert not ids & {"btn-open-data-folder", "btn-open-log-folder",
                      "about-diagnostics", "about-copy-diagnostics", "about-report-link",
                      "btn-check-updates", "about-update-status", "btn-open-notices"}


def test_diagnostics_name_the_build_and_the_data(monkeypatch):
    GraphManager().add_node(Node(
        name="Sleep", type="Learn", description="", value=5, time_o=1, time_m=2,
        time_p=3, interest=5, difficulty=5, status="Open", context="Mind"))
    text = about.diagnostics()
    assert f"Skill Tree {__version__}" in text
    assert "Python" in text and "SQLite" in text and "Dash" in text
    assert f"schema {schema.SCHEMA_VERSION}" in text
    assert "1 nodes" in text


def test_diagnostics_hide_the_home_folder(monkeypatch, tmp_path):
    """They get pasted into public issues; a home folder names its owner."""
    home = tmp_path / "alice"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv(app_paths.HOME_ENV, str(home / "AppData" / "Skill Tree"))
    monkeypatch.setattr(database, "get_db_path",
                        lambda: str(home / "AppData" / "Skill Tree" / "Data" / "skilltree.db"))
    schema.init_db(recheck=True)
    text = about.diagnostics()
    assert "alice" not in text
    assert "~" in text


def test_the_report_link_opens_the_bug_form_with_the_diagnostics():
    url = urlparse(about.report_url("Skill Tree 1.0 & more"))
    assert (url.scheme, url.netloc, url.path) == (
        "https", "github.com", "/jmaroszek/Skill-Tree/issues/new")
    query = parse_qs(url.query)
    assert query["template"] == ["bug_report.yml"]
    assert query["diagnostics"] == ["Skill Tree 1.0 & more"]


def test_the_bug_form_has_the_field_the_link_fills():
    form = (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s+id: diagnostics\s*$", form, re.M)


def _component(root, component_id):
    if getattr(root, "id", None) == component_id:
        return root
    children = getattr(root, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if hasattr(child, "children") or hasattr(child, "id"):
            found = _component(child, component_id)
            if found is not None:
                return found
    return None


def test_the_toolbar_has_no_external_help_button():
    assert _component(build_app_layout([], env="sandbox"), "btn-help") is None


def test_the_notice_file_remains_available_to_packaged_builds(monkeypatch, tmp_path):
    notices = tmp_path / "THIRD_PARTY_NOTICES.txt"
    notices.write_text("the notices")
    monkeypatch.setattr(about, "resource_path", lambda *parts: tmp_path.joinpath(*parts))
    assert about.notices_path() == notices


def test_a_build_without_notices_returns_no_path(monkeypatch, tmp_path):
    monkeypatch.setattr(about, "resource_path", lambda *parts: tmp_path.joinpath(*parts))
    assert about.notices_path() is None


def test_the_notices_cover_every_runtime_package_and_vendored_asset():
    pytest.importorskip("packaging")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "third_party_notices", Path(__file__).parents[1] / "packaging" / "third_party_notices.py")
    notices = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(notices)

    text = notices.notices()

    for line in (Path(__file__).parents[1] / "requirements.txt").read_text().splitlines():
        name = line.split("#")[0].split("==")[0].strip()
        if name and not name.startswith("-"):
            pattern = "[-_]".join(map(re.escape, re.split(r"[-_]", name)))
            assert re.search(rf"^{pattern} \d", text, re.IGNORECASE | re.MULTILINE), name
    for vendored in ("Bootstrap Icons", "Bootswatch Darkly", "Lato font", "SortableJS"):
        assert vendored in text
    assert "(No license text" not in text
