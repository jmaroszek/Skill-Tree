"""The cursor stays the arrow unless it says something (STYLE_GUIDE.md, Cursors).

Buttons, cards and menu rows keep the arrow, so only `.link-like` may show the
hand. The help, move and crosshair cursors are web-page habits the app dropped.
"""
import re

from support.paths import ROOT, app_asset_files

_CSS_RULE = re.compile(r"([^{}]*)\{([^{}]*)\}")
_CSS_CURSOR = re.compile(r"cursor\s*:\s*(pointer|help|move|crosshair)\b")
_JS_CURSOR = re.compile(r"cursor['\"]?\s*:\s*['\"](pointer|help|move|crosshair)['\"]")
_PY_CURSOR = re.compile(r"['\"]cursor['\"]\s*:\s*['\"](pointer|help|move|crosshair)['\"]")


def _css_offenders():
    for path in app_asset_files(".css"):
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        for selector, body in _CSS_RULE.findall(text):
            for match in _CSS_CURSOR.finditer(body):
                if match.group(1) == "pointer" and ".link-like" in selector:
                    continue
                yield f"{path.name}: {selector.strip()} -> {match.group(0)}"


def test_stylesheets_keep_the_arrow():
    assert list(_css_offenders()) == []


def test_scripts_keep_the_arrow():
    offenders = [f"{path.name}: {m.group(0)}" for path in app_asset_files(".js")
                 for m in _JS_CURSOR.finditer(path.read_text(encoding="utf-8"))]
    assert offenders == []


def test_inline_styles_keep_the_arrow():
    offenders = [f"{path.relative_to(ROOT)}: {m.group(0)}"
                 for path in sorted((ROOT / "skilltree").rglob("*.py"))
                 for m in _PY_CURSOR.finditer(path.read_text(encoding="utf-8"))]
    assert offenders == []
