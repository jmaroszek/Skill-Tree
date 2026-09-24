# Skill Tree Style Guide

How this app's UI is put together, and why. **Values live in code, not here.**

For years this file named tokens — `bg-card`, `text-primary`, `border-panel` —
that existed nowhere in the codebase, so every call site hand-typed the hex.
That is how the app ended up with 361 colour literals, 28 distinct font sizes,
and one table drawing its Type column in a different grey from the Delay and
Status columns beside it. The names are real now:

| Layer | Where | What it holds |
|-------|-------|---------------|
| CSS | [`assets/tokens.css`](assets/tokens.css) | every colour, size, radius, shadow and motion value, as `--st-*` custom properties on `:root` |
| Python | [`style_tokens.py`](style_tokens.py) | `var(--st-*)` **references**, never copies, plus shared composites like `CELL_MUTED` and `TABLE_STYLE` |
| Badges | [`config.py`](config.py) `BADGE_PALETTE` | node type, status, edge and event tiles — user-adjacent, reached through `badge_style()` |
| Components | [`ui_kit.py`](ui_kit.py) | close, add, info, restore, edit, nav, step, and the semantic action buttons |

Read `assets/tokens.css` for the values. It is commented, and it is the only
place any of them appear.

**Two rules that keep it working:**

1. **Tokens are named by role, never by appearance** — `--st-field-bg`, not
   `--st-gray-100`. The app's form layer is light (DARKLY renders
   `.form-control` white) while its chrome is dark. If those are ever unified,
   that should be a value edit in one file rather than another sweep.
2. **Python holds references, not copies.** Dash passes `var()` straight to the
   DOM, so an inline style dict and a stylesheet rule resolve to the same
   definition. This works in clientside-callback JavaScript too.

### Enforcement

[`tests/test_style_tokens.py`](tests/test_style_tokens.py) fails on a new raw
colour or font size in a UI module, on a token defined in only one of the two
languages, on a badge value this guide documents that `BADGE_PALETTE` disagrees
with, and on the component shapes that silently render as nothing. A genuine
exception — Plotly and Cytoscape read computed values and cannot resolve
`var()` — is marked at the call site with a trailing `# literal:` comment
naming the reason, so it stays visible rather than hiding in a list.

## Theme

Bootstrap DARKLY (Bootswatch 5.3.6) via `dash-bootstrap-components`.

### The one naming trap

Bootstrap has a `.text-muted` class. This guide used to define a *token* called
`text-muted` as `#6c757d`. They are not the same colour: under DARKLY the class
resolves to `var(--bs-secondary-color)`, i.e. `rgba(255,255,255,.75)`. The app
used both believing they were interchangeable, which is exactly why adjacent
cells of one table disagreed.

`--st-text-secondary` is now pinned to what the class actually computes to, so
the token and the class *are* interchangeable. Prefer the class in component
code; use `tokens.TEXT_SECONDARY` where only an inline dict will do. A test
holds them together.

`--st-text-dim` (`#6c757d`) still exists for things that really are dimmer than
body text — rest-state icon strokes, captions, disabled affordances. It is not
a synonym for muted body text.

### Node-info badge palette (muted)

The Next-tab priority bars, Node Editor priority strip, Details info
pane, and subtasks-table tiles all share a single palette
(`config.BADGE_PALETTE`, accessed via `config.badge_style(name)` for
badges or read directly for the Next-tab bar fills). The palette is
**deliberately decoupled from Settings → Type Colors** — the canvas
needs vivid hues to keep the network readable; the bars/badges need the
same hue identity at a quieter register, and frozen literals here are
the single source of truth so future-you doesn't have to remember any
derivation. **This file is the human-readable source of truth — keep
`config.BADGE_PALETTE` and the documentation here in sync.**

| Tile         | Background | Text      | Notes                                                     |
|--------------|-----------|-----------|-----------------------------------------------------------|
| Unblocking   | `#c516a5` | `#ffffff` | A step pinned toward a blocked Now node. Bar color only — it has no badge tile. |
| Goal         | `#cdbe23` | `#ffffff` | Type tile. Canvas Goal color with −5 sat (intentional exception to the default −20 muting — yellow goes olive when pushed further). Suppressed when a `Priority N` tile is shown. |
| Priority     | `#cdbe23` | `#ffffff` | `Priority N` for priority Goals. Same hue as Goal.        |
| PriorityRank | `#f39c12` | `#ffffff` | The bare rank number on Goals-sidebar cards and Details suggestions. Darkly's warning orange, deliberately warmer than the Goal yellow. |
| Action       | `#bb6823` | `#ffffff` | Type tile. More desaturated than the default — orange holds saturation visually. |
| Learn        | `#1d5cba` | `#ffffff` | Type tile.                                                |
| Resource     | `#814d9e` | `#ffffff` | Type tile. Less desaturated than the default — purple turns muddy if pushed too far. |
| Milestone    | `#2f909d` | `#ffffff` | Type tile.                                                |
| Open         | `#3e61a0` | `#ffffff` | Status tile — solid blue.                                 |
| Done         | `#148a68` | `#ffffff` | Status tile.                                              |
| Blocked      | `#9e3838` | `#ffffff` | Status tile.                                              |
| HardRelPri   | `#2a4d6e` | `#d6e0ee` | `Hard N` for non-Goal nodes in a priority Goal subtree. Darker rugged blue — matches subtasks-table Hard. |
| SoftRelPri   | `#414f5c` | `#d0d6dc` | `Soft #N`. A darker slate than the `EdgeSoft` tile, despite what this row used to claim. |

