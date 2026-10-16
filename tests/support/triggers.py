"""Pretend Dash fired a callback.

Callbacks read their trigger from Dash's callback context, through
ui.dash_tools or dash.ctx. fire() sets that context the way Dash would, so a
test needn't know which module a callback lives in or patch it. conftest
puts the context back after every test.
"""
from dash._callback_context import context_value
from dash._utils import AttributeDict


def fire(*ids, value=1):
    """Make the callbacks a test calls next see `ids` as what fired them.

    An id may name its prop ("store.data"); a bare id fires its n_clicks.
    fire() with no ids is the page-load call, when nothing fired.
    """
    triggered = [{"prop_id": i if "." in i else f"{i}.n_clicks", "value": value}
                 for i in ids]
    context_value.set(AttributeDict(triggered_inputs=triggered))
