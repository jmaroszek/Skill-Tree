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

### Node-info badge palette (slightly muted)

The Node Editor priority strip and the Details info pane share a single
palette (`config.BADGE_PALETTE`, accessed via `config.badge_style(name)`).
All values are slightly muted from their canvas / Bootstrap-Darkly
equivalents so the strip sits alongside the cool/quiet subtasks-table
edge tiles without feeling loud. **This file is the human-readable source
of truth — keep `config.BADGE_PALETTE` and the documentation here in
sync.**

| Tile         | Background | Text      | Notes                                                     |
|--------------|-----------|-----------|-----------------------------------------------------------|
| Override     | `#c4528c` | `#ffffff` | Manual override; rare but loud. Always first in stack.    |
| Goal         | `#f39c12` | `#ffffff` | Type tile — Darkly `--bs-warning` (matches the empty-state ranking list). Suppressed when a `Priority N` tile is shown. |
| Priority     | `#f39c12` | `#ffffff` | `Priority N` for priority Goals. Same hue as Goal.        |
| Action       | `#d97120` | `#ffffff` | Type tile.                                                |
| Learn        | `#2c70d6` | `#ffffff` | Type tile.                                                |
| Resource     | `#7c4d9c` | `#ffffff` | Type tile.                                                |
| Open         | `#5677a6` | `#ffffff` | Status tile — lighter, friendlier blue.                   |
| Done         | `#1a9d78` | `#ffffff` | Status tile.                                              |
| Blocked      | `#b35353` | `#ffffff` | Status tile.                                              |
| HardRelPri   | `#375a7f` | `#d6e0ee` | `Hard N` for non-Goal nodes in a priority Goal subtree. Darker rugged blue — matches subtasks-table Hard. |
| SoftRelPri   | `#52606e` | `#d0d6dc` | `Soft #N`. Matches subtasks-table Soft tile.              |

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
| Hard      | `#375a7f` | `#d6e0ee` | Darker rugged blue. Same value as the `HardRelPri` badge. |
| Soft      | `#6c7682` | `#dde0e5` | Neutral slate.                                            |
| Synergy   | `#5a8088` | `#d8e6e9` | Cyan-teal — categorically different from Hard/Soft.       |

The explain-modal contributors chart and legend use the same edge palette
plus a `Self` tile (`#7a6e62` warm sand) for the node itself.

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
| Compact inline label | `dbc.Label("Name", className="small text-muted mb-0")` | Grouped inputs in a Row (Optimistic, Expected, Pessimistic) |
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
| Editor sidebar width | `380px` |
| Filters panel width | `320px` |
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
`Open`, `Done`, `Blocked`, `HardRelPri`, `SoftRelPri`. Unknown names fall
back to a neutral gray.

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