The type-color values were originally derived by HSL-desaturating the
saturated canvas palette by per-hue amounts (Learn −25 sat / −10 light,
Action −30/−10, Resource −10/−4, Goal/Milestone/Unblocking −20/−7), then
frozen here. To re-derive after a major canvas-palette swap, dig those
deltas out of the git history for this file or `config.BADGE_PALETTE`.
Otherwise, just edit the literals to taste.

**Render order** in the Details info pane:

1. Status (always)
2. Priority (`#N Priority` for priority Goals; suppresses the Goal type tile)
3. Type (skipped when the node is a priority Goal)
4. Relationship Priority (`Hard #N` / `Soft #N` for non-Goal nodes in a priority subtree)

The Node Editor priority strip is the same minus Status and Type, which are
handled by other inputs in the editor: Priority → RelPriority.

### Edge-relationship tiles

`EdgeHard` / `EdgeSoft` / `EdgeSynergy` / `EdgeSelf` in `BADGE_PALETTE`. All sit
at similar lightness and are told apart by hue alone. `EdgeHard` shares
`HardRelPri`'s value, so one blue means one thing app-wide: related to a
priority goal via a Hard edge. `EdgeSelf` is a warm sand, deliberately off the
cool Hard/Soft/Synergy axis so the node itself cannot be mistaken for an edge.

These four values previously existed in **three** places — the subtasks table's
own `_REL_BADGE_STYLES`, the explain modal's `_VIA_COLORS`, and its legend —
kept in step by comments claiming they matched. They all read from the palette
now.

Explain speaks in the reader's units, not the scorer's. Value is a share of
total value, cost is the time and effort behind it, and an adjustment is the
percent change it makes to the score. A row's muted detail is a plain fact
(the ratings, the context, the goal), never a parameter value in parentheses.
The only score printed is the 0–100 priority.

### Event-card badge palette

Used on Events-tab event cards. The three trigger-type labels (Manual,
Date, Completion) **all share a single neutral pewter tile** —
they are peer categories and the text inside the badge already carries
the type, so adding hue would only introduce false hierarchy or echo
node-type colors. The `EventTriggered` tile deliberately matches the
`Done` status badge (`#148a68`) so "fired / complete" reads as one
consistent meaning across the app.

The date label reads `Date`, not `Scheduled`. All three name the *mechanism*
that fires the event, and Scheduled describes a state — which the dormant
table now uses it for, on a node whose wake date is set.

An event card keeps the complete description in the DOM and clamps it to three
rendered lines with `.event-card-description`. Do not return to character-count
truncation: proportional glyph widths make equal character counts occupy
different numbers of lines.

| Tile           | Background | Text      | Notes                                                              |
|----------------|-----------|-----------|--------------------------------------------------------------------|
| EventTrigger   | `#56575a` | `#dcdcdd` | Pewter — used for Manual / Date / Completion uniformly.           |
| EventTriggered | `#148a68` | `#ffffff` | Matches `Done`. Used once the event has fired.                     |

### Selection (Cytoscape)

A selected node takes a thick **white** border and keeps its own fill. This
guide used to document a cyan `#0dcaf0` background, which was abandoned because
it was nearly indistinguishable from the Milestone type colour; a border-only
indicator works over any fill. See the comment in [`styles.py`](styles.py).

### Redundant context on a derived row

When a row is shown *because of* another node — an unblocking step under its Now
target — the second line names that node first, then prints only the part of the
row's own context the target has not already implied. Same context and
subcontext: the target alone. Same context, different subcontext: the subcontext.
Different context: both, unabbreviated. Trimming buys back width in a fixed
250px column, but the real point is signal — a step drawn from elsewhere in the
graph is worth noticing, and it only reads as unusual if the ordinary case is
quiet. When the referenced node can't be resolved, print the full context rather
than guess.

### Canvas node fill
Every canvas fills a node by the same precedence, in
`callback_helpers.node_fill_color`. Done and Blocked come first. Otherwise the
node takes its type color. Settings → Appearance sets all of these colors. A
dormant node keeps its fill and adds the dashed `.dormant` style on top; a Now
node keeps its fill and adds the pulsing amber border. Neither dormant nor Now
ever changes the fill, so status and type stay readable underneath.

## Typography

### Heading hierarchy
| Level | Element | Class | Usage |
|-------|---------|-------|-------|
| Page title | `html.H4` | `mb-0` | Panel titles in a flex header row (Node Editor, Goals, Events, Filters) |
| Section title | `html.H5` | `mt-2 mb-1` | Section headers everywhere |
| Section title in a flex row | `html.H5` | `mb-0` | Where a bottom margin would break the row's centring |
| Major section in a modal | `html.H5` | `mt-3 mb-2` | The migration modal's blocks |
| Inline heading | `html.H6` | `style=tokens.SECTION_TITLE_STYLE` | Home-tab section headings |

**Never use `html.Div` with a manual fontSize/fontWeight for a section header.**

### The type scale

Eight steps in `assets/tokens.css`, from `--st-fs-xs` to `--st-fs-2xl`, plus
`--st-fs-heading` and `--st-fs-display` for the two one-off display sizes.
Python reaches them as `tokens.FS_XS` … `tokens.FS_DISPLAY`.

