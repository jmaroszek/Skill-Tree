"""Keep the design token layer from eroding.

STYLE_GUIDE.md named tokens for years while every call site hand-typed the
value, and the guide had no way to notice. These are the checks that would
have caught that: they fail on a new raw colour or font size in UI code, on a
token that exists in only one of the two languages, and on the component shape
that renders as nothing.

Each test says what drifted last time, so a failure explains itself.
"""
import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
TOKENS_CSS = ASSETS / "tokens.css"

# UI modules: everything that builds Dash components.
UI_MODULES = [
    "layout.py", "details_layout.py", "events_layout.py", "sidebars_layout.py",
    "settings_layout.py", "review_hub_layout.py", "analyze_layout.py",
    "callback_helpers.py", "callbacks.py", "details_callbacks.py",
    "event_callbacks.py", "settings_callbacks.py", "sidebars_callbacks.py",
    "review_hub_callbacks.py", "next_view.py", "canvas_view.py",
    "list_toolbar.py", "duration_ui.py", "context_picker.py", "ui_kit.py",
    "sidebar_state.py",
]

# Modules that legitimately hold real values rather than references:
#   config.py     - BADGE_PALETTE and the canvas colours Settings edits
#   styles.py     - Cytoscape parses its own stylesheet, not CSS
#   style_tokens  - the var() references themselves
# analyze_callbacks builds Plotly figures, which read computed values and
# cannot resolve a CSS variable; its chart constants stay literal and are
# pinned to the tokens by test_plotly_chart_colours_match_their_tokens below.
VALUE_OWNERS = {"config.py", "styles.py", "style_tokens.py", "analyze_callbacks.py"}

# Lines that legitimately hold a real value even inside a UI module. Each is a
# renderer that reads computed values and cannot resolve a CSS variable:
#
#   Plotly figures  - paper_bgcolor, marker_color, hoverlabel, axis colours
#   Cytoscape       - the community-cluster palette and per-element data
#
# Marked with a trailing `# literal:` comment naming the reason, so the
# exception is visible at the call site rather than hidden in this list.
LITERAL_OK = re.compile(r"#\s*literal:")

HEX = re.compile(r'["\']#[0-9a-fA-F]{3,8}["\']')
FONT_SIZE = re.compile(r'["\']fontSize["\']\s*:\s*["\'][\d.]+(?:rem|px|em)["\']')


