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

from skilltree.store import settings
from skilltree.store.settings import DEFAULT_NODE_COLORS
from skilltree.ui.styles import BADGE_PALETTE
from skilltree.ui.timing import TOOLTIP_HIDE_DELAY_MS
from skilltree.domain.models import STATUS_DONE, STATUS_OPEN
from skilltree.ui import tokens
from skilltree.ui.styles import badge_style

# The show delay is CSS (custom.css, Tooltips): the tooltip mounts at once and
# fades in late, so a press or a warm handoff can change the wait.
_DELAY = {"show": 0, "hide": TOOLTIP_HIDE_DELAY_MS}


def Tooltip(children, target, **kwargs):
    """The app's one tooltip: a ``dbc.Tooltip`` that opens on hover only.

    ``dbc.Tooltip`` defaults to ``trigger="hover focus"`` and opens on any
    ``focusin`` without asking whether the focus came from the keyboard. A modal
    hands focus back to whatever opened it when it closes, so the tooltip of the
    button you had just clicked popped open with the cursor nowhere near it, and
    stayed until you clicked elsewhere. Every tooltip goes through here so the
    trigger is decided in one place.

    Icon buttons still name themselves for assistive technology through their
    visually-hidden label, so nothing is lost by dropping the focus trigger.
    Keyboard focus never opens a tooltip: a field's hint reaches screen readers
    as its description instead (see ``hover_label``).
    ``trigger`` and ``delay`` can still be overridden per call.
    """
    kwargs.setdefault("trigger", "hover")
    kwargs.setdefault("delay", _DELAY)
    return dbc.Tooltip(children, target=target, **kwargs)


def hint(text, label=False):
    """Props that give an element the shared hover tip, instead of a ``title``.

    For small marks and row buttons that would each need a Tooltip component:
    assets/components/hover_tips.js shows ``data-hint`` with the app's tooltip
    timing and look. A native ``title`` keeps Chromium's own delay and look,
    and shows again after a click. ``label=True`` also names an icon-only
    button for screen readers, which the ``title`` used to do.
    """
    props = {"data-hint": text}
    if label:
        props["aria-label"] = text
    return props


def bullet_hint(intro, *items):
    """Tooltip body: a short intro line, then one bullet per item.

    Anything a tooltip enumerates is a bullet list, never a run-on sentence.
    """
    return html.Div([
        html.Div(intro, className="text-start"),
        html.Ul([html.Li(item) for item in items], className="ps-3 mb-0 text-start"),
    ])


def hover_label(text, label_id, hint, component=dbc.Label, placement="top", **kwargs):
    """A label or heading with its explainer on hover, in a ``display: contents`` wrapper.

    The tooltip targets the element itself, not an (i) button: the text only
    explains, and (i) is kept for controls that open a reference. ``label_id`` must be unique in the layout.
    Pass ``component=html.H5`` for a section heading. The ``hover-hint`` class
    fits a heading to its text, and keyboard navigation finds the label by it.
    """
    kwargs["className"] = f"{kwargs.get('className', '')} hover-hint".strip()
    hint_id = f"{label_id}-hint"
    return html.Div([
        component(text, id=label_id, **kwargs),
        Tooltip(hint, target=label_id, placement=placement),
        html.Span(_hint_text(hint), id=hint_id, className="visually-hidden"),
    ], className="keyboard-hint-label", style={"display": "contents"},
        **{"data-keyboard-hint": hint_id})