They replaced 28 ad-hoc literals, including a 0.72/0.78/0.82/0.88rem cluster
whose members differed by less than a pixel, and three data tables that each
picked a different one. If a new size seems necessary it is almost always one
of the existing steps; extend the scale in `tokens.css` rather than at a call
site.

### Body text
| Style | How | Usage |
|-------|-----|-------|
| Default | (none) | Standard body text |
| Secondary | `className="text-muted"` | Helper text, table cells, anything recessive |
| Small secondary | `className="text-muted small"` | Description under an input |
| Status message | `style={"fontSize": tokens.FS_BASE}` | Save confirmations |
| Validation error | `style=tokens.ERROR_TEXT_HIDDEN` / `ERROR_TEXT_VISIBLE` | Field-level errors; `ERROR_TEXT_JS_*` for clientside callbacks |
| Badge text | `badge_style(name, font_size=tokens.FS_XS)` | Status and type tiles |

Prefer the `.text-muted` class over `tokens.TEXT_SECONDARY`; reach for the
token only inside an inline style dict where a class cannot go.

### Labels

Duration inputs share `duration_ui.bracket_label` to attach the percentile
reading (10% chance of finishing sooner / a 50/50 estimate / 10% chance of
taking longer) as a hover tooltip on the Lower/Expected/Upper word itself,
rather than as inline paragraph text. `duration_ui.estimate_guidance` renders
the small (i) info icon next to the "Time Estimates" header explaining the
Expected-only exception, following the same info-icon + tooltip pattern used
for "Ratings".
| Context | Pattern | Usage |
|---------|---------|-------|
| Top-level settings label | `dbc.Label("Name", className="fw-bold mt-2")` | Section-level fields in Settings |
| Standard input label | `dbc.Label("Name", className="mt-2")` | Form fields in sidebars, modals, and under section headers (Name, Type, Hours per Week) |
| Compact inline label | `dbc.Label("Name", className="small text-muted mb-0")` | Grouped inputs in a Row (Lower, Expected, Upper) |
| Subsection helper | `html.Small("description", className="text-muted d-block mb-1")` | Under settings section headers |
| Helper text (paragraph) | `html.P("description", className="text-muted small")` | After textarea inputs in settings |
| Formula | `html.Small("formula", className="text-muted d-block mb-1", style={"fontFamily": "monospace"})` | Algorithm formulas |

## Buttons

Build every action button through [`ui_kit.py`](ui_kit.py), which names the
**action** rather than the Bootstrap colour:

| Helper | Colour | Usage |
|--------|--------|-------|
| `primary_action` | `primary` | Commits the form: Save, Apply, View Details |
| `confirm_action` | `success` | Commits *and* finishes: Save & Close, Trigger, Add |
| `cancel_action` | `secondary` | Dismisses without committing: Cancel, Revert, Dismiss |
| `danger_action` | `danger` | Destructive: Delete, Discard |

Do **not** hand-paint a button's background. `custom.css` already restyles
`.btn-danger` to the tamed red app-wide; repeating `get_danger_color()` inline
only creates a second place for the value to drift, which is what six delete
buttons used to do — three of them with their own extra padding on top.

A "Cancel" that actually reverts should say Revert. The unsaved-changes modal
calls that choice Discard/Edit/Save; keep those verbs consistent.

### Modal footers

One structure: actions on the right, the dismissive action first, separated by
`me-2`. Use `flex-fill` only for a two- or three-way choice with no obvious
default (the unsaved-changes and delete confirms). Every modal is
`centered=True`; yes/no confirms are `size="sm"`; a modal with a form is `lg`
and one with a table is `xl` or a `dialog_style` max-width. Every modal has a
`ModalHeader` with a `ModalTitle`, including the short confirms.

### Icon affordances

**One icon family, Bootstrap Icons (`bi bi-*`), at one weight.** Never a Unicode
glyph (`×`, `←`, `↺`, `☰`, `▸`) and never a colour emoji. The app used to have
eight close controls written as a Unicode multiplication sign in five style
variants, several of them `html.Span` and therefore not keyboard-reachable.

Build them through [`ui_kit.py`](ui_kit.py). Each returns a real `<button>` with
the icon, a visually-hidden label, and a tooltip carrying the shared delay:

| Helper | Icon | Usage |
|--------|------|-------|
| `panel_close_button` | `x-lg` | Dismiss a sidebar, panel or popup (`large=True` in a sidebar header) |
| `add_button` | `plus-lg` | Reveal or append a repeatable field |
| `info_button` | `info-circle` | Explain the control or section beside it |
| `restore_button` | `arrow-counterclockwise` | Reset a group of settings |
| `edit_button` | `pencil` | Open an editor for the thing beside it |
| `nav_button` | `arrow-left` / `-right` | Back / forward |
| `step_button` | `dash-lg` / `plus-lg` | A −/+ stepper beside a count |

A `+` means *add a field*; a chevron means *disclose existing content*. Do not
substitute one for the other, and do not stack a disclosure chevron beside a
select — move the affordance to the heading instead.

