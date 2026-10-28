"""A dcc.Dropdown picked from the keyboard keeps what it was given.

Dash toggles a focused option on Enter's keyup. The keyboard script also
toggled checkboxes on Enter's keydown, so a multi-select option went on and
then straight off. And a menu opened near the window's bottom was capped to
the few pixels there, so Radix never flipped it above the field.
"""
from support.paths import asset_file


def test_enter_leaves_a_dropdown_option_to_dash():
    source = asset_file("keyboard_navigation.js").read_text(encoding="utf-8")
    assert 'input[type="checkbox"]:not(.dash-options-list-option-checkbox)' in source


def test_an_empty_search_menu_is_tall_enough_to_flip():
    css = asset_file("dropdowns.css").read_text(encoding="utf-8")
    assert ".dash-dropdown-content:has(.dash-dropdown-search:placeholder-shown)" in css
    assert "min-height: 190px" in css
