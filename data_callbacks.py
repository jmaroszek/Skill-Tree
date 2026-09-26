"""The Settings > Data tab: backups, restore, export and import.

Each action runs at once rather than waiting for the Settings save, and
reports in the tab's status line. A restore or an import replaces the whole
graph, so it finishes by reloading the page, which then builds every view from
the new data.
"""
import base64
import json
import logging
from datetime import date

import dash
from dash import Input, Output, State, dcc, html, no_update

import backup
import data_transfer
from config import ConfigManager
from resource_links import open_path

logger = logging.getLogger(__name__)

_KIND_LABELS = {
    "daily": "daily",
    "manual": "made by hand",
    "pre-migration": "before an upgrade",
    "before-restore": "before a restore",
    "before-import": "before an import",
}


def backup_options():
    """The restore dropdown: newest first, labelled with time and kind."""
    options = []
    for info in reversed(backup.list_backups()):
        when = info["when"].strftime("%b %d, %Y  %H:%M")
        kind = _KIND_LABELS.get(info["kind"], info["kind"])
        options.append({"label": f"{when}  ({kind})", "value": str(info["path"])})
    return options


def _ok(text):
    return html.Span(text, className="text-success")


def _problem(text):
    return html.Span(text, className="text-danger")


def register_data_callbacks(app, services=None):
    # Fresh values each time the tab opens: backups appear while the app runs.
    @app.callback(
        Output("restore-backup-select", "options"),
        Output("setting-backup-extra-dir", "value"),
        Input("settings-modal-tabs", "active_tab"),
        prevent_initial_call=True,
    )
    def load_data_tab(active_tab):
        if active_tab != "tab-data":
            return no_update, no_update
        return backup_options(), ConfigManager.get_backup_extra_dir()

    @app.callback(
        Output("data-status", "children", allow_duplicate=True),
        Output("restore-backup-select", "options", allow_duplicate=True),
        Input("btn-backup-now", "n_clicks"),
        prevent_initial_call=True,
    )
    def back_up_now(n_clicks):
        if not n_clicks:
            return no_update, no_update
        try:
            path = backup.create_backup("manual")
            backup.mirror(path)
        except Exception:
            logger.exception("Manual backup failed")
            return _problem("The backup failed. The log has the details."), no_update
        return _ok(f"Backed up to {path.name}."), backup_options()

    @app.callback(
        Output("data-status", "children", allow_duplicate=True),
        Input("btn-open-backup-folder", "n_clicks"),
        prevent_initial_call=True,
    )
    def open_backup_folder(n_clicks):
        if not n_clicks:
            return no_update
        folder = backup.backup_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            open_path(str(folder))
        except Exception as exc:
            logger.warning("Could not open %s: %s", folder, exc)
            return _problem(f"Couldn't open the folder. It is {folder}.")
        return no_update

    @app.callback(
        Output("restore-confirm", "is_open"),
        Output("restore-confirm-text", "children"),
        Input("btn-restore-backup", "n_clicks"),
        Input("btn-restore-cancel", "n_clicks"),
        State("restore-backup-select", "value"),
        State("restore-backup-select", "options"),
        prevent_initial_call=True,
    )
    def confirm_restore(_restore, _cancel, selected, options):
        if dash.ctx.triggered_id != "btn-restore-backup" or not selected:
            return False, no_update
        label = next((o["label"] for o in options or [] if o["value"] == selected), selected)
        return True, (f"Replace your current graph with the backup from {label}? "
                      "Your current graph is backed up first.")

    @app.callback(
        Output("data-status", "children", allow_duplicate=True),
        Output("restore-confirm", "is_open", allow_duplicate=True),
        Output("data-reload-trigger", "data", allow_duplicate=True),
        Input("btn-restore-confirm", "n_clicks"),
        State("restore-backup-select", "value"),
        prevent_initial_call=True,
    )
    def restore(n_clicks, selected):
        if not n_clicks or not selected:
            return no_update, no_update, no_update
        try:
            data_transfer.restore_backup(selected)
        except data_transfer.TransferRefused as exc:
            return _problem(str(exc)), False, no_update
        return _ok("Restored. Reloading…"), False, n_clicks

    @app.callback(
        Output("download-export-json", "data"),
        Input("btn-export-json", "n_clicks"),
        prevent_initial_call=True,
    )
    def export_json(n_clicks):
        if not n_clicks:
            return no_update
        return dcc.send_string(data_transfer.export_json(),
                               f"skill-tree-export-{date.today().isoformat()}.json")

    @app.callback(
        Output("download-export-db", "data"),
        Input("btn-export-db", "n_clicks"),
        prevent_initial_call=True,
    )
    def export_database(n_clicks):
        if not n_clicks:
            return no_update
        return dcc.send_bytes(data_transfer.export_database_bytes(),
                              f"skill-tree-{date.today().isoformat()}.db")

    @app.callback(
        Output("data-status", "children", allow_duplicate=True),
        Output("data-reload-trigger", "data", allow_duplicate=True),
        Input("upload-import", "contents"),
        State("upload-import", "filename"),
        prevent_initial_call=True,
    )
    def import_export(contents, filename):
        if not contents:
            return no_update, no_update
        try:
            _header, _, payload = contents.partition(",")
            bundle = json.loads(base64.b64decode(payload))
        except (ValueError, UnicodeDecodeError):
            return _problem(f"{filename or 'That file'} isn't a Skill Tree export."), no_update
        try:
            counts = data_transfer.import_data(bundle)
        except data_transfer.TransferRefused as exc:
            return _problem(str(exc)), no_update
        return _ok(f"Imported {counts.get('Nodes', 0)} nodes. Reloading…"), filename or "import"

    # A restore or import replaced the graph under every open view.
    app.clientside_callback(
        """function(trigger) {
            if (trigger) { window.location.reload(); }
            return window.dash_clientside.no_update;
        }""",
        Output("data-reload-sink", "data"),
        Input("data-reload-trigger", "data"),
        prevent_initial_call=True,
    )
