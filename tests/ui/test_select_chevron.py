"""A native select's chevron: the paint worklet that draws it and the CSS that
turns it over have to agree on two names."""
from support.paths import asset_file


def test_the_stylesheet_paints_with_the_worklet_the_script_registers():
    script = asset_file("select_chevron.js").read_text(encoding="utf-8")
    css = asset_file("dropdowns.css").read_text(encoding="utf-8")
    assert "registerPaint('select-chevron'" in script
    assert "paint(select-chevron)" in css


def test_the_angle_is_registered_so_it_can_transition():
    script = asset_file("select_chevron.js").read_text(encoding="utf-8")
    css = asset_file("dropdowns.css").read_text(encoding="utf-8")
    assert "--select-chevron-turn" in script
    assert "@property --select-chevron-turn" in css
    assert "transition: --select-chevron-turn" in css
    assert "--select-chevron-turn: 180deg" in css