**A helper that returns a list will not render.** Dash does not flatten nested
lists inside `children`; React rejects them and silently drops the whole
subtree, and nothing at the Python level notices because the component tree
looks correct. `ui_kit` wraps a button and its tooltip in a `.ui-affordance`
span with `display: contents`, which stays out of layout so the button remains
a direct flex item of its row. A test guards this.

### Flat ghost treatment

Icon-only affordances use a flat ghost look — transparent fill, muted stroke,
lightens on hover — rather than a filled button, which reads as chunky on the
dark theme. The classes are background-aware:

| Class | Background | Used for |
|-------|-----------|----------|
| `.btn.editor-icon-btn` | inside a white field | trailing actions in an `.editor-field-group` |
| `.btn.panel-close-btn`, `.adder-btn`, `.info-btn`, `.restore-btn`, `.edit-btn`, `.step-btn` | dark panel | the `ui_kit` affordances above |
| `#main-toolbar .btn-secondary`, `.btn-canvas-overlay.btn-secondary`, `.details-header-btn.btn-secondary` | dark panel/canvas | toolbar, canvas overlay, details header |

Add `.editor-icon-btn-danger` to a remove button so the red appears only on
hover — a multi-row field shouldn't read as a wall of danger buttons.

Table-row actions secondary to scanning the data use progressive disclosure:
hidden until the row is hovered, revealed on keyboard focus, always visible on
coarse pointers. Details subtasks, Reflection history and Events dormant nodes
share this.

A state that belongs to a table row, not an action on it, is a quiet marker
instead, and stays visible. The dormant table's Wakes cell puts a `bi-play-circle`
(`.dormant-now-marker`, soft stroke, native `title`) after the date when the node
will be added to Now on waking. It uses the same play glyph as the Add to Now menu
command and disappears once the node is awake.

### Button sizes
- `size="sm"` — Toolbar, inline actions
- (default) — Form actions (Save, Delete, Clear)
- A form-action row inside a narrow side pane takes `sm` anyway. The Events
  editor's Actions section is the case: at the default size, three buttons
  above a dense table read as a slab rather than a row.
- `size="lg"` + `className="w-100"` — Full-width major actions (Save Settings)

## Spacing

### Standard margins (Bootstrap)
| Class | Value | Common usage |
|-------|-------|-------------|
| `mt-1` / `mb-1` | 0.25rem | Tight vertical gaps |
| `mt-2` / `mb-2` | 0.5rem | Form field spacing |
| `mt-3` / `mb-3` | 1rem | Section spacing |
| `mt-4` / `mb-4` | 1.5rem | Before button rows |
| `me-2` | 0.5rem | Between inline buttons |
| `my-2` / `my-3` | 0.5rem / 1rem | Horizontal rules |

### Padding
| Class | Usage |
|-------|-------|
| `p-2` | Tab content inner padding, card padding |
| `ps-3 pe-4 pb-2 pt-0` | Node editor sidebar content |
| `px-3` | Horizontal padding on panels |

## Layout Dimensions

| Element | Value |
|---------|-------|
| Sidebar width (editor / goals / events / filters) | `350px` (`config.SIDEBAR_WIDTH`) |
| Canvas height | `760px` (from config) |
| Transition speed | `0.3s ease` (sidebar toggles) |

The left sidebars (editor, Goals, Events) slide with `transform: translateX(...)` and `willChange: transform`, not by animating `left`. The browser runs a transform animation off the main thread, so the slide stays smooth while the page is busy. Rebuilding a sidebar's list waits until the slide finishes. On the Events tab, the content glides aside with the sidebar. Its style comes back in the same callback return as the sidebar's, so both animations start on the same frame.

Only the Events tab does this. Everywhere else a sidebar slides over the content and covers it. Events earns the exception because its sidebar and its panel are two halves of one task: you pick an event from the list and read its detail beside it. The other sidebars are transient tools over a workspace, and pushing that workspace aside costs more than it gives. It animates `width`, which is main-thread layout on every frame, and it moves the content: on the Nodes canvas the pan does not change, so the whole graph shifts right by the sidebar's width and loses its right edge — possibly including the node the editor just opened. Covering a predictable left strip is less disorienting, and the canvas can pan out from under it. Before adding a tab to the glide, be sure its content is cheap to reflow and that seeing it beside the panel is worth the shift.

Content that draws into a fixed-size surface does not follow a glide on its own. The Events graph is resized on `#events-tab-inner`'s `transitionend` rather than every frame, since a per-frame Cytoscape redraw is exactly the main-thread work the transform-based slide avoids. The canvas is clipped mid-glide and settles at the end.

A panel that loads on first view shows the shared loading cover: `dbc.Spinner(spinner_style=LOADING_SPINNER_STYLE)` over a `canvas-cover-label` caption, inside a `loading-cover` div. Analyze and the Goals sidebar use it.

Analyze renders on its first visit, starting while its tab is still hidden when the pointer or focus reaches it. On every reveal, `assets/analyze_first_paint.js` hides only the `.dash-graph` drawings. It resizes their Plotly roots against the visible columns, then reveals them on the next frame. Keep Analyze graphs responsive, and give their wrappers an explicit figure height. That lets the sizing gate hold the finished page layout without exposing Plotly's hidden-tab fallback width.

## Borders & Dividers

