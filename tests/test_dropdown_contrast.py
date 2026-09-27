"""Every dropdown's chosen value is readable.

A dcc.Dropdown draws a white field, and DARKLY's body text is white, so a
chosen value vanished unless something darkened it. The app's one idiom for
that is a `.text-dark` wrapper (assets/dropdowns.css). The Data tab's restore
dropdown shipped without one: picking a backup left the field looking empty.
"""
from dash import dcc

from layout import build_app_layout


def _dropdowns(component, ancestors=()):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _dropdowns(child, ancestors)
        return
    if not hasattr(component, "to_plotly_json"):
        return
    if isinstance(component, dcc.Dropdown):
        yield component, ancestors
    yield from _dropdowns(getattr(component, "children", None), ancestors + (component,))


def _is_dark(component):
    return "text-dark" in (getattr(component, "className", None) or "").split()


def test_every_dropdown_sits_in_a_text_dark_wrapper():
    found = list(_dropdowns(build_app_layout([], env="sandbox")))
    assert found, "the layout should have dropdowns"
    unreadable = [dropdown.id for dropdown, ancestors in found
                  if not any(_is_dark(a) for a in ancestors) and not _is_dark(dropdown)]
    assert unreadable == []
