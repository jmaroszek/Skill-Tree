"""The node editor taking in what changed outside it.

Three things write the editor's baseline, the snapshot that says what is unsaved:
loading a node, a save, and this. The server works out what moved (form.rebase).
The browser applies it, against the editor as it is when the answer lands.
"""
from dash import ClientsideFunction, Input, Output, State, no_update

from skilltree.features.editor.form import EDITOR_FORM, RELATIONSHIP_FIELDS, rebase, stored_relationships


# The form's values an answer is judged against, and the fields it can write,
# in the order the browser callback takes and returns them.
MERGE_READS = (*RELATIONSHIP_FIELDS, 'status_done', 'now')
MERGE_WRITES = {key: Output(EDITOR_FORM[key].component_id, EDITOR_FORM[key].component_property,
                            allow_duplicate=True)
                for key in MERGE_READS}


def register_merge_callbacks(app, services):
    manager = services.graph

    # Any mutation can change the open node from outside the editor, whose form
    # was filled when it loaded. The link menu, the Details tab and a bridge
    # change its links. The "Mark Done?" suggestion, the node menu, an event
    # putting it to sleep or a cascade change its Done or Now. Save judges the
    # same way (form.resolve_*), so it never depends on this having run. A changed
    # snapshot also checks again: after a save that merged in an outside change,
    # the snapshot holds the form's lists rather than what was stored.
    @app.callback(
        Output('editor-merge-store', 'data'),
        Input('graph-version-store', 'data'),
        Input('editor-pristine-snapshot', 'data'),
        [State('node-original-name', 'data'),
         {key: EDITOR_FORM[key] for key in MERGE_READS}],
        prevent_initial_call=True,
    )
    def merge_outside_changes(_version, snapshot, original_name, form):
        node = manager.get_node(original_name) if original_name else None
        if node is None or not isinstance(snapshot, dict) or snapshot.get('name') != original_name:
            return no_update
        groups = rebase(node, stored_relationships(manager.get_edges(), original_name),
                        form, snapshot)
        if not groups:
            return no_update
        return {'name': original_name, 'groups': groups,
                'reads': MERGE_READS, 'writes': list(MERGE_WRITES)}

    app.clientside_callback(
        ClientsideFunction(namespace='editor_form', function_name='apply_merge'),
        *MERGE_WRITES.values(),
        Output('editor-pristine-snapshot', 'data', allow_duplicate=True),
        Input('editor-merge-store', 'data'),
        State('node-original-name', 'data'),
        State('editor-pristine-snapshot', 'data'),
        *(EDITOR_FORM[key] for key in MERGE_READS),
        prevent_initial_call=True,
    )