def _source(name):
    return (ROOT / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("module", UI_MODULES)
def test_ui_modules_do_not_hardcode_colours(module):
    """A colour in UI code must come from style_tokens or config.BADGE_PALETTE.

    Before the token layer there were 361 hex literals across these files, and
    the same semantic colour was written several different ways -- which is how
    one table drew its Type column in an opaque #6c757d while the Delay and
    Status columns beside it used Bootstrap's translucent .text-muted.
    """
    offenders = []
    for i, line in enumerate(_source(module).splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):          # a comment may quote an old value
            continue
        if LITERAL_OK.search(line):
            continue
        for _ in HEX.finditer(line):
            offenders.append(f"{module}:{i}  {stripped[:88]}")
    assert not offenders, (
        "Hardcoded colour(s) found. Add the value to assets/tokens.css and "
        "reference it through style_tokens, or use config.badge_style() for a "
        "badge:\n  " + "\n  ".join(offenders))


@pytest.mark.parametrize("module", UI_MODULES)
def test_ui_modules_do_not_hardcode_font_sizes(module):
    """Font sizes come from the eight-step scale in assets/tokens.css.

    There were 28 distinct literals before, including a 0.72/0.78/0.82/0.88rem
    cluster whose members differed by less than a pixel, and three data tables
    that each picked a different one.
    """
    offenders = [
        f"{module}:{i}  {line.strip()[:88]}"
        for i, line in enumerate(_source(module).splitlines(), 1)
        if (FONT_SIZE.search(line) and not line.strip().startswith("#")
            and not LITERAL_OK.search(line))
    ]
    assert not offenders, (
        "Hardcoded font size(s) found. Use a step from style_tokens "
        "(FS_XS..FS_2XL):\n  " + "\n  ".join(offenders))


def test_every_python_token_resolves_to_a_real_css_variable():
    """style_tokens exports references; assets/tokens.css defines them.

    A typo in either direction yields `var(--st-typo)`, which silently computes
    to nothing rather than raising.
    """
    css = TOKENS_CSS.read_text(encoding="utf-8")
    defined = set(re.findall(r"(--st-[a-z0-9-]+)\s*:", css))
    referenced = set(re.findall(r"var\((--st-[a-z0-9-]+)\)",
                                _source("style_tokens.py")))
    missing = sorted(referenced - defined)
    assert not missing, (
        f"style_tokens references CSS variables that tokens.css does not "
        f"define: {missing}")


def test_every_css_variable_used_in_a_stylesheet_is_defined():
    """Same check from the stylesheet side."""
    css = TOKENS_CSS.read_text(encoding="utf-8")
    defined = set(re.findall(r"(--st-[a-z0-9-]+)\s*:", css))
    missing = {}
    for sheet in sorted(ASSETS.glob("*.css")):
        if sheet.name == "tokens.css":
            continue
        used = set(re.findall(r"var\((--st-[a-z0-9-]+)", sheet.read_text(encoding="utf-8")))
        if used - defined:
            missing[sheet.name] = sorted(used - defined)
    assert not missing, f"Undefined CSS variables referenced: {missing}"


def test_text_secondary_matches_what_bootstraps_text_muted_resolves_to():
    """The collision that started this.

    STYLE_GUIDE.md used to define a token it called "text-muted" as #6c757d.
    Bootstrap 5.3 also has a .text-muted class, which under DARKLY resolves to
    var(--bs-secondary-color) -- rgba(255,255,255,.75). The app used both,
    believing they were the same thing, and adjacent cells of one table
    disagreed. --st-text-secondary must stay pinned to the class's value so
    the token and the class remain interchangeable.
    """
    css = TOKENS_CSS.read_text(encoding="utf-8")
    m = re.search(r"--st-text-secondary:\s*([^;]+);", css)
    assert m, "--st-text-secondary is missing from tokens.css"
    value = m.group(1).strip().replace(" ", "")
    assert value == "rgba(255,255,255,0.75)", (
        f"--st-text-secondary is {m.group(1).strip()!r}. It must equal what "
        f"Bootstrap's .text-muted computes to under DARKLY "
        f"(rgba(255, 255, 255, 0.75)); otherwise a cell using the token and a "
        f"cell using the class render differently again.")


def test_plotly_chart_colours_match_their_tokens():
    """Plotly reads computed values, so analyze_callbacks keeps real hex.

    That is a legitimate exception, but an unwatched one drifts: its status map
    used to paint Blocked in stock Bootstrap red while the rest of the app used
    the palette's darker red.
    """
    import analyze_callbacks
    from config import BADGE_PALETTE
    from models import STATUS_OPEN, STATUS_DONE, STATUS_BLOCKED

    for status in (STATUS_OPEN, STATUS_DONE, STATUS_BLOCKED):
        assert analyze_callbacks._STATUS_COLORS[status] == BADGE_PALETTE[status][0], (
            f"Analyze paints {status} differently from its badge elsewhere.")

    css = TOKENS_CSS.read_text(encoding="utf-8")
    for const, token in [("_BG", "--st-bg-canvas"),
                         ("_CARD_BG", "--st-bg-raised"),
                         ("_BORDER", "--st-border-panel")]:
        expected = re.search(rf"{token}:\s*([^;]+);", css).group(1).strip()
        assert getattr(analyze_callbacks, const) == expected, (
            f"analyze_callbacks.{const} has drifted from {token}.")


def test_the_three_data_tables_share_one_definition():
    """Details subtasks, Events dormant nodes and Reflection history.

    They sit side by side conceptually and used to disagree on font size
    (0.82 / 0.85 / unset) and on whether to clear DARKLY's per-cell background
    tint (only one did).
    """
    for module in ("details_layout.py", "events_layout.py",
                   "review_hub_callbacks.py"):
        src = _source(module)
        assert "tokens.TABLE_PROPS" in src, f"{module} builds a table by hand"
        assert "tokens.TABLE_STYLE" in src, f"{module} sets its own table style"


def test_no_unicode_glyphs_are_used_as_icons():
    """One icon family at one weight, which STYLE_GUIDE.md has always required.

    There used to be eight close controls written as a Unicode multiplication
    sign in five style variants, plus arrows, a restore glyph defined three
    times, a drag handle and a caret. Several were html.Span, so they were not
    keyboard-reachable.
    """
    glyphs = "×←→−☰▸↺✓✗"
    pattern = re.compile(
        rf'html\.(?:Span|Button|Div)\(\s*["\'](?:[{glyphs}]|\\u[0-9a-fA-F]{{4}})["\']')
    offenders = []
    for module in UI_MODULES:
        for i, line in enumerate(_source(module).splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{module}:{i}  {line.strip()[:88]}")
    assert not offenders, (
        "Unicode glyph used as an icon. Use a Bootstrap Icon through ui_kit:\n  "
        + "\n  ".join(offenders))


def test_component_builders_never_return_a_bare_list():
    """Dash does not flatten nested lists inside `children`.

    React rejects them outright -- "Objects are not valid as a React child" --
    and silently drops the whole subtree, so the control simply is not in the
    DOM. Nothing at the Python level notices, because the component tree looks
    correct; this only shows up in a browser. ui_kit hit exactly this, and the
    fix is a wrapper with `display: contents`.
    """
    tree = ast.parse(_source("ui_kit.py"))
    offenders = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.List):
                offenders.append(f"ui_kit.{fn.name} (line {node.lineno})")
    assert not offenders, (
        "These return a bare list, which Dash cannot place in `children`; "
        "wrap them in a `display: contents` element instead:\n  "
        + "\n  ".join(offenders))


def test_the_badge_table_in_the_style_guide_matches_the_palette():
    """STYLE_GUIDE.md documents BADGE_PALETTE as a table for human reading.

    That is worth keeping -- the notes beside each value explain *why* a hue was
    chosen -- but a table maintained by hand drifts. One row used to claim
    SoftRelPri matched the subtasks-table Soft tile when the two had different
    values. This holds the documentation to the code.
    """
    from config import BADGE_PALETTE

    guide = (ROOT / "STYLE_GUIDE.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\|\s*(\w+)\s*\|\s*`(#[0-9a-fA-F]{6})`\s*\|\s*`(#[0-9a-fA-F]{3,6})`",
                      guide, re.M)
    documented = {name: (bg, fg) for name, bg, fg in rows}
    assert documented, "no badge rows found in STYLE_GUIDE.md"

    mismatched = {
        name: {"guide": pair, "palette": BADGE_PALETTE[name]}
        for name, pair in documented.items()
        if name in BADGE_PALETTE and BADGE_PALETTE[name] != pair
    }
    assert not mismatched, (
        f"STYLE_GUIDE.md documents badge values that config.BADGE_PALETTE "
        f"does not agree with: {mismatched}")
