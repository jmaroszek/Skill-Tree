"""Each piece of UI state has one owner, and these rules keep it that way.

The feature review traced every bug able to lose typed work to state with more
than one owner: a sidebar's style, the editor's baseline, a message read as a
signal. Most of what makes those possible shows in the callback graph, so a
test can refuse it.

A limit here may only fall. When a change lowers a count, lower its limit.
"""
import re

from skilltree.engine.handlers import HANDLERS
from skilltree.features.editor.view import VIEW_OUTPUTS
from support.callback_graph import built_app, read_ids, writer_counts
from support.callbacks import unwrapped
from support.layout import walk
from support.paths import ROOT

# Outputs that two or more callbacks write. Up from 121 once: the Dormant section's
# 8 widgets became form fields like any other, which a load fills and the merge
# follows, and that took 6 writers off the baseline.
MOST_SHARED_OUTPUTS = 129

# What a node load sends with the editor's values, which a callback also keeps
# in step with the user's edits (features/editor/view.py). Both writers answer
# from one rule, and tests/features/editor/test_editor_view.py checks the
# browser's copy against the Python twin, so they can't disagree the way two
# owners of a store can. They're counted apart, with a limit of their own.
LOAD_TWINS = {f'{component}.{prop}' for component, prop in VIEW_OUTPUTS.values()}
MOST_LOAD_TWINS = 33

# Callbacks allowed to write each output.
MOST_WRITERS = {
    # left_panel.js draws the left sidebars and owns the store they follow.
    'left-panel-store.data': 1,
    'sidebar-editor-container.className': 1,
    'details-goal-sidebar.className': 1,
    'events-sidebar-container.className': 1,
    'sidebar-filters-container.className': 1,
    'editor-pristine-snapshot.data': 3,
    # Everything else writes a notice, and notices.js shows it.
    'save-output.children': 1,
    'modal-error.is_open': 1,
    # populate_editor decides what the editor does next.
    'pending-navigation-store.data': 1,
    'modal-unsaved-changes.is_open': 1,
    # The two places a Settings save commits.
    'settings-version-store.data': 2,
}

# A message says something to a person. Code that reads one to learn what
# happened breaks when the wording changes.
MESSAGE_TEST = re.compile(
    r"""start(?:s|S)[Ww]ith\(\s*\(?\s*["'](?:Error|Settings saved|Updated node|Added node)""")

# Stores that exist to be written: a browser callback needed an Output.
SINKS = {'theme-preview-sink', 'theme-reload-sink', 'settings-close-sink', 'data-reload-sink', 'about-update-sink', 'welcome-reload-sink'}


def _sources():
    """Every Python and JavaScript file the app runs, but for vendored ones."""
    python = (ROOT / 'skilltree').rglob('*.py')
    scripts = (path for path in (ROOT / 'assets').rglob('*.js') if 'vendor' not in path.parts)
    for path in (*python, *scripts):
        yield path.relative_to(ROOT).as_posix(), path.read_text(encoding='utf-8')


def test_outputs_with_several_writers_only_fall():
    shared = sorted(output for output, count in writer_counts(built_app()).items()
                    if count > 1 and output not in LOAD_TWINS)
    assert len(shared) <= MOST_SHARED_OUTPUTS, (len(shared), shared)


def test_load_twins_only_fall():
    twins = sorted(output for output, count in writer_counts(built_app()).items()
                   if count > 1 and output in LOAD_TWINS)
    assert len(twins) <= MOST_LOAD_TWINS, (len(twins), twins)


def test_owned_outputs_have_no_new_writers():
    counts = writer_counts(built_app())
    assert {output: counts.get(output, 0) for output in MOST_WRITERS
            if counts.get(output, 0) > MOST_WRITERS[output]} == {}


def test_a_sidebars_style_belongs_to_no_callback():
    counts = writer_counts(built_app())
    assert [sidebar for sidebar in ('sidebar-editor-container', 'details-goal-sidebar',
                                    'events-sidebar-container', 'sidebar-filters-container')
            if f'{sidebar}.style' in counts] == []


def test_how_a_sidebar_slides_is_only_in_css():
    # content_room.js slides the tab content, not a sidebar.
    assert [path for path, text in _sources() if 'translateX' in text
            and path != 'assets/sidebars/content_room.js'] == []


def test_the_unsaved_check_has_two_callers():
    """populate_editor, for what the editor does next, and an empty form's Save."""
    callers = sorted(path for path, text in _sources()
                     if 'is_form_dirty_vs_snapshot(' in text and path.endswith('.py')
                     and 'def is_form_dirty_vs_snapshot' not in text)
    assert callers == ['skilltree/engine/handlers.py', 'skilltree/features/editor/callbacks.py']


def test_where_the_editor_is_going_is_a_dict_not_a_string():
    sentinels = re.compile(r"__(?:background|bridge|new_goal|new_node|new_subtask)__")
    assert [path for path, text in _sources() if sentinels.search(text)] == []


def test_a_render_can_never_replace_what_changes_the_graph():
    """Dash throws away a callback's answer if it fires again first, though the
    run still finishes on the server. So what commits has a callback to itself."""
    app = built_app()
    doors = [callback for callback in app._callback_list
             if callback["output"] in app.callback_map
             and "callback" in app.callback_map[callback["output"]]
             and unwrapped(app.callback_map[callback["output"]]["callback"]).__name__
             == "core_engine"]
    assert len(doors) == 2
    ids = [{dep["id"] for dep in door["inputs"]} for door in doors]
    actions = set(HANDLERS) | {"btn-editor-reopen-confirm"}
    assert actions in ids
    assert not (ids[0] & ids[1])


def test_no_code_reads_a_message():
    assert [path for path, text in _sources() if MESSAGE_TEST.search(text)] == []


def test_every_store_has_a_reader():
    app = built_app()
    layout = app.layout() if callable(app.layout) else app.layout
    stores = {node.id for node in walk(layout) if type(node).__name__ == 'Store'}
    read = read_ids(app)
    scripts = '\n'.join(text for path, text in _sources() if path.endswith('.js'))
    unread = {store for store in stores if store not in read and store not in scripts}
    assert unread == SINKS
