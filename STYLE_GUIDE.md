# Skill Tree Style Guide

Reference for all UI styling conventions. Use these tokens when adding or modifying UI elements.

## Theme

Bootstrap DARKLY theme via `dash-bootstrap-components`.

## Color Palette

### Backgrounds
| Token              | Hex       | Usage                              |
|--------------------|-----------|------------------------------------|
| bg-canvas          | `#1a1d21` | Graph/canvas containers            |
| bg-sidebar         | `#212529` | Sidebar panels, list panels        |
| bg-card            | `#2b3035` | Cards, tooltips, selected states   |
| bg-card-default    | `#212529` | Unselected card background         |

### Borders
| Token        | Hex       | Usage                                  |
|--------------|-----------|----------------------------------------|
| border-panel | `#495057` | Panel dividers, card borders, hr lines |

### Text
| Token      | Hex       | Usage                     |
|------------|-----------|---------------------------|
| text-primary | `#dee2e6` | Main body text           |
| text-muted   | `#6c757d` | Helper text, secondary   |
| text-white   | `#fff`    | Node labels, headings    |
| text-soft    | `#adb5bd` | Subtle indicators        |

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
| Override     | `#c516a5` | `#ffffff` | Manual override; rare but distinct. Always first in stack. |
| Goal         | `#cdbe23` | `#ffffff` | Type tile. Canvas Goal color with −5 sat (intentional exception to the default −20 muting — yellow goes olive when pushed further). Suppressed when a `Priority N` tile is shown. |
| Priority     | `#cdbe23` | `#ffffff` | `Priority N` for priority Goals. Same hue as Goal.        |
| Action       | `#bb6823` | `#ffffff` | Type tile. More desaturated than the default — orange holds saturation visually. |
| Learn        | `#1d5cba` | `#ffffff` | Type tile.                                                |
| Resource     | `#814d9e` | `#ffffff` | Type tile. Less desaturated than the default — purple turns muddy if pushed too far. |
| Milestone    | `#2f909d` | `#ffffff` | Type tile.                                                |
| Open         | `#3e61a0` | `#ffffff` | Status tile — solid blue.                                 |
| Done         | `#148a68` | `#ffffff` | Status tile.                                              |
| Blocked      | `#9e3838` | `#ffffff` | Status tile.                                              |
| HardRelPri   | `#2a4d6e` | `#d6e0ee` | `Hard N` for non-Goal nodes in a priority Goal subtree. Darker rugged blue — matches subtasks-table Hard. |
| SoftRelPri   | `#414f5c` | `#d0d6dc` | `Soft #N`. Matches subtasks-table Soft tile.              |

The type-color values were originally derived by HSL-desaturating the
saturated canvas palette by per-hue amounts (Learn −25 sat / −10 light,
Action −30/−10, Resource −10/−4, Goal/Milestone/Override −20/−7), then
frozen here. To re-derive after a major canvas-palette swap, dig those
deltas out of the git history for this file or `config.BADGE_PALETTE`.
Otherwise, just edit the literals to taste.

**Render order** in the Details info pane:

1. Override (always first if active)
2. Status (always)
3. Priority (`#N Priority` for priority Goals; suppresses the Goal type tile)
4. Type (skipped when the node is a priority Goal)
5. Relationship Priority (`Hard #N` / `Soft #N` for non-Goal nodes in a priority subtree)

**Render order** in the Node Editor priority strip is the same minus
Status and Type (those are handled by other inputs in the editor):
Override → Priority/RelPriority.

### Subtasks-table edge palette

Used by the `_REL_BADGE_STYLES` map for the relationship column. All
three tiles sit at similar lightness, distinguished only by hue. Hard
matches the `Hard #N` priority badge (`HardRelPri` above) so the same
blue means the same thing across the app — a node related to a priority
goal via a Hard edge.

| Edge type | Background | Text      | Notes                                                     |
|-----------|-----------|-----------|-----------------------------------------------------------|
| Hard      | `#2a4d6e` | `#d6e0ee` | Darker rugged blue. Same value as the `HardRelPri` badge. |
| Soft      | `#576068` | `#dde0e5` | Neutral slate.                                            |
| Synergy   | `#466a78` | `#d8e6e9` | Cyan-teal — categorically different from Hard/Soft.       |

The explain-modal contributors chart and legend use the same edge palette
plus a `Self` tile (`#685e52` warm sand) for the node itself.

### Event-card badge palette

