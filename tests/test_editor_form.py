"""The node editor's form is declared once (callback_helpers.EDITOR_FORM).

Four callbacks read the whole form: core_engine saves it, and populate_editor,
toggle_unsaved_modal and sync_original_name_after_save compare it with its
pristine snapshot. Each used to list its ~33 fields itself, by position, so a
new field meant four matching edits, and a slip passed one field's value in
another's place. Now each takes the form as one grouped State, a dict keyed
by field.
"""
import inspect

import dash

import callbacks
from callback_helpers import EDITOR_FORM, editor_form_values, editor_form_values_from

READERS = ("core_engine", "populate_editor", "toggle_unsaved_modal",
           "sync_original_name_after_save")


def _registered_specs():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    callbacks.register_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found[getattr(fn, "__name__", None)] = (spec, fn)
    return found


def test_each_reader_takes_the_whole_form_as_one_group():
    specs = _registered_specs()
    form = [state.to_dict() for state in EDITOR_FORM.values()]
    for name in READERS:
        spec, fn = specs[name]
        states = spec["state"]
        starts = [i for i in range(len(states) - len(form) + 1)
                  if states[i:i + len(form)] == form]
        assert starts, f"{name} doesn't take EDITOR_FORM whole"
        # ...and receives it as the one `form` parameter, not field by field.
        params = inspect.signature(fn).parameters
        assert "form" in params and not set(params) & set(EDITOR_FORM), name


def test_the_form_holds_every_field_the_unsaved_check_compares():
    compared = set(inspect.signature(editor_form_values).parameters)
    declared = set(EDITOR_FORM) - {"link_values", "link_ids"} | {"resource_links"}
    assert declared == compared


def test_a_missing_form_reads_as_empty_fields():
    empty = editor_form_values_from(None)
    assert empty == editor_form_values_from({})
    assert empty["name"] is None and empty["resource_links"] == {}


def test_links_arrive_joined_by_section():
    values = editor_form_values_from({
        "link_values": ["b.pdf", "https://a.example"],
        "link_ids": [{"type": "resource-link", "index": "files:0"},
                     {"type": "resource-link", "index": "web:0"}],
    })
    assert values["resource_links"] == {"files": ["b.pdf"], "web": ["https://a.example"]}