def _hint_text(value):
    """Plain text for a field's persistent accessible description."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_hint_text(child) for child in value)
    if hasattr(value, "children"):
        return _hint_text(value.children)
    return str(value)


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
        [button, Tooltip(tooltip, target=button_id, placement=placement)],
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


def add_button(button_id, tooltip, placement="right", large=False, label=None, **kwargs):
    """The ``+`` that reveals or appends a repeatable field.

    A plain text ``+``, which is the treatment the node editor already had and
    the one to match: lighter than an icon glyph, and it sits on the label's
    baseline without needing a box. This is the one affordance that is not a
    Bootstrap Icon, and deliberately so — the no-Unicode-glyph rule is about
    symbols like ``×`` and ``↺`` that have a real icon equivalent, not about a
    plus sign.

    A ``+`` means *add a field*; a chevron means *disclose existing content*.
    Do not substitute one for the other. ``large`` is the sidebar-header size.
    ``label`` names the button for screen readers when it has no tooltip;
    dbc.Button rejects ``aria-label``, so it goes in a visually-hidden span.
    """
    size_class = "adder-btn-lg" if large else ""
    children = ["+", html.Span(label or tooltip or "Add", className="visually-hidden")]
    button = dbc.Button(
        children,
        id=button_id,
        color="link",
        className=f"adder-btn {size_class}".strip(),
        **kwargs,
    )
    if tooltip is None:
        return button
    return html.Span(
        [button, Tooltip(tooltip, target=button_id, placement=placement)],
        className="ui-affordance",
    )


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


def filter_chip(prefix, className_extra=""):
    """The "Filtered" chip: which filters are narrowing this view, and a clear.

    Hidden until `ui.filters.filter_chip_state` marks it active. The
    callback fills ``{prefix}-text`` and the chip's data-hint and `hidden`; the
    clear button is ``{prefix}-clear``.
    """
    return html.Div([
        html.I(className="bi bi-funnel-fill", **{"aria-hidden": "true"}),
        html.Span(id=f"{prefix}-text", className="filter-chip-text"),
        html.Button(html.I(className="bi bi-x-lg", **{"aria-hidden": "true"}),
                    id=f"{prefix}-clear", n_clicks=0, type="button",
                    className="filter-chip-clear", **hint("Clear all filters", label=True)),
    ], id=prefix, className=" ".join(filter(None, ["filter-chip", className_extra])),
        role="status", hidden=True, **{"aria-label": "Filtered"})


def swap_button(button_id, tooltip, **kwargs):
    """Reverses a pair, such as the bridge dialog's Start and End. The only
    control beside the pair, so it is drawn in body text where a stepper is
    dim."""
    return _icon_button(button_id, "arrow-down-up", tooltip, "step-btn swap-btn",
                        tooltip=tooltip, **kwargs)


def disclosure_all_button(button_id, expand, **kwargs):
    """Expand all or Collapse all for a list of folding rows, such as the
    Analyze tab's Ratings by Context. Same quiet ghost as the stepper, so a
    pair sits in a card corner without competing with its title."""
    icon, label = (("arrows-expand", "Expand all") if expand
                   else ("arrows-collapse", "Collapse all"))
    return _icon_button(button_id, icon, label, "step-btn disclosure-btn",
                        tooltip=label, **kwargs)


def guide_toggle_button(button_id, label="Show the mean of all nodes", **kwargs):
    """Toggles a chart's reference line, such as the dashed mean of all nodes in
    Ratings by Context. dbc.Button rejects ``aria-*`` props, so the script
    that owns the toggle sets ``aria-pressed``; the pressed style keys off
    the root class it maintains."""
    return _icon_button(button_id, "align-center", label,
                        "step-btn guide-toggle-btn", tooltip=label, **kwargs)


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


def split_handle(handle_id, axis, min_size):
    """The bar you drag to resize the two panels on either side of it.

    It resizes its previous and next siblings, so it goes between them.
    ``axis`` is ``"cols"`` for panels side by side and ``"rows"`` for stacked
    ones. A drag leaves each panel at least ``min_size`` pixels.
    ``assets/components/split_handles.js`` does the dragging for every handle, and the
    ``.split-handle`` rules in ``theme.css`` draw it.
    """
    return html.Div(id=handle_id, className=f"split-handle split-handle-{axis}",
                    role="separator", tabIndex=0,
                    **{"data-min-size": str(min_size),
                       "aria-label": "Resize panels",
                       "aria-orientation": "vertical" if axis == "cols" else "horizontal"})


# --- Semantic action buttons ------------------------------------------------
# "Cancel" had four treatments across four modals, including one button that
# hand-painted #6c757d -- which is exactly `color="secondary"` -- and carried a
# tooltip describing a revert. "Save" was `primary` in two places, `success` in
# a third and an icon in a fourth. "Delete" inlined a danger colour at six
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
    tamed red app-wide, so repeating the colour here only
    creates a second place for the value to drift.
    """
    kwargs.setdefault("color", "danger")
    return dbc.Button(label, id=button_id, **kwargs)


def done_color():
    """The user's canvas colour for Done.

    Three surfaces reached for this with their own inline fallback hex; a
    fallback repeated four times is a value that can drift from its default.
    """
    return settings.NODE_COLORS.get().get(
        STATUS_DONE, DEFAULT_NODE_COLORS[STATUS_DONE])


def node_type_color(node_type):
    """The user's canvas colour for a node type, for a dot beside its name."""
    return settings.NODE_COLORS.get().get(
        node_type, DEFAULT_NODE_COLORS.get(node_type, "#6c757d"))  # literal: unknown type


def progress_bar_color(pct):
    """Fill for a completion bar: the Done green at 100%, the accent below.

    Both the Home tab and the Details goal-progress bar computed this with
    their own literals.
    """
    return (BADGE_PALETTE[STATUS_DONE][0] if pct == 100
            else BADGE_PALETTE[STATUS_OPEN][0])


def goal_corner_badge(text, palette_name, class_name="badge"):
    """The fixed-width badge in a goal card's corner: a priority rank or score.

    The Goals sidebar and the Details suggestions share it, so the same number
    looks the same on both.
    """
    return html.Span(text, className=class_name, style={
        **badge_style(palette_name, font_size=tokens.FS_XS),
        "minWidth": "34px", "textAlign": "center", "display": "inline-block",
    })
