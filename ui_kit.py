"""Small shared affordances: close, add, info, restore.

Each of these existed at a handful of call sites with slightly different
markup, sizing and accessibility. They are the kind of control that is too
small to feel worth a helper right up until the moment you notice the app has
five versions of it.

What was here before:

* **Close** — eight buttons, five style variants (``fs-3`` / ``fs-4`` /
  ``1.2rem``, ``#fff`` / ``#adb5bd``), split between ``html.Span`` and
  ``html.Button``, and written as both ``"×"`` and ``"\\u00d7"`` in the same
  codebase. The ``html.Span`` ones were not keyboard-reachable at all.
* **Add** — fourteen ``+`` buttons at three font sizes, ten of them with
  neither a tooltip nor a ``title``.
* **Info** — the same eight-key inline style dict at four call sites,
  differing only in ``"top": "0px"`` versus ``"3px"``.
* **Restore** — the ``↺`` glyph defined three separate times, once as a
  literal and once as an escape, with tooltip copy that read "Restore" in one
  place and "Restore defaults" in the other three.

STYLE_GUIDE.md already required one icon family at one weight and forbade
Unicode glyphs; these builders are what makes that enforceable rather than
aspirational.
"""
from dash import html
import dash_bootstrap_components as dbc

from config import (DEFAULT_NODE_COLORS, TOOLTIP_SHOW_DELAY_MS,
                    TOOLTIP_HIDE_DELAY_MS, ConfigManager)
from models import STATUS_DONE, STATUS_OPEN

_DELAY = {"show": TOOLTIP_SHOW_DELAY_MS, "hide": TOOLTIP_HIDE_DELAY_MS}


def _icon_button(button_id, icon, label, class_name, tooltip=None,
                 placement="top", **kwargs):
    """A ghost icon button with a visually-hidden label and optional tooltip.

    The label is always rendered for screen readers even when a tooltip is
    present, because a tooltip is a hover affordance and does not name the
    control for assistive technology.
    """
    button = dbc.Button(
        [
            html.I(className=f"bi bi-{icon}", **{"aria-hidden": "true"}),
            html.Span(label, className="visually-hidden"),
        ],
        id=button_id,
        color="link",
        className=class_name,
        **kwargs,
    )
    if tooltip is None:
        return button
    # A wrapper, NOT a bare list: Dash does not flatten nested lists inside
    # `children`, and React rejects them outright ("Objects are not valid as a
    # React child"), silently dropping the whole subtree. The Python-level
    # tests walk the component tree and cannot see that, so this is only
    # visible in a browser.
    #
    # `display: contents` on .ui-affordance keeps the wrapper out of layout, so
    # the button still behaves as a direct flex item of the row it sits in.
    return html.Span(
        [button, dbc.Tooltip(tooltip, target=button_id,
                             placement=placement, delay=_DELAY)],
        className="ui-affordance",
    )


def panel_close_button(button_id, label="Close", large=False,
                       className_extra="", **kwargs):
    """The X that dismisses a sidebar, panel or popup.

    A real ``<button>`` rather than a clickable ``html.Span``, so it is in the
    tab order and responds to Enter and Space. Existing wiring is unaffected:
    every call site drives these through ``n_clicks`` or a ``getElementById``
    click listener, both of which behave identically on a button.
    """
    classes = " ".join(filter(None, [
        "panel-close-btn",
        "panel-close-btn-lg" if large else "",
        className_extra,
    ]))
    return _icon_button(button_id, "x-lg", label, classes, **kwargs)


def add_button(button_id, tooltip, placement="right", large=False, **kwargs):
    """The ``+`` that reveals or appends a repeatable field.

    Per STYLE_GUIDE.md a ``+`` means *add a field* and a chevron means
    *disclose existing content*; do not substitute one for the other. ``large``
    is the sidebar-header variant.
    """
    size_class = "adder-btn-lg" if large else ""
    return _icon_button(
        button_id, "plus-lg", tooltip, f"adder-btn {size_class}".strip(),
        tooltip=tooltip, placement=placement, **kwargs)


def info_button(button_id, tooltip=None, placement="top", **kwargs):
    """The (i) that explains the control or section beside it.

    Pass ``tooltip=None`` when the caller supplies its own popover, which the
    ratings references do.
    """
    return _icon_button(button_id, "info-circle", tooltip or "More information",
                        "info-btn", tooltip=tooltip, placement=placement,
                        **kwargs)


