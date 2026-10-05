"""The Settings > About tab: diagnostics, the report link, and the folder buttons.

The update switch and "Check now" belong to the desktop shell, not to this
server. Clientside callbacks below reach it through preload.js's bridge.
"""
import logging

from dash import Input, Output, html, no_update

import about
from app_paths import get_data_dir, get_log_dir
from resource_links import open_path

logger = logging.getLogger(__name__)


def register_about_callbacks(app, services=None):
    # Fresh each time the tab opens: counts and versions change while it runs.
    @app.callback(
        Output("about-diagnostics", "children"),
        Output("about-report-link", "href"),
        Input("settings-modal-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def load_about_tab(active_tab):
        if active_tab != "tab-about":
            return no_update, no_update
        text = about.diagnostics()
        return text, about.report_url(text)

    def _open(folder):
        try:
            folder.mkdir(parents=True, exist_ok=True)
            open_path(str(folder))
        except Exception as exc:
            logger.warning("Could not open %s: %s", folder, exc)
            return html.Span(f"Couldn't open the folder. It is {folder}.",
                             className="text-danger")
        return no_update

    @app.callback(
        Output("about-status", "children", allow_duplicate=True),
        Input("btn-open-data-folder", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_data_folder(n_clicks):
        return _open(get_data_dir()) if n_clicks else no_update

    @app.callback(
        Output("about-status", "children", allow_duplicate=True),
        Input("btn-open-log-folder", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_log_folder(n_clicks):
        return _open(get_log_dir()) if n_clicks else no_update

    @app.callback(
        Output("about-notices-status", "children"),
        Input("btn-open-notices", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_notices(n_clicks):
        path = about.notices_path()
        if not n_clicks or path is None:
            return no_update
        try:
            open_path(str(path))
        except Exception as exc:
            logger.warning("Could not open %s: %s", path, exc)
            return html.Span(f"Couldn't open them. They are in {path}.",
                             className="text-danger")
        return no_update

    # --- Updates: the desktop shell's, through preload.js's bridge. In a
    # browser there's no bridge and the block stays hidden. ---
    # Two callbacks, so the block appears with the tab instead of waiting on the
    # shell's answer for the switch.
    app.clientside_callback(
        """function(activeTab) {
            const bridge = window.skillTreeDesktop && window.skillTreeDesktop.updates;
            if (activeTab !== 'tab-about' || !bridge) { return window.dash_clientside.no_update; }
            return {display: 'block'};
        }""",
        Output("about-updates", "style"),
        Input("settings-modal-tabs", "active_tab"),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """async function(activeTab) {
            const bridge = window.skillTreeDesktop && window.skillTreeDesktop.updates;
            if (activeTab !== 'tab-about' || !bridge) { return window.dash_clientside.no_update; }
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

    app.clientside_callback(
        """async function(clicks) {
            const bridge = window.skillTreeDesktop && window.skillTreeDesktop.updates;
            const none = window.dash_clientside.no_update;
            if (!clicks || !bridge) { return [none, none, none]; }
            const found = await bridge.checkNow();
            return [found.message, found.url || '',
                    found.url ? {display: 'inline'} : {display: 'none'}];
        }""",
        Output("about-update-status", "children"),
        Output("about-update-link", "href"),
        Output("about-update-link", "style"),
        Input("btn-check-updates", "n_clicks"),
        prevent_initial_call=True,
    )
