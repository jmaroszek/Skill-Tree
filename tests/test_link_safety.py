"""Opening a saved link asks first when it would start an app or reach a server (P3.7).

A link is data, and since P2.4 it can arrive in someone else's export. Most
links open at once: web pages, email, Obsidian notes, documents and folders
on this computer. Three kinds wait for a yes, the way a browser asks before
handing a link to another program:

- Any other scheme runs whatever app registered it. On Windows some of those
  handlers have been exploitable (ms-msdt, "Follina").
- A network path (\\\\host\\share) makes Windows sign in to that host, which
  hands it the user's password hash. Merely checking that the file exists
  does it, so the question comes before any filesystem call.
- A program, script, installer or shortcut. The system opens those by
  running them.
"""
import os

import dash
import pytest

import resource_links as resources
from resource_links import NeedsConfirmation

# Written around the Resource sections new databases used to start with.
pytestmark = pytest.mark.usefixtures("legacy_resource_sections")

MIXED = {"id": "files", "name": "Files", "kind": "mixed", "root_path": ""}


@pytest.fixture
def opened(monkeypatch):
    calls = []
    monkeypatch.setattr(resources, "open_path", lambda target: calls.append(("os", target)))
    monkeypatch.setattr(resources.webbrowser, "open_new_tab",
                        lambda target: calls.append(("browser", target)) or True)
    return calls


@pytest.fixture
def no_network_touch(monkeypatch):
    """Fail if anything looks at a network path before the user agreed."""
    real_exists, real_isdir = os.path.exists, os.path.isdir

    def guarded(real):
        def check(path):
            text = os.fspath(path).replace("/", "\\")
            assert not text.startswith("\\\\evil"), f"touched {path} before asking"
            return real(path)
        return check
    monkeypatch.setattr(os.path, "exists", guarded(real_exists))
    monkeypatch.setattr(os.path, "isdir", guarded(real_isdir))


@pytest.mark.parametrize("link, how", [
    ("https://example.com/a", "browser"),
    ("http://example.com", "browser"),
    ("mailto:someone@example.com", "os"),
    ("obsidian://open?vault=Notes&file=a", "os"),
])
def test_everyday_links_open_without_asking(opened, link, how):
    resources.open_resource(link, MIXED)
    assert opened == [(how, link)]


@pytest.mark.parametrize("link, named", [
    ("notion://www.notion.so/page", "notion:"),
    ("ms-msdt:/id PCWDiagnostic /skip force", "ms-msdt:"),
    ("search-ms:query=x&crumb=location:\\\\evil.example\\s", "search-ms:"),
    ("file:///C:/Windows/System32/calc.exe", "file:"),
    ("javascript:alert(1)", "javascript:"),
])
def test_other_schemes_ask_first_and_open_once_agreed(opened, link, named):
    with pytest.raises(NeedsConfirmation) as asked:
        resources.open_resource(link, MIXED)
    assert named in str(asked.value)
    assert opened == []

    resources.open_resource(link, MIXED, confirmed=True)
    assert opened == [("os", link)]


@pytest.mark.parametrize("link", [
    "\\\\evil.example\\share\\notes.md",
    "//evil.example/share/notes.md",
    "\\\\?\\UNC\\evil.example\\share\\notes.md",
])
def test_a_network_path_asks_before_touching_the_network(opened, no_network_touch, link):
    with pytest.raises(NeedsConfirmation) as asked:
        resources.open_resource(link, MIXED)
    assert "evil.example" in str(asked.value)
    assert opened == []


def test_a_network_root_folder_asks_too(opened, no_network_touch):
    section = {**MIXED, "root_path": "\\\\evil.example\\share"}
    with pytest.raises(NeedsConfirmation, match="evil.example"):
        resources.open_resource("notes/a.pdf", section)
    obsidian = {**section, "kind": "obsidian"}
    with pytest.raises(NeedsConfirmation, match="evil.example"):
        resources.open_resource("notes/a.md", obsidian)
    assert opened == []


@pytest.mark.parametrize("link", [
    "C:\\Windows\\System32\\calc.exe",
    "C:\\Users\\Public\\run-me.BAT",        # any case
    "C:\\Users\\Public\\setup.exe.",         # Windows drops the trailing dot
    "C:\\Users\\Public\\invoice.pdf.exe",    # the last suffix is what runs
    "C:\\Users\\Public\\Desktop\\tool.lnk",  # a shortcut can point anywhere
])
def test_a_file_that_opening_would_run_asks_first(opened, link):
    with pytest.raises(NeedsConfirmation) as asked:
        resources.open_resource(link, MIXED)
    assert "run a program" in str(asked.value)
    assert opened == []


