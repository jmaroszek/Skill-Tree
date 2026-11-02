"""The whole app's callback graph, for tests of who writes and hears what.

built_app() runs create_app once per worker, because the rules only read the
graph. Call it inside a test, never at import or in a module-scoped fixture:
those run before temp_database, so they would open the real sandbox database.
"""
import functools

import pytest

from skilltree import app as app_module


@functools.cache
def built_app():
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("WERKZEUG_RUN_MAIN", "true")
        return app_module.create_app(app_module.AppSettings(
            environment="sandbox", configure_logging=False))


def outputs_of(callback):
    """``component.prop`` for each thing ``callback`` writes. A browser callback
    with no Output has only a generated name, which has no prop."""
    raw = callback["output"]
    parts = raw.strip(".").split("...") if raw.startswith("..") else [raw]
    return {part.split("@")[0] for part in parts if "." in part}


def _writer(callback, position):
    """One browser function registered twice is one owner of what it writes."""
    function = callback.get("clientside_function")
    if function and function.get("namespace") != "_dashprivate_clientside_funcs":
        return function["namespace"], function["function_name"]
    return position


def writer_counts(app):
    """{output: how many callbacks write it}."""
    writers = {}
    for position, callback in enumerate(app._callback_list):
        for output in outputs_of(callback):
            writers.setdefault(output, set()).add(_writer(callback, position))
    return {output: len(found) for output, found in writers.items()}


def read_ids(app):
    """The plain ids any callback takes as an Input or State."""
    return {dep["id"] for callback in app._callback_list
            for dep in callback.get("inputs", []) + callback.get("state", [])
            if isinstance(dep.get("id"), str)}
