"""Every dropdown's chosen value is readable.

A dcc.Dropdown draws a dark field in assets/css/fields.css, and its value takes
the field's light text from there. A `.text-dark` wrapper's `!important` would
beat that and leave a dark value in a dark field, so none may remain.
"""
from dash import dcc

from skilltree.shell import build_app_layout
from skilltree.store.graph.manager import GraphManager


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


def test_no_dropdown_sits_in_a_text_dark_wrapper():
    found = list(_dropdowns(build_app_layout(GraphManager(), env="sandbox")))
    assert found, "the layout should have dropdowns"
    unreadable = [dropdown.id for dropdown, ancestors in found
                  if any(_is_dark(a) for a in ancestors) or _is_dark(dropdown)]
    assert unreadable == []