Used on Events-tab event cards. The three trigger-type labels (Manual,
Scheduled, Completion) **all share a single neutral pewter tile** —
they are peer categories and the text inside the badge already carries
the type, so adding hue would only introduce false hierarchy or echo
node-type colors. The `EventTriggered` tile deliberately matches the
`Done` status badge (`#148a68`) so "fired / complete" reads as one
consistent meaning across the app.

| Tile           | Background | Text      | Notes                                                              |
|----------------|-----------|-----------|--------------------------------------------------------------------|
| EventTrigger   | `#56575a` | `#dcdcdd` | Pewter — used for Manual / Scheduled / Completion uniformly.       |
| EventTriggered | `#148a68` | `#ffffff` | Matches `Done`. Used once the event has fired.                     |

### Selection (Cytoscape)
| Token           | Hex       |
|-----------------|-----------|
| selected-node   | `#0dcaf0` |
| selected-border | `#055160` |

## Typography

### Heading Hierarchy
| Level | Element | Style | Usage |
|-------|---------|-------|-------|
| Page title | `html.H4` | `className="mb-3 mt-3"` | Top of each tab ("Settings", "Next") |
| Section title | `html.H5` | `className="mt-2 mb-1"` | All section headers everywhere: node editor, settings, modals |
| Inline heading | `html.H6` | `style={"fontWeight": "500"}` | Minor headings in cards |

**Never use `html.Div` with manual fontSize/fontWeight for section headers.** Always use `html.H5` for consistent font rendering.

### Body Text
| Style | Class/Style | Usage |
|-------|-------------|-------|
| Default | (none) | Standard body text |
| Small muted | `className="text-muted small"` | Helper/description text below inputs |
| Status message | `style={"fontSize": "0.85rem"}` | Save confirmations, errors |
| Tooltip text | `style={"fontSize": "0.85rem", "lineHeight": "1.5"}` | Hover tooltips |
| Badge text | `style={"fontSize": "0.7rem"}` | Status badges, type badges |
| Priority badge | `style={"fontSize": "0.75rem"}` | Editor priority badge |

### Labels
| Context | Pattern | Usage |
|---------|---------|-------|
| Top-level settings label | `dbc.Label("Name", className="fw-bold mt-2")` | Section-level fields in Settings Nodes tab (Node Types, Contexts) |
| Standard input label | `dbc.Label("Name", className="mt-2")` | Form fields in sidebars, modals, and under section headers (Name, Type, Hours per Week) |
| Compact inline label | `dbc.Label("Name", className="small text-muted mb-0")` | Grouped inputs in a Row (Lower, Expected, Upper) |
| Subsection helper | `html.Small("description", className="text-muted d-block mb-1")` | Under settings section headers |
| Helper text (paragraph) | `html.P("description", className="text-muted small")` | After textarea inputs in settings |
| Formula | `html.Small("formula", className="text-muted d-block mb-1", style={"fontFamily": "monospace"})` | Algorithm formulas |

## Buttons

| Role | `color=` | Usage |
|------|----------|-------|
| Primary action | `primary` (blue) | Save |
| Confirm + close | `success` (green) | Save & Close, New Node |
| Secondary/reset | `secondary` (gray) | Clear |
| Destructive | `danger` + custom bg | Delete (uses `ConfigManager.get_danger_color()` = `#c94c4c`) |
| Icon/link | `link` | +/- buttons, restore defaults |

### Flat ghost icon buttons

For icon-only affordances, use the flat "ghost" treatment (transparent fill,
muted stroke, lightens on hover) rather than a filled `color="light"`/
`"secondary"` button — filled icon buttons read as chunky and high-contrast on
the dark theme. Use **one** icon family (Bootstrap Icons, `bi bi-*`) at one
weight; never mix in Unicode glyphs (`▾`, `×`) or color emoji (📁). The ghost
classes are background-aware:

| Class | Background | Icon at rest | Used for |
|-------|-----------|--------------|----------|
| `.btn.editor-icon-btn` | inside a white field | muted dark `#6c757d` | trailing actions in an `.editor-field-group` (browse, open, remove) |
| `#main-toolbar .btn-secondary` / `.btn-canvas-overlay.btn-secondary` / `.details-header-btn.btn-secondary` | dark panel/canvas | muted light | toolbar, canvas overlay, details header |

Add `.editor-icon-btn-danger` to a remove (`bi bi-x-lg`) button so the red
(`#c94c4c`) appears only on hover — a multi-row field shouldn't read as a wall
of danger buttons.

