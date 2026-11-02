"""What the editor does when something asks it to show something else.

An intent says where the user asked to go, as a dict with a 'kind':

    tap, edit, picker   a node, under 'name'
    new                 a blank form: under a 'parent', or as a 'goal'
    bridge              a new node between the bridge dialog's two nodes
    background          an empty click on the canvas
    close               the editor's X, or its toolbar icon

next_step holds the whole rule, so a missing case can't hide in a branch.
populate_editor builds the intent, asks here, and carries out the answer. An
intent that has to ask waits in pending-navigation-store until the dialog is
answered. tests/features/editor/test_editor_navigation.py runs the table.
"""

LOAD = 'load'
ASK = 'ask'
KEEP = 'keep'
CLOSE = 'close'

# A canvas click isn't about a form out of sight behind another sidebar, so edits
# waiting there stay as they are. Everything else that would replace the form
# asks, and the editor opens to show what's at stake.
_LEAVES_A_HIDDEN_FORM_ALONE = ('tap', 'background')


def next_step(intent, editor_open, dirty, holds=False):
    """LOAD, ASK, KEEP or CLOSE for ``intent``.

    ``holds`` means the form already shows the node it asks for. Reloading that
    would drop the edits, so they stay, and nothing needs asking.
    """
    kind = intent['kind']
    if not dirty:
        return CLOSE if kind == 'close' else LOAD
    if holds or (not editor_open and kind in _LEAVES_A_HIDDEN_FORM_ALONE):
        return KEEP
    return ASK
