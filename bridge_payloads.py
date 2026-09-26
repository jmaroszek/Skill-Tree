"""Values the browser writes into hidden Dash inputs, and how to read them.

The JS bridges (assets/menus.js, context_menu.js and the rest) write a value
into a hidden input and append ``'|' + Date.now()``, so that sending the same
value twice still changes the input and fires its callback. Some senders put
a field before the stamp (``name|rank|<ms>``), and a JSON list of names can
carry two stamps (``["a","b"]|<ms>|<ms>``).

Node and event names are free text and may contain ``|`` themselves. Splitting
on the first ``|`` cut such a name short, and the action then landed on
whichever node the prefix happened to name. So read from the right: the stamp
and every extra field are free of ``|``, and only the first field can hold one.

Pure functions only: core modules such as node_commands use this, and must not
depend on the Dash UI layer.
"""
import json


def strip_stamp(value):
    """``value`` without its trailing ``|<ms>`` stamp, if it has one."""
    if not isinstance(value, str):
        return ""
    head, sep, tail = value.rpartition("|")
    return head if sep and tail.isdigit() else value


def fields(value, count):
    """A stamped payload split into ``count`` fields, the first free text.

    ``fields("Goal|A|2|1700000000000", 2)`` is ``["Goal|A", "2"]``. None when
    the payload holds fewer fields.
    """
    parts = strip_stamp(value).rsplit("|", count - 1)
    return parts if len(parts) == count else None


def names(value):
    """The node names in a stamped payload: a JSON list, or one bare name.

    The JSON list is read up to its closing bracket, so any stamps after it are
    ignored whatever they hold.
    """
    if not isinstance(value, str) or not value:
        return []
    try:
        parsed, _end = json.JSONDecoder().raw_decode(value)
    except ValueError:
        parsed = None
    if isinstance(parsed, list):
        return [name for name in parsed if isinstance(name, str) and name]
    name = strip_stamp(value)
    return [name] if name else []


def edge_key(source, target, edge_type):
    """A string key for one edge that survives a dcc.Store round trip."""
    return json.dumps([source, target, edge_type])


def parse_edge_key(key):
    """The ``(source, target, type)`` an ``edge_key`` encodes, or None."""
    try:
        parts = json.loads(key)
    except (TypeError, ValueError):
        return None
    if (isinstance(parts, list) and len(parts) == 3
            and all(isinstance(part, str) for part in parts)):
        return tuple(parts)
    return None
