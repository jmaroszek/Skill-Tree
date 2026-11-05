"""A tree of html.* components sent as one component holding its description.

Every update to Dash's store re-checks every mounted component, wherever it is
and whether or not it is showing, so a hidden tab's rows slow a click on any
other tab (docs/performance.md). Rows that no callback reads or writes don't
need to be components. inert_rows() mounts them as one, and
assets/analyze/rating_dist.js builds their elements inside it, where Dash and
React never look. The browser's own behaviour, such as a <details> folding, and
any delegated listener work on the result as on any other element.

The description is JSON rather than HTML, so a node's name stays text: the script
makes elements and text nodes from it and never parses markup.
"""
import json
import re

from dash import html

_ATTRIBUTE_NAMES = {'className': 'class', 'tabIndex': 'tabindex'}


def inert_rows(children, class_name):
    """One html.Div standing for ``children``, whatever their number."""
    return html.Div(className=class_name,
                    **{'data-tree': json.dumps(to_tree(children), separators=(',', ':'))})


def to_tree(node):
    """A list of what ``node`` holds: a string for text, and [tag, attributes,
    children] for an element. Only html.* components: anything else behaves
    through Dash, which this takes it away from."""
    if node is None:
        return []
    if isinstance(node, (list, tuple)):
        return [item for child in node for item in to_tree(child)]
    if isinstance(node, (str, int, float)):
        return [str(node)]
    if getattr(node, '_namespace', None) != 'dash_html_components':
        raise TypeError(f"{type(node).__name__} can't be inert: only html.* components can")
    props = dict(node.to_plotly_json()['props'])
    children = props.pop('children', None)
    attributes = {_ATTRIBUTE_NAMES.get(name, name): _attribute_value(name, value)
                  for name, value in props.items() if value is not None}
    return [[type(node).__name__.lower(), attributes, to_tree(children)]]


def _attribute_value(name, value):
    if name == 'style':
        return ';'.join(f"{_css_name(k)}:{v}" for k, v in value.items())
    return str(value)


def _css_name(name):
    if name.startswith('--'):
        return name
    return re.sub(r'[A-Z]', lambda m: f"-{m.group(0).lower()}", name)