- Panel dividers: `1px solid var(--st-border-panel)` (`tokens.BORDER_PANEL`)
- Selected card: `2px solid var(--st-accent)` (`tokens.ACCENT`)
- Unselected card: `1px solid var(--st-border-panel)`
- **Form/sidebar dividers**: `html.Hr(className="my-2")` — tight spacing for sidebars, settings, modals
- **Standalone section dividers**: `html.Hr(className="my-3")` — more spacious, for filter panels and major sections
- **Context menu dividers**: `_menu_divider()` in `layout.py` (`html.Hr(style={"margin": "2px"})`) — ultra-tight
- Never use bare `html.Hr()` — always specify a margin class
- Context menu panel: the `.ctx-menu` class in `theme.css` (`--st-radius`, `--st-shadow-panel`)

## Context Menus

Build every right-click menu and popover from `_floating_menu`, `_menu_item`,
`_menu_divider` and `_menu_heading` in `layout.py`, and open it through
`assets/menus.js`, which positions, dismisses and runs submenus for all of them.
Don't hand-build a menu or give one its own inline panel style.

A menu opened from something that doesn't say what it does, like an icon
button, starts with a `_menu_heading` caption naming its purpose (`Sort by`).
A right-click menu doesn't need one, since its target is the thing you clicked.

A node has exactly one menu, `#node-context-menu`, wherever it appears:
canvases, Next rows, Now cards and Goals sidebar cards. Rows and cards opt in
with `node_menu_attributes` (`callback_helpers.py`). An option that fits only
some nodes is hidden for the rest rather than living in a separate menu:
external links appear only when set, and Set Priority only for a single Goal.

Group items by user intent: primary Edit; inspection (View Details / Explain
Priority); Set Priority, alone in a Goal-only section; workflow state (Now /
Event / Done); conditional external links; and an isolated destructive Delete
row with `_menu_item(..., danger=True)`. An option that fits only some nodes
gets a section of its own where it can, so hiding it leaves the rest of the
menu identical for every node. The Events sidebar menu follows the same
grouping: Edit; Trigger Now…; Delete…. When one `+` can add things in more
than one way, it opens a menu rather than sitting beside a second button:
the Events tab's Dormant Nodes `+` offers New node and Existing nodes…. A
text link next to a `+` reads like save-status feedback. A choice menu, such as a sidebar sort
menu, gives every row a check glyph and shows only the current row's
(`.ctx-menu-item-checked`). Labels name the command in full rather
than a bare noun (`View Details`, not `Details`). Toggle labels describe the
resulting action (`Add to Now` / `Remove from Now`, `Mark Done` / `Reopen`)
rather than naming the underlying field. Commands that open another choice or
confirmation use an ellipsis; a submenu row uses a caret instead. When a
section has nothing to show, hide it along with its leading divider.

Every action row has a compact leading Bootstrap Icon (`.ctx-menu-icon`) plus
its full text label (`.ctx-menu-label`); the label remains the accessible,
primary cue. Keep the icon column fixed and use the same icon for a command
wherever it appears. State toggles swap their glyph with their label: Now uses
play/pause, and Done/Reopen uses check/undo. Destructive Delete uses `trash3`
and inherits the danger colour.

## Cards

```python
import style_tokens as tokens

style = tokens.card_style(selected=False)
```

`card_style` returns the standard padding, radius, border, background, cursor
and transition, swapping to the raised background and the accent border when
`selected=True`.

Clickable cards must use a native `html.Button(type="button")` when the whole
surface performs one action. Reset its browser chrome in a scoped class, retain
the standard card colors above, and provide a visible `:focus-visible` outline.

The Details empty-state pattern is `.details-suggestion-row`: the name, with
the context alone on a muted mono line below. Every suggestion is a Goal, so the
card has no type strip or type label. The subcontext is left out, since a Goal's
subcontext often repeats its own name. The corner badge matches the Goal's card in the
Goals sidebar, and both come from `_goal_corner_badge`. Priority Goals show
their rank in `PriorityRank` orange. Other Goals show their 0-100 priority
from `analyze_callbacks.normalize_goal_scores`. Leave out metadata that every
card would repeat, such as a status the type already implies. Never normalize a
score against the visible list, since the number would then describe the list
rather than the node.

Keep these rows at their standard card size even when the panel is short. The
scrolling `.details-empty-state` uses a subtle lower-edge fade to communicate
that more results continue below the viewport, and the suggestions container
keeps enough bottom padding for the final card to finish above that fade.

## Inputs

- Standard: `dbc.Input(type="text")` — DARKLY defaults
- Textarea: `dbc.Textarea(style={"height": "120px", "resize": "vertical"})`
- Placeholders end in `...` (three dots, not the single ellipsis character) and
  describe the action: `Name node...`, `Choose node type...`. Every light
  control renders them in `--st-text-placeholder`. The filter sidebar keeps its
  dark `All` placeholders, since there they read as a value.

### Dropdowns

The app has three dropdown implementations and cannot reasonably have fewer:

| Implementation | Used for |
|----------------|----------|
| `dbc.Select` — a native `<select>` | short, fixed choices (type, unit, rank) |
| `dcc.Dropdown` — Dash 4's Radix popover | long or searchable lists, multi-select |
| [`context_picker.py`](context_picker.py) | context / subcontext, which cascade |

**They all open the same panel.** [`assets/dropdowns.css`](assets/dropdowns.css)
owns every rule for all three, built from the tokens. The reference look is the
context picker's panel — it was the one that already looked right.

