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

### Status (via ConfigManager + Bootstrap)
| Name    | Bootstrap `color=` | Hex       |
|---------|--------------------|-----------|
| Open    | `primary`          | `#0d6efd` |
| Done    | `success`          | `#198754` |
| Blocked | `danger`           | `#dc3545` |
| Goal    | `warning`          | `#ffc107` |
| Danger  | (custom)           | `#c94c4c` |

### Selection (Cytoscape)
| Token           | Hex       |
|-----------------|-----------|
| selected-node   | `#0dcaf0` |
| selected-border | `#055160` |

## Typography

### Heading Hierarchy
| Level | Element | Style | Usage |
|-------|---------|-------|-------|
| Page title | `html.H4` | `className="mb-3 mt-3"` | Top of each tab ("Settings", "Goals") |
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
| Confirm + close | `success` (green) | Save & Close, New Node, New Goal |
| Secondary/reset | `secondary` (gray) | Clear |
| Destructive | `danger` + custom bg | Delete (uses `ConfigManager.get_danger_color()` = `#c94c4c`) |
| Icon/link | `link` | +/- buttons, restore defaults |

### Button sizes
- `size="sm"` — Toolbar, inline actions
- (default) — Form actions (Save, Delete, Clear)
- `size="lg"` + `className="w-100"` — Full-width major actions (Save Settings, Run Simulation)

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
| Goal list panel width | `350px` |
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

```python
dbc.Badge("Status", color="success", style={"fontSize": "0.7rem", "width": "62px", "textAlign": "center"})
```

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

## Z-Index Scale

| Layer | Value |
|-------|-------|
| Context menu | `10000` |
| Tooltip | `9999` |
| Filters overlay | `100` |