@pytest.mark.parametrize("path, suffix", [
    ("/Applications/Calculator.app", "app"),
    ("/Users/me/Downloads/start.command", "command"),
    ("/home/me/Desktop/installer.desktop", "desktop"),
    ("/home/me/tools/deploy.sh", "sh"),
    ("/home/me/Downloads/Tool.AppImage", "appimage"),
    ("/home/me/notes/paper.pdf", None),
    ("/home/me/notes", None),
    ("C:\\notes\\archive.tar.gz", None),
])
def test_runnable_files_are_named_by_their_last_suffix(path, suffix):
    assert resources.runnable_suffix(path) == suffix


def test_a_runnable_file_opens_once_agreed(opened, tmp_path):
    program = tmp_path / "tool.exe"
    program.write_bytes(b"MZ")
    with pytest.raises(NeedsConfirmation, match=r"\.exe file"):
        resources.open_resource(str(program), MIXED)
    resources.open_resource(str(program), MIXED, confirmed=True)
    assert opened == [("os", str(program))]


def test_runnable_files_under_a_root_folder_or_in_a_vault_ask_too(opened, tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "setup.lnk").write_bytes(b"L")
    (tmp_path / "sync.sh").write_text("echo hi")
    section = {**MIXED, "root_path": str(tmp_path)}
    with pytest.raises(NeedsConfirmation, match=r"\.lnk file"):
        resources.open_resource("tools/setup.lnk", section)
    with pytest.raises(NeedsConfirmation, match=r"\.sh file"):
        resources.open_resource("sync.sh", {**section, "kind": "obsidian"})
    assert opened == []


@pytest.mark.parametrize("name", ["paper.pdf", "notes.md", "plan.docx", "photo.JPG", "folder"])
def test_documents_and_folders_open_without_asking(opened, tmp_path, name):
    target = tmp_path / name
    if "." in name:
        target.write_text("x")
    else:
        target.mkdir()
    resources.open_resource(str(target), MIXED)
    assert opened == [("os", str(target))]


def test_windows_drive_paths_are_not_mistaken_for_schemes(opened, tmp_path):
    local = tmp_path / "notes.txt"
    local.write_text("x")
    resources.open_resource(str(local), MIXED)
    assert opened == [("os", str(local))]
    assert resources.link_scheme("C:\\Users\\me\\notes.txt") is None
    assert resources.link_scheme("c:/notes.txt") is None


def test_a_bare_domain_with_a_port_is_a_web_address_not_a_scheme(opened):
    assert resources.link_scheme("example.com:8080/docs") is None
    resources.open_resource("example.com:8080/docs", MIXED)
    assert opened == [("browser", "https://example.com:8080/docs")]


# --- The two ways a link is opened ------------------------------------------

def test_the_context_menu_route_relays_the_question(monkeypatch, opened):
    import app as app_module
    from graph_manager import GraphManager
    from models import Node
    monkeypatch.setenv("WERKZEUG_RUN_MAIN", "true")
    GraphManager().add_node(Node(
        name="Reading", type="Learn", description="", value=5, time_o=1, time_m=2,
        time_p=3, interest=5, difficulty=5, status="Open", context="Mind",
        resource_links={"website": ["notion://www.notion.so/page"]}))
    client = app_module.create_app(app_module.AppSettings(
        environment="sandbox", configure_logging=False)).server.test_client()
    ask = {"node": "Reading", "section": "website", "index": 0}

    first = client.post("/open-resource", json=ask).get_json()
    assert first["ok"] is False and "notion:" in first["confirm"]
    assert opened == []

    second = client.post("/open-resource", json={**ask, "confirmed": True}).get_json()
    assert second == {"ok": True}
    assert opened == [("os", "notion://www.notion.so/page")]


def _callbacks():
    from callbacks import register_callbacks
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


def test_the_editor_button_asks_through_a_confirm_dialog(monkeypatch, opened):
    from dash._callback_context import context_value
    from dash._utils import AttributeDict
    monkeypatch.setattr(resources, "get_sections", lambda: [dict(MIXED, id="website")])
    import callbacks
    monkeypatch.setattr(callbacks, "get_sections", lambda: [dict(MIXED, id="website")])
    found = _callbacks()
    token = context_value.set(AttributeDict(
        triggered_inputs=[{"prop_id": '{"index":"website:0","type":"resource-open"}.n_clicks',
                           "value": 1}]))
    try:
        result = found["open_resource_link"](
            [1], ["notion://www.notion.so/page"], [{"type": "resource-link", "index": "website:0"}])
    finally:
        context_value.reset(token)
    status, message, displayed, pending = result
    assert displayed is True and "notion:" in message
    assert pending == {"section": "website", "link": "notion://www.notion.so/page"}
    assert opened == []

    found["open_confirmed_link"](1, pending)
    assert opened == [("os", "notion://www.notion.so/page")]