The native `<select>` popup is reachable because of `appearance: base-select`,
which swaps OS rendering for a real, styleable `::picker(select)` while keeping
native semantics and keyboard behaviour. Chromium 135+; the app ships in
Electron and is developed in Chrome, and an `@supports` guard leaves the OS
popup alone elsewhere.

Two things that are easy to get wrong there, both established by probing rather
than by reading the spec:

- `::picker(select)` accepts **no descendant selectors**. Every form of
  `select::picker(select) option` is dropped silently by the parser, so rows
  have to be addressed as plain `option`.
- The trigger needs `display: flex`, or base-select stacks its parts and the
  control grows from 38px to 62px. Keep Bootstrap's established chevron and
  hide the added `::picker-icon`, so native selects continue to match the
  context picker and `dcc.Dropdown` when closed.
- Set `position-try-order: normal` on the picker. Chromium's UA default prefers
  whichever side has more vertical room, which can open a short menu upward
  even when it fits below. `normal` tries below first and retains the UA's
  above-trigger fallback for genuine overflow.

Do not add a new dropdown style. If a control needs a look the shared rules do
not give it, change the shared rules.

### Unit selects

Use `duration_ui.unit_select(...)` with `TIME_UNITS` or `DURATION_UNITS`. The
four-unit select was typed out by hand at nine sites, which is how one ended up
missing `Years` while `hours_to_friendly_unit` could still return it, and how
four picked up a 100px width the others never got.

### Context / subcontext pickers

Use the shared builders in `context_picker.py`; do not add a new pair of visible
Context and Subcontext dropdowns.

- Node editing uses the single-path cascading picker. A context opens a
  subcontext flyout after a 500ms fine-pointer hover or immediately on click.
- Filtering uses the hierarchical checkbox picker. Only the parent checkbox
  selects every subcontext; the rest of the parent row expands or collapses.
  Every context starts collapsed each time the menu opens.
- `No subcontext` is always the final child, separated from user-defined
  subcontexts by a horizontal rule.
- Up/Down moves through choices, Enter/Space activates the focused choice,
  Right enters/expands, Left returns/collapses, and Tab keeps native order.
- The closed multi-picker shows at most two configured-order context summaries,
  followed by `+N` without another separator (for example,
  `Wisdom · STEM +1`). A bare context implies all of its subcontexts; a count
  in parentheses is the number of selected subcontexts.

The migration/remapping grid is the deliberate exception. Its paired compact
selects include `Keep existing` / `Clear` commands and compare many rows at
once, so they are not ordinary context assignment or filtering controls.

### Unified field (input + trailing icon)

