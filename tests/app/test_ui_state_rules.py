"""Each piece of UI state has one owner, and these rules keep it that way.

The feature review traced every bug able to lose typed work to state with more
than one owner: a sidebar's style, the editor's baseline, a message read as a
signal. Most of what makes those possible shows in the callback graph, so a
test can refuse it.

A limit here may only fall. When a change lowers a count, lower its limit.
"""
import re

from support.callback_graph import built_app, read_ids, writer_counts
from support.layout import walk
from support.paths import ROOT

# Outputs that two or more callbacks write.
MOST_SHARED_OUTPUTS = 126

# Callbacks allowed to write each output.
MOST_WRITERS = {
    'sidebar-editor-container.style': 8,
    'details-goal-sidebar.style': 8,
    'events-sidebar-container.style': 7,
    'editor-pristine-snapshot.data': 9,
}

# A message says something to a person. Code that reads one to learn what
# happened breaks when the wording changes.
MESSAGE_TEST = re.compile(
    r"""start(?:s|S)[Ww]ith\(\s*\(?\s*["'](?:Error|Settings saved|Updated node|Added node)""")
READS_MESSAGES = {
    'skilltree/engine/callbacks.py': 2,
    'skilltree/features/editor/callbacks.py': 1,
    'skilltree/features/editor/dormancy.py': 1,
    'skilltree/features/settings/callbacks.py': 1,
    'skilltree/features/settings/resources.py': 1,
    'skilltree/ui/components/context_picker.py': 1,
}

# Stores that exist to be written: a browser callback needed an Output.
SINKS = {'settings-close-sink', 'data-reload-sink', 'about-update-sink', 'welcome-reload-sink'}


def _sources():
    """Every Python and JavaScript file the app runs, but for vendored ones."""
    python = (ROOT / 'skilltree').rglob('*.py')
    scripts = (path for path in (ROOT / 'assets').rglob('*.js') if 'vendor' not in path.parts)
    for path in (*python, *scripts):
        yield path.relative_to(ROOT).as_posix(), path.read_text(encoding='utf-8')


def test_outputs_with_several_writers_only_fall():
    shared = sorted(output for output, count in writer_counts(built_app()).items() if count > 1)
    assert len(shared) <= MOST_SHARED_OUTPUTS, shared


def test_owned_outputs_have_no_new_writers():
    counts = writer_counts(built_app())
    assert {output: counts.get(output, 0) for output in MOST_WRITERS
            if counts.get(output, 0) > MOST_WRITERS[output]} == {}


def test_no_new_code_reads_a_message():
    found = {}
    for path, text in _sources():
        count = len(MESSAGE_TEST.findall(text))
        if count:
            found[path] = count
    assert found == READS_MESSAGES


def test_every_store_has_a_reader():
    app = built_app()
    layout = app.layout() if callable(app.layout) else app.layout
    stores = {node.id for node in walk(layout) if type(node).__name__ == 'Store'}
    read = read_ids(app)
    scripts = '\n'.join(text for path, text in _sources() if path.endswith('.js'))
    unread = {store for store in stores if store not in read and store not in scripts}
    assert unread == SINKS
