"""What the app tells the user after an action, and which kind of thing it is.

A notice is {"kind", "text", "ts"}, written to notice-store. A callback that
needs to know what happened reads a signal of its own: graph-version-store,
settings-version-store, editor-save-result-store. It never reads the words,
which are for the user and free to change.

assets/components/notices.js shows a notice: the line under the editor's Save,
and for an error the dialog too. The stamp makes a repeat a fresh value, so an
error that happens twice opens the dialog twice.
"""
import time


def _notice(kind, text):
    return {'kind': kind, 'text': text, 'ts': int(time.time() * 1000)}


def info(text):
    """Something that went as asked, or nearly: it only shows on the line."""
    return _notice('info', text)


def error(text):
    """Something that didn't go through: the dialog opens and says why."""
    return _notice('error', f"Error: {text}")
