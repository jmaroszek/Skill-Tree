"""Finding components in a Dash layout, for tests that check one."""
from dash.development.base_component import Component


def walk(component):
    """Every component in ``component``'s tree, in document order, itself first."""
    stack = [component]
    while stack:
        node = stack.pop()
        if isinstance(node, (list, tuple)):
            stack.extend(reversed(node))
        elif isinstance(node, Component):
            yield node
            children = getattr(node, "children", None)
            if children is not None:
                stack.append(children)


def find(component, component_id):
    """The component with ``component_id`` in ``component``'s tree."""
    for node in walk(component):
        if getattr(node, "id", None) == component_id:
            return node
    raise AssertionError(f"{component_id!r} is not in the layout")
