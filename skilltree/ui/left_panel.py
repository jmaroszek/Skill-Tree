"""The server's one say over the left sidebars (engine.sidebars)."""
import time


def close_editor():
    """The request that closes the editor, if it's still what's open. The stamp
    makes a repeat a new value."""
    return {'close': 'editor', 'ts': int(time.time() * 1000)}
