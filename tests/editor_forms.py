"""A node editor form, for tests that call the editor's callbacks directly.

The callbacks take the form as one dict (callback_helpers.EDITOR_FORM), which
Dash builds from the editor's fields. editor_form() builds one with every
field empty except those given, and call() calls a callback the way Dash
would. Both refuse a name that is neither a form field nor a parameter, so a
test can't set something nothing reads.
"""
import inspect

from callback_helpers import EDITOR_FORM


def editor_form(**fields):
    unknown = sorted(set(fields) - set(EDITOR_FORM))
    assert not unknown, f"not a node editor field: {unknown}"
    return {key: fields.get(key) for key in EDITOR_FORM}


def call(fn, **values):
    """Call an editor callback by parameter name, every other one None.

    A value named for an EDITOR_FORM field goes into the ``form`` dict the
    callback takes; any other names one of the callback's own parameters.
    """
    params = inspect.signature(fn).parameters
    form = {key: values.pop(key) for key in list(values) if key in EDITOR_FORM}
    unknown = sorted(set(values) - set(params))
    assert not unknown, f"not a parameter of {fn.__name__}: {unknown}"
    kwargs = dict.fromkeys(params)
    kwargs.update(values)
    kwargs["form"] = editor_form(**form)
    return fn(**kwargs)