def restore_button(button_id, tooltip="Restore defaults", placement="top",
                   **kwargs):
    """Reset a group of settings to their shipped values."""
    return _icon_button(button_id, "arrow-counterclockwise", tooltip,
                        "restore-btn", tooltip=tooltip, placement=placement,
                        **kwargs)


def nav_button(button_id, direction, tooltip, className_extra="", **kwargs):
    """Back/forward navigation. ``direction`` is ``"left"`` or ``"right"``.

    Keeps the existing ``.details-header-btn`` ghost treatment, which already
    styles its own disabled state; only the glyph changes from a Unicode arrow
    to the matching Bootstrap Icon.
    """
    classes = " ".join(filter(
        None, ["details-header-btn btn-secondary", className_extra]))
    return _icon_button(button_id, f"arrow-{direction}", tooltip, classes,
                        tooltip=tooltip, **kwargs)


def step_button(button_id, icon, tooltip, **kwargs):
    """A -/+ stepper beside a count, such as the Home tab's suggestion rows."""
    return _icon_button(button_id, icon, tooltip, "step-btn",
                        tooltip=tooltip, **kwargs)


def edit_button(button_id, tooltip="Edit", placement="top", className_extra="",
                **kwargs):
    """The pencil that opens an editor for the thing beside it.

    Matches the row-action pencils in Details subtasks, Reflection history and
    Events dormant nodes: one icon, a visually-hidden label and a dbc tooltip
    rather than a native ``title``, whose timing and styling match nothing
    else in the app.
    """
    classes = " ".join(filter(None, ["edit-btn", className_extra]))
    return _icon_button(button_id, "pencil", tooltip, classes,
                        tooltip=tooltip, placement=placement, **kwargs)


# --- Semantic action buttons ------------------------------------------------
# "Cancel" had four treatments across four modals, including one button that
# hand-painted #6c757d -- which is exactly `color="secondary"` -- and carried a
# tooltip describing a revert. "Save" was `primary` in two places, `success` in
# a third and an icon in a fourth. "Delete" inlined get_danger_color() at six
# sites although custom.css already restyles .btn-danger globally, and three of
# the six added their own padding on top.
#
# These name the ACTION, not the colour, so the mapping lives in one place and
# a reader of a call site sees intent rather than a Bootstrap variant.

def primary_action(label, button_id, **kwargs):
    """The button that commits the modal or form: Save, Apply, Confirm."""
    kwargs.setdefault("color", "primary")
    return dbc.Button(label, id=button_id, **kwargs)


def confirm_action(label, button_id, **kwargs):
    """A commit that also closes or completes: Save & Close, Trigger.

    Green is reserved for "this finishes the task", which is why it is a
    separate helper rather than a flag on primary_action.
    """
    kwargs.setdefault("color", "success")
    return dbc.Button(label, id=button_id, **kwargs)


def cancel_action(label, button_id, **kwargs):
    """Dismiss without committing. Always `secondary`, never hand-painted."""
    kwargs.setdefault("color", "secondary")
    return dbc.Button(label, id=button_id, **kwargs)


def danger_action(label, button_id, **kwargs):
    """Destructive: Delete, Discard.

    No inline background. `custom.css` already restyles `.btn-danger` to the
    tamed red app-wide, so repeating ConfigManager.get_danger_color() here only
    creates a second place for the value to drift.
    """
    kwargs.setdefault("color", "danger")
    return dbc.Button(label, id=button_id, **kwargs)


def done_color():
    """The user's canvas colour for Done.

    Three surfaces reached for this with their own inline fallback hex; a
    fallback repeated four times is a value that can drift from its default.
    """
    return ConfigManager.get_node_colors().get(
        STATUS_DONE, DEFAULT_NODE_COLORS[STATUS_DONE])


def progress_bar_color(pct):
    """Fill for a completion bar: the Done green at 100%, the accent below.

    Both the Home tab and the Details goal-progress bar computed this with
    their own literals.
    """
    from config import BADGE_PALETTE
    return (BADGE_PALETTE[STATUS_DONE][0] if pct == 100
            else BADGE_PALETTE[STATUS_OPEN][0])
