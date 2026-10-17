"""Application update preferences in Settings > App.

The desktop shell persists the toggle through preload.js's bridge. Browsers
have no updater, so only the version number is shown there.
"""
from dash import Input, Output


def register_about_callbacks(app, services):
    app.clientside_callback(
        """function(activeTab) {
            const bridge = window.skillTreeDesktop && window.skillTreeDesktop.updates;
            if (activeTab !== 'tab-data' || !bridge) { return window.dash_clientside.no_update; }
            return {display: 'block'};
        }""",
        Output("about-updates", "style"),
        Input("settings-modal-tabs", "active_tab"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """async function(activeTab) {
            const bridge = window.skillTreeDesktop && window.skillTreeDesktop.updates;
            if (activeTab !== 'tab-data' || !bridge) { return window.dash_clientside.no_update; }
            return await bridge.getAutoCheck();
        }""",
        Output("about-update-auto", "value"),
        Input("settings-modal-tabs", "active_tab"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """async function(on) {
            const bridge = window.skillTreeDesktop && window.skillTreeDesktop.updates;
            if (bridge) { await bridge.setAutoCheck(!!on); }
            return window.dash_clientside.no_update;
        }""",
        Output("about-update-sink", "data"),
        Input("about-update-auto", "value"),
        prevent_initial_call=True,
    )
