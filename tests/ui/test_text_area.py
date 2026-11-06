"""The description boxes take a filled value in the same frame as the form.

dbc.Textarea copies a new value in after React has drawn it, so a load showed
the description a frame after the rest. ui/components/text_area.py draws the
value it is given.
"""
from dash import dcc

from skilltree.store.graph.manager import GraphManager
from support.layout import find


def _layout():
    from skilltree.shell import build_app_layout
    return build_app_layout(GraphManager(), env="sandbox")


def test_the_description_boxes_draw_the_value_they_are_given():
    layout = _layout()
    for box in ("node-desc", "event-description"):
        component = find(layout, box)
        assert isinstance(component, dcc.Textarea), box
        # The app's field look; fields.css undoes Dash's own.
        assert "form-control" in component.className.split()

