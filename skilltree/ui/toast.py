"""Toasts that clear themselves a set time after their text last changed."""

from dash import Input


def register_toast_timer(app, component_id, ms):
    """Blank ``component_id``'s children ``ms`` after they were last set.

    The timer restarts on every change, so a message that follows another
    still stays its full time (see assets/components/toast_timer.js).
    """
    app.clientside_callback(
        "function(children) { window.dash_clientside.toast_timer.arm("
        f"'{component_id}', {int(ms)}, children); }}",
        Input(component_id, 'children'),
        prevent_initial_call=True,
    )
