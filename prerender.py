"""Run marked callbacks' initial calls on the server, into the layout.

When the page loads, Dash asks the server for every callback that isn't
prevent_initial_call, and each answer costs the browser far more than the
server. dash-renderer re-checks every mounted component on each store update,
and one callback makes about a dozen updates. Most of the startup cascade only
recomputed what the layout could already say: which trigger-type section to
show, the empty alias and link rows, a hint for the default trigger mode.

A callback marked @prerendered runs here instead, while the layout is built.
It is called exactly as Dash would call it on load, with the layout's own
input values and nothing triggered, and its outputs are written into the
layout. The callback is registered with prevent_initial_call=True, so the
browser never repeats it. Later input changes run it as before.

Only callbacks whose inputs are all in the initial layout qualify, with no
pattern-matching ids. A Store input is fine, even one whose data starts as
None: assets/store_mount.js keeps a mounting Store from reporting a change.
"""
import json
from contextvars import copy_context

from dash import no_update
from dash._callback_context import context_value
from dash._utils import AttributeDict
from dash.development.base_component import Component
from dash.exceptions import PreventUpdate

_MARK = '_skill_tree_prerendered'


def prerendered(func):
    """Mark a callback to run while the layout is built. Place it below
    @app.callback, and register the callback with prevent_initial_call=True."""
    setattr(func, _MARK, True)
    return func


def _is_marked(func):
    while func is not None:
        if getattr(func, _MARK, False):
            return True
        func = getattr(func, '__wrapped__', None)
    return False


def _key(component_id):
    if isinstance(component_id, dict):
        return json.dumps(component_id, sort_keys=True)
    return component_id


class _Spec:
    def __init__(self, key, entry):
        self.name = key
        self.multi = key.startswith('..')
        # Dash's registered wrapper expects its own request plumbing. The
        # function beneath it (with any of our own decorators) is what runs.
        self.func = entry['callback'].__wrapped__
        outputs = entry['output']
        if not isinstance(outputs, (list, tuple)):
            outputs = [outputs]
        self.outputs = [(_key(o.component_id), o.component_property)
                        for o in outputs]
        self.inputs = [(_key(i['id']), i['property']) for i in entry['inputs']]
        self.states = [(_key(s['id']), s['property']) for s in entry['state']]
        for component_id, _prop in self.outputs + self.inputs + self.states:
            if isinstance(component_id, str) and component_id.startswith('{'):
                raise ValueError(f"{self.name}: pattern-matching ids can't "
                                 "be prerendered")


def prerendered_specs(app):
    """The app's @prerendered callbacks, checked.

    Not cached: Dash calls the layout function once when it is assigned,
    before any callback is registered.
    """
    registered = {entry['output']: entry for entry in app._callback_list}
    specs = []
    for key, entry in app.callback_map.items():
        if not _is_marked(entry.get('callback')):
            continue
        if registered.get(key, {}).get('prevent_initial_call') is not True:
            raise RuntimeError(f"{key}: a prerendered callback must set "
                               "prevent_initial_call=True, or the browser "
                               "runs it again on load")
        specs.append(_Spec(key, entry))
    return specs


def _index(layout):
    """Components by id, found wherever a prop holds a component."""
    found = {}
    stack = [layout]
    while stack:
        value = stack.pop()
        if isinstance(value, Component):
            component_id = getattr(value, 'id', None)
            if component_id is not None:
                found[_key(component_id)] = value
            stack.extend(getattr(value, prop, None)
                         for prop in value._prop_names)
        elif isinstance(value, (list, tuple)):
            stack.extend(value)
    return found


def _in_order(specs):
    """Producers before consumers, so a chain settles as it would on load."""
    producers = {out: spec for spec in specs for out in spec.outputs}
    ordered, placed = [], set()

    def place(spec, visiting):
        if id(spec) in placed:
            return
        if id(spec) in visiting:
            raise ValueError(f"{spec.name}: prerendered callbacks form a cycle")
        visiting.add(id(spec))
        for dep in spec.inputs + spec.states:
            producer = producers.get(dep)
            if producer is not None and producer is not spec:
                place(producer, visiting)
        placed.add(id(spec))
        ordered.append(spec)

    for spec in specs:
        place(spec, set())
    return ordered


def _initial_call(spec, args):
    def call():
        # What Dash passes on a page-load call: nothing triggered.
        context_value.set(AttributeDict(triggered_inputs=[]))
        return spec.func(*args)
    return copy_context().run(call)


def prerender_layout(layout, app):
    """Write every @prerendered callback's initial outputs into ``layout``."""
    components = _index(layout)
    for spec in _in_order(prerendered_specs(app)):
        # Dash skips a callback whose inputs or outputs aren't on the page.
        if any(cid not in components for cid, _ in spec.inputs + spec.outputs):
            continue
        args = [getattr(components[cid], prop, None) if cid in components
                else None for cid, prop in spec.inputs + spec.states]
        try:
            result = _initial_call(spec, args)
        except PreventUpdate:
            continue
        values = result if spec.multi else [result]
        for (cid, prop), value in zip(spec.outputs, values):
            if value is not no_update:
                setattr(components[cid], prop, value)
    return layout