When a text input needs a **per-row trailing action** (browse, open, remove a
repeatable row), wrap the input and its ghost icon button(s) in a single
`.editor-field-group` rather than placing a separate filled button beside it.
The group carries the border, white background, radius, and focus ring
(mirroring DARKLY's `.form-control`), and the inner input drops its own chrome —
so the whole control spans full width and lines up with standalone fields like
Type and Description. A separate beside-button leaves the input ending one
button-width short, which reads as a narrower field.

```python
html.Div([
    dbc.Input(id={"type": "obsidian-link", "index": i}, type="text"),  # no flex/border styles
    dbc.Button(html.I(className="bi bi-folder2-open"),
               id=..., className="editor-icon-btn"),
    dbc.Button(html.I(className="bi bi-x-lg"),
               id=..., className="editor-icon-btn editor-icon-btn-danger"),
], className="d-flex editor-field-group")
```

Keep disclosure chevrons for content that is actually expanded/collapsed, such
as the Explain modal's "Calculation details" section. Its `.editor-chevron`
uses `.on-dark` for the muted panel-text stroke and `.open` for rotation. Do
**not** stack a disclosure chevron beside a `dbc.Select`/`dcc.Dropdown`; either
move the affordance to the heading or promote the hidden control to its own
always-visible field when it is commonly used.

### Radio groups and nesting depth

A mutually-exclusive choice is a `dbc.RadioItems` with `inline=True` when the
options are short (`event-trigger-type`, `event-trigger-mode`) and stacked when
the labels run long. Every radio group in the app is currently inline; the
stacked variant lost its last example when the priority override was retired,
so match the inline ones unless your labels genuinely won't fit. Use a
`dbc.Checklist` only for independent toggles — see the pill group below.

Once a choice grows past two or three options, switch to a `dbc.Select`
instead of letting radios wrap or crowd a shared row. A choice that only
changes how a list is viewed, like its sort, goes behind a menu button
instead. See the sidebar list toolbar below.

Size carries the nesting. A radio that *is* the section's question runs at the
default size. A radio that refines a choice already made above it drops to
`style={"fontSize": "0.85rem"}`, so it reads as a detail rather than competing
with its parent. The Any/All selector inside the Node Completion trigger sits
at this second level.

Help text under either sits in `html.Small(className="text-muted d-block mb-2",
style={"fontSize": "0.8rem"})`.

When the same control exists on two surfaces, drive their help text from
**one** shared formatting helper rather than duplicating literals — the copies
drift otherwise. Better still, don't build the second surface: the Events tab
once had its own copy of the node editor for dormant nodes, and the two
drifted until it was folded back into the one editor.

### Sidebar list toolbar (search + sort)

The Goals and Events sidebars share one toolbar, built by
`list_toolbar.build_list_toolbar`. It holds a search field and a sort button
beside it. Use it for any new sidebar list rather than stacking a search field
over a sort dropdown.

- The sort button is a flat ghost icon (`bi bi-arrow-down-up`). It opens a
  floating menu of sort options, right-aligned under the button. The menu
  starts with a `Sort by` heading and checks the current option.
- The current sort is not written on the toolbar. The list itself should show
  it, as the goal cards' corner badges and the event drag handles do. The
  button's tooltip names it too (`Sort: Priority`).
- The choice lives in a local-storage `dcc.Store`, so it survives a reload.
- Keep filters out of the toolbar. A filter that hides part of a list goes
  at the end of that list as a divider that counts what it hides:
  `2 triggered events hidden · Show`. Once shown, the divider reads
  `2 triggered events · Hide` and heads the revealed cards. The count follows
  the search. `Show`/`Hide` is a lighter-gray text button with no underline.

### Toggle-pill group (multi-select day/option picker)

For a compact set of mutually-independent toggles rendered as pills (e.g. the
habit-mode weekday picker), use a `dbc.Checklist` styled with Bootstrap's
`btn-check` pattern. Do **not** set `inline=True` — it double-wraps the items.
Avoid Bootstrap's `btn-group` here: its flex rules collapse the pills to text
width. Instead size them with the `.habit-days-picker` flex rule in
`assets/custom.css` (`display:flex; gap; .btn { flex:1 1 0 }`), which spreads
N equal-width pills across the row so none overflow the 350px sidebar.

```python
dbc.Checklist(
    id="node-habit-days",
    options=[{"label": "S", "value": 6}, {"label": "M", "value": 0}, ...],
    value=[0, 1, 2, 3, 4, 5, 6],
    className="habit-days-picker",
    inputClassName="btn-check",
    labelClassName="btn btn-outline-light btn-sm",
    labelCheckedClassName="active",
)
```

The selected `value` list holds the chosen options directly, so selection
state needs no extra callback. Compare these lists as sets in dirty-checks
(`is_form_dirty_vs_snapshot`) since the order is not significant.

### Row editor (Settings ▸ Contexts)

When the user edits a list of named things that other data refers to by name,
give each item a row that remembers the name it was loaded under, rather than
a free-text field. The row's identity is what turns an edit into a rename
instead of a delete plus an add. The Contexts tab is the example; its model is
in `context_rules.py` and its rows in `build_context_editor_rows`.

- **Children as chips.** A context's subcontexts are pills holding an inline
  input sized in `ch` to its text, a grip, and a trailing `×`. The grip is the
  drag handle, because a drag cannot start inside a text field. It uses the
  progressive disclosure described under the flat ghost treatment above.
- **Removal is held, not immediate.** Removing a saved row strikes it through
  on `--st-danger-wash`, names how many nodes it holds, and offers undo until
  Save. A row that was never saved simply disappears.
- **Typing never re-renders.** Names are callback `State`, folded into the
  store on the next structural edit and on Save, so the caret stays put. Live
  feedback writes only `invalid` flags and the one summary line under the
  rows.
- **Drag remounts.** SortableJS moves DOM nodes behind React's back. The
  container's React `key` is derived from the row and chip ids in order, so
  the render after a drop remounts it rather than reconciling against the
  rearranged DOM. That matters most for a chip dragged into another row.
  Inside a modal, use SortableJS's fallback mode with `fallbackOnBody` and the
  drag-clone z-index, so the clone shows above the modal.
- **Plain-id controls stay static.** A callback `Input` with a string id must
  be in the initial layout, so the "Add context" button sits outside the
  rendered rows. Only pattern-matched ids live inside them.

### Details local-view control row

Graph-layout physics sliders use qualitative endpoint rows rather than native
numeric marks: **Short / Long** for Edge Length and **Weak / Strong** for
Gravity and Repulsion. Set the slider's `marks=None` and render the endpoints in
a sibling `.graph-settings-axis` row. This keeps both labels aligned with the
track edges, makes them visually subordinate to the parameter name, and leaves
the numeric range, step and stored value strictly as implementation details.

The Details subtree controls are a row of compact switches. Use
`.details-view-controls` for the wrapping flex row. Both physical copies of
this row (Milestones/Subtasks) must use the same classes and stay synchronized
through callbacks. Order the row as enabled-by-default switches followed by
disabled-by-default switches, keeping the controls in one continuous compact
row without separators.

**Keep this row switches-only.** A slider among switches reads as a different
class of control and needs fixed widths and negative-margin nudges to line up,
which is why Max Depth was moved out to the graph-settings panel. Anything that
isn't a toggle belongs there instead.

Max Depth is the one control in a graph-settings panel that is not about
layout: it also limits the subtasks table, milestones strip and Time
Simulation. It is opt-in via `build_graph_settings_panel(..., max_depth_id=…)`
so only the Details canvas gets it, and it sits above a divider ahead of the
physics sliders to mark it as a different kind of control. Its wider reach is
documented in `docs/features.md` rather than captioned in the panel — this is
a single-user app, so in-UI explanation of the author's own model is noise.

## Data tables

Details subtasks, Events dormant nodes and Reflection history are one family.
Build all three with `tokens.TABLE_PROPS`, `tokens.TABLE_CLASS` and
`tokens.TABLE_STYLE`, and style cells with `tokens.CELL_PRIMARY` /
`tokens.CELL_MUTED`.

They used to disagree on font size (0.82 / 0.85 / unset) and on whether to clear
DARKLY's per-cell background tint (only one did), and the Events table drew its
Type column from an inline literal while the columns beside it used
`.text-muted`. A test asserts all three share one definition.

A default value should recede rather than disappear: muted text keeps "None"
quiet enough that a real delay still stands out, without the absence of a
whole column having to carry that meaning.

The Events dormant table extends that rule to certainty. Its Wakes column is
muted while the date is a projection, because the event has not fired and the
date can still move. It takes full contrast once the event fires and the date
is committed. A woken node takes a badge, the only non-text state in the
column.

The Details subtasks Name column is fixed at 360px. Its link is a single-line
ellipsis and its `title` contains the complete node name; long names must not
move or crowd the Status, Relationship, and classification columns.

## Badges

Use `config.badge_style(name)` rather than `dbc.Badge(color=...)` so badges
pick up the centralized BADGE_PALETTE instead of stock Bootstrap colors.
The helper returns an inline-style dict with background, foreground, and
font size pre-set.

```python
from config import badge_style

# Standard size (0.75rem) — Node Editor + Details info-pane stack
html.Span(node.status, className="badge", style=badge_style(node.status))

# Compact size (0.7rem) — subtasks-table cells, goal cards
html.Span(rel, className="badge",
          style=badge_style('HardRelPri', font_size="0.7rem"))
```

Valid names: `Goal`, `Priority`, `PriorityRank`, `Action`, `Learn`,
`Resource`, `Milestone`, `Open`, `Done`, `Blocked`, `HardRelPri`, `SoftRelPri`,
`EventTrigger`, `EventTriggered`. Unknown names fall back to a neutral gray.

## Tooltips (hover)

```python
import style_tokens as tokens

style = tokens.TOOLTIP_STYLE
```

Plotly hover labels take the same three colors through `layout.hoverlabel`.
The Details Time Simulation chart is the example. It is a high-level view read
by hovering, so it turns off drag-zoom and uses `closest` hover. That hover
answers only over a bar and adds no exact axis value. Its axis, lines and
tooltips share one natural time unit rather than raw hours.

## Scrollbars

**Preference: no visible scrollbars anywhere in the app.** Elements may still scroll — the scrollbar chrome should just be invisible.

This is enforced globally in `assets/custom.css` via a `*` selector:
```css
* { scrollbar-width: none; -ms-overflow-style: none; }
*::-webkit-scrollbar { display: none; }
```

Do **not** add per-element scrollbar-hiding rules — the global rule covers everything. If a new scrollable container appears with a visible scrollbar, check that the global rule hasn't been overridden locally.

## Z-Index Scale

| Layer | Value |
|-------|-------|
| Startup cover | `20000` |
| Context menu | `10000` |
| Tooltip | `9999` |
| Drag clone (a sortable item dragged out of a modal) | `2000` |
| Filters overlay | `100` |
| Canvas first-paint cover | `30` |
| Graph layout panel | `20` |
| Canvas overlays (buttons, stats) | `10` |

## Calculation status

The Time Simulation panel uses a small muted, polite live-region caption for
“Calculating…” and the actual trial count. Hide stale results while a different
selection is calculating. If the responsiveness limit reduces trials, explain
that beside the count without adding a modal or interrupting navigation.

## Canvas loading cover

A canvas that isn't ready is covered, not shown mid-assembly. The cover is
opaque in the canvas color (`--st-bg-canvas`), fills the canvas container, and sits
above every canvas overlay, so the wait reads as an empty canvas rather than a
panel laid over a half-drawn graph.

Show its caption in the same task that reveals the tab, never on a timer. The
wait a loading caption explains is usually main-thread work, and a timer can't
fire during it, so a delayed caption tends to arrive after the content it was
announcing. Let it appear outright rather than fading in; a fade needs rendered
frames to get going, and the main thread often stalls right after the reveal.
A canvas that is already ready still shows nothing, because the cover lifts
before that frame is painted. Fade the cover out when it has been
on screen, and cut straight to the content when it hasn't — a cross-fade over a
cover the user never saw only reads as lag.

Every cover needs a backstop that lifts it regardless. Content the user can see
is always better than a spinner with nothing behind it.

## Startup cover

Don't show a surface the user can click before it can respond. The Home tab
paints half a second after launch, seconds before the app can act on it, and
a UI that looks ready but drops clicks is worse than a short wait. So the whole
window opens behind a startup cover, and the app appears once it is ready.

The cover follows the canvas cover's rules. It is opaque in the canvas color,
which is also the desktop window's title-bar color. It shows the shared spinner
over a `canvas-cover-label` caption, "Getting ready…". It sits above every
other layer, modals included. It fades out over 200 ms, and a backstop lifts it
regardless. It is part of the page template (`layout.build_index_string`), not
the Dash layout, so it is the first thing painted.

Its lift condition is in the Startup readiness section of
[`docs/app_architecture.md`](docs/app_architecture.md). If new startup work
runs, the cover waits for it. Keep work that nobody sees at launch out of the
load path: skip a render the layout already carries, and give a hidden surface
its own arrival signal. When a callback's page-load answer depends only on the
layout, mark it `@prerendered` so the server builds that answer into the
layout instead of the browser asking for it.