Disclosure / secondary affordances next to a **dropdown** heading (e.g. the
Search "locate" crosshair) go as a muted `color="link"` icon next to the section
heading — not stacked beside the control, which would compete with its native
chevron. Use the `+`-adder style: `dbc.Button(color="link",
className="p-0 ms-2 text-decoration-none text-muted")`.

A disclosure toggle on a plain **text input** (e.g. Name → Aliases) may instead
live *inside* the field as a trailing chevron — see *Unified field* below.

### Button sizes
- `size="sm"` — Toolbar, inline actions
- (default) — Form actions (Save, Delete, Clear)
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

## Borders & Dividers

- Panel dividers: `1px solid #495057`
- Selected card: `2px solid #0d6efd`
- Unselected card: `1px solid #495057`
- **Form/sidebar dividers**: `html.Hr(className="my-2")` — tight spacing for sidebars, settings, modals
- **Standalone section dividers**: `html.Hr(className="my-3")` — more spacious, for filter panels and major sections
- **Context menu dividers**: `html.Hr(style={"margin": "2px"})` — ultra-tight
- Never use bare `html.Hr()` — always specify a margin class
- Context menu: `border-radius: 6px`, `box-shadow: 0 4px 16px rgba(0,0,0,0.4)`

## Cards

```python
style={
    "padding": "10px 14px",
    "borderRadius": "6px",
    "border": "1px solid #495057",       # or "2px solid #0d6efd" if selected
    "backgroundColor": "#212529",         # or "#2b3035" if selected
    "cursor": "pointer",
    "transition": "background-color 0.2s",
}
```

## Inputs

- Standard: `dbc.Input(type="text")` — uses Bootstrap DARKLY defaults
- Textarea default: `dbc.Textarea(style={"height": "120px", "resize": "vertical"})`
- Underline-only input: `style={"border": "none", "borderBottom": "1px solid #495057", "borderRadius": "0"}`

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

A single text field can also carry an **in-field disclosure chevron** (Name →
Aliases): same `.editor-field-group`, with the toggle button styled
`editor-icon-btn editor-disclosure-btn` wrapping a `html.Span(className=
"editor-chevron")`. `.editor-chevron` renders the *exact* DARKLY form-select
chevron (stroke #303030, width 2) so it matches the native Context/Subcontext
arrows instead of the thinner `bi-chevron-down`; a clientside callback adds
`.open` to rotate it 180° while the collapse is open.

Do **not** stack such a chevron beside a `dbc.Select`/`dcc.Dropdown` — it would
double up with the native one. For those, either move the affordance to the
heading (Search locate) or promote the hidden control to its own always-visible
field when it's almost always used (Subcontext is a permanent field in the node
editor and both add-node modals).

### Radio groups and nesting depth

A mutually-exclusive choice is a `dbc.RadioItems` with `inline=True` when the
options are short (`event-trigger-type`, `dormant-node-mode`, `events-sort-mode`)
and stacked when the labels run long (`dormant-override-mode`). Use a
`dbc.Checklist` only for independent toggles — see the pill group below.

Size carries the nesting. A radio that *is* the section's question runs at the
default size. A radio that refines a choice already made above it drops to
`style={"fontSize": "0.85rem"}`, so it reads as a detail rather than competing
with its parent. The Any/All selector inside the Node Completion trigger and
`dormant-override-mode` are both at this second level.

Help text under either sits in `html.Small(className="text-muted d-block mb-2",
style={"fontSize": "0.8rem"})`.

When the same control exists on two surfaces (the event editor and the
dormant-node modal both build triggers), drive their help text from **one**
shared formatting helper rather than duplicating literals — the copies drift
otherwise. `_trigger_mode_hint` in `event_callbacks.py` feeds both.

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

### Details local-view control row

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

Valid names: `Override`, `Goal`, `Priority`, `Action`, `Learn`, `Resource`,
`Open`, `Done`, `Blocked`, `HardRelPri`, `SoftRelPri`, `EventTrigger`,
`EventTriggered`. Unknown names fall back to a neutral gray.

## Tooltips (hover)

```python
style={
    "position": "fixed",
    "zIndex": 9999,
    "maxWidth": "280px",
    "fontSize": "0.85rem",
    "lineHeight": "1.5",
    "backgroundColor": "#2b3035",
    "color": "#dee2e6",
    "borderColor": "#495057",
}
```

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
| Context menu | `10000` |
| Tooltip | `9999` |
| Filters overlay | `100` |
