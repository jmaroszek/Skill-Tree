"""A multi-line text field that shows a new value in the same frame as the rest.

dbc.Textarea keeps its own copy of the value and copies a new one in from an
effect, after React has drawn it. So when a callback filled a form, the
description often arrived a frame after every other field. dcc.Textarea draws
the value it is given. It looks like any other field: ``form-control`` brings the
app's field styling, and fields.css undoes Dash's own textarea look
(``.dash-textarea``).
"""
from dash import dcc


def text_area(id, height, **kwargs):
    """A resizable text area ``height`` tall, starting empty."""
    return dcc.Textarea(id=id, value="", className="form-control",
                        style={"height": height, "resize": "vertical"}, **kwargs)
