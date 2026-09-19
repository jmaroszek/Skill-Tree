"""UI contracts shared by every surface that creates or edits a node."""

import pytest
from dash.development.base_component import Component


def _walk(component, parent=None):
    if component is None:
        return
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child, parent)
        return
    if not isinstance(component, Component):
        return
    yield component, parent
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            yield from _walk(child, component)
    elif children is not None:
        yield from _walk(children, component)


def _find(component, component_id):
    for child, parent in _walk(component):
        if getattr(child, "id", None) == component_id:
            return child, parent
    raise AssertionError(f"{component_id!r} is missing from the layout")


def _parent_of(root, target):
    for child, parent in _walk(root):
        if child is target:
            return parent
    return None


def _row_children(row):
    """A row's children, flattened through any `display: contents` wrapper."""
    out = []
    for child in getattr(row, "children", None) or []:
        if (getattr(child, "className", "") or "") == "ui-affordance":
            out.extend(getattr(child, "children", None) or [])
        else:
            out.append(child)
    return out


def _ids(component):
    return {
        getattr(child, "id", None)
        for child, _parent in _walk(component)
        if getattr(child, "id", None) is not None
    }


def _text(component):
    children = getattr(component, "children", None)
    return children if isinstance(children, str) else None


def _editor_surfaces():
    from details_layout import build_details_tab_content
    from events_layout import build_events_tab_content
    from sidebars_layout import node_editor_content

    return (
        (node_editor_content, "node-name", "btn-alias-add", "aliases-label"),
        (build_details_tab_content(), "details-add-name",
         "btn-details-add-alias-add", "details-add-aliases-label"),
        (build_events_tab_content(), "dormant-node-name",
         "btn-dormant-alias-add", "dormant-aliases-label"),
    )


@pytest.mark.parametrize("surface_index", range(3))
def test_alias_add_button_sits_beside_name_label(surface_index):
    surface, name_id, add_id, aliases_label_id = _editor_surfaces()[surface_index]
    button, button_parent = _find(surface, add_id)
    _name_input, input_parent = _find(surface, name_id)
    aliases_label, _label_parent = _find(surface, aliases_label_id)

    # A plain text "+", which is the treatment the node editor always had and
    # the one ui_kit.add_button standardised on. It is the one affordance that
    # is not a Bootstrap Icon, deliberately: the no-Unicode-glyph rule is about
    # symbols like "x" and the restore arrow that have a real icon equivalent.
    assert button.children == "+"
    assert "adder-btn" in button.className
    assert button_parent is not None

    # Its tooltip is a sibling inside the same wrapper, so the label is still
    # reachable without hovering blind.
    tooltip = next(c for c in button_parent.children
                   if getattr(c, "target", None) == add_id)
    assert tooltip.children == "Add alias"

    # ui_kit wraps the button with its tooltip in a `display: contents` span,
    # so the row that owns the label is one level above that wrapper. The
    # contract is unchanged: the "+" sits in the same row as "Name".
    row = button_parent
    if (getattr(row, "className", "") or "") == "ui-affordance":
        row = _parent_of(surface, row)
    assert "Name" in {
        _text(child)
        for child in _row_children(row)
        if isinstance(child, Component)
    }
    assert "editor-field-group" not in (getattr(input_parent, "className", "") or "")
    assert aliases_label.children == "Alias"


def test_alias_disclosure_chevrons_are_gone_from_every_node_editor():
    removed_ids = {
        "btn-aliases-toggle",
        "aliases-chevron",
        "btn-details-add-aliases-toggle",
        "details-add-aliases-chevron",
        "btn-dormant-aliases-toggle",
        "dormant-aliases-chevron",
    }
    for surface, _name_id, _add_id, _aliases_label_id in _editor_surfaces():
        assert removed_ids.isdisjoint(_ids(surface))


def test_dormant_node_type_starts_unselected_like_main_node_editor():
    from events_layout import build_events_tab_content
    from sidebars_layout import node_editor_content

    main_type, _main_parent = _find(node_editor_content, "node-type")
    dormant_type, _dormant_parent = _find(
        build_events_tab_content(), "dormant-node-type"
    )

    assert main_type.placeholder == dormant_type.placeholder == "Choose node type..."
    assert not hasattr(dormant_type, "value")


def test_resources_heading_is_short_and_consistent_in_every_node_editor():
    for surface, _name_id, _add_id, _aliases_label_id in _editor_surfaces():
        visible_text = {
            text
            for child, _parent in _walk(surface)
            if (text := _text(child)) is not None
        }
        assert "Resources" in visible_text
        assert "External Resources" not in visible_text
