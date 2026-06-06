"""
Shared helper functions for Dash callback modules.

Contains stateless utility functions extracted from callbacks.py to keep
the callback registration files focused on Dash I/O wiring.
"""

import json
import logging

import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

logger = logging.getLogger(__name__)

from config import BADGE_PALETTE, ConfigManager, badge_style
from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_DONE


SECTION_TITLE_STYLE = {"fontSize": "1.3rem", "fontWeight": "600"}


RESTORE_ICON = "↺"  # ↺ anticlockwise open circle arrow


def build_calibration_dismissed_view(manager):
    """List of nodes marked "Don't ask again" during a calibration review,
    each row with a Restore button (pattern-matched id
    `{'type': 'calibration-restore', 'index': <name>}`). Returns a Dash
    component tree suitable for any container — the caller decides where to
    mount it. Used by the Review Hub's Excluded tab."""
    dismissed = sorted(n.name for n in manager.get_all_nodes(include_dormant=True)
                       if n.calibration_dismissed)
    if not dismissed:
        return html.Small("Nothing excluded.", className="text-muted d-block")
    rows = []
    for name in dismissed:
        rows.append(html.Div([
            html.Span(name, className="text-truncate"),
            dbc.Button(RESTORE_ICON,
                       id={'type': 'calibration-restore', 'index': name},
                       color="link", size="sm",
                       className="p-0 ms-2 text-decoration-none",
                       style={"fontSize": "1.1rem", "lineHeight": "1",
                              "color": "#adb5bd"}),
            dbc.Tooltip("Restore", target={'type': 'calibration-restore', 'index': name},
                        placement="right"),
        ], className="d-flex align-items-center mb-1"))
    return html.Div(rows)


_CONTEXT_WEIGHTS_PER_COLUMN = 3


def build_context_weight_rows(contexts, ctx_weights):
    """Build the per-context weight input rows for the Scoring settings tab.

    Rows are chunked into fixed-height columns (``_CONTEXT_WEIGHTS_PER_COLUMN``
    each) laid out left-to-right, so the inputs fill the horizontal dead space
    instead of stacking in one tall column.
    """
    def make_cells(ctx_name):
        # Label + input as sibling grid items so the grid aligns them: labels
        # left-aligned (column hugs the left margin), inputs share a column.
        return [
            dbc.Label(ctx_name, className="mb-0"),
            dbc.Input(
                id={"type": "setting-context-weight", "index": ctx_name},
                type="number", min=0, max=10, step="any",
                value=float(ctx_weights.get(ctx_name, 1.0)),
                style={"width": "120px"},
            ),
        ]

    per_col = _CONTEXT_WEIGHTS_PER_COLUMN
    column_style = {
        "display": "grid",
        # Label track sizes to the longest label in the column; inputs align.
        "gridTemplateColumns": "max-content 120px",
        "columnGap": "0.75rem",
        "rowGap": "0.5rem",
        "alignItems": "center",
        # Keep rows packed at the top so a short last column (e.g. 2 items)
        # leaves blank space below rather than spreading its rows out.
        "alignContent": "start",
    }
    columns = []
    for i in range(0, len(contexts), per_col):
        cells = []
        for ctx_name in contexts[i:i + per_col]:
            cells.extend(make_cells(ctx_name))
        columns.append(html.Div(cells, style=column_style))
    return [html.Div(columns, className="d-flex flex-wrap align-items-start",
                     style={"columnGap": "3rem", "rowGap": "0.5rem"})]


def compute_orphaned_subcontext_pairs(old_subcontexts, new_subcontexts, new_contexts):
    """(ctx, sub) pairs present in old but not in new, where ctx still exists in new_contexts.

    Subcontexts are identified by (context, subcontext) tuple — the same name under a
    different parent is a distinct pair. Pairs whose parent context is being removed
    are skipped (those nodes are handled by the context-orphan path instead).
    """
    new_contexts_set = set(new_contexts)
    pairs = []
    for ctx, subs in old_subcontexts.items():
        if ctx not in new_contexts_set:
            continue
        new_subs = set(new_subcontexts.get(ctx, []))
        for sub in subs:
            if sub not in new_subs:
                pairs.append((ctx, sub))
    return pairs


def detect_context_renames(old_contexts, new_contexts, old_subcontexts, new_subcontexts):
    """Detect 1:1 context renames where the new context preserves all old subcontexts.

    Returns {old_ctx: new_ctx} when exactly one context was removed and exactly one
    was added, AND the new context's subcontexts are a superset of the old's. This
    is conservative on purpose — false positives would silently merge unrelated
    contexts. Anything ambiguous returns {} so the user disambiguates in the modal.
    """
    removed = [c for c in old_contexts if c not in set(new_contexts)]
    added = [c for c in new_contexts if c not in set(old_contexts)]
    if len(removed) != 1 or len(added) != 1:
        return {}
    old_ctx, new_ctx = removed[0], added[0]
    old_subs = set(old_subcontexts.get(old_ctx, []))
    new_subs = set(new_subcontexts.get(new_ctx, []))
    if not old_subs.issubset(new_subs):
        return {}
    return {old_ctx: new_ctx}


def _get_duplicate_stop_words():
    """Get stop words for duplicate comparison from linter settings."""
    linter = ConfigManager.get_titlecase_linter()
    exclusions = linter.get('exclusions', [])
    if exclusions:
        return {w.lower() for w in exclusions}
    # Fallback defaults
    return {
        "a", "an", "or", "not", "with", "the", "but", "and", "vs", "vs.",
        "at", "of", "are", "as", "is", "in", "to", "for", "on", "from",
        "by", "about", "into", "it",
    }


def normalize_name_for_comparison(name):
    """Strip stop/connector words and lowercase for fuzzy duplicate comparison.

    Uses the linter exclusion list from Settings so the user controls which
    words are ignored during duplicate detection.
    """
    if not name:
        return ""
    stop_words = _get_duplicate_stop_words()
    words = name.lower().split()
    return " ".join(w for w in words if w not in stop_words)


# --- Google Drive Path Helpers ---

def _gdrive_prefix():
    """Return the configured Google Drive root path, normalized with a trailing separator."""
    import os
    prefix = (ConfigManager.get_gdrive_path() or '').strip()
    if prefix and not prefix.endswith(os.sep) and not prefix.endswith('/'):
        prefix += os.sep
    return prefix


def strip_gdrive_prefix(links):
    """Strip the configured GDrive root prefix from each path in a list."""
    prefix = _gdrive_prefix()
    if not prefix:
        return links
    result = []
    for p in (links or []):
        if p and p.startswith(prefix):
            result.append(p[len(prefix):])
        else:
            result.append(p)
    return result


def expand_gdrive_prefix(path):
    """Prepend the configured GDrive root prefix to a relative path if it lacks one."""
    import os
    if not path or not path.strip():
        return path
    path = path.strip()
    prefix = _gdrive_prefix()
    if not prefix:
        return path
    # Already absolute — don't double-prefix
    if os.path.isabs(path) or path.startswith('http://') or path.startswith('https://'):
        return path
    return prefix + path


# --- Serialization Helpers ---

def parse_links(db_value):
    """Parse a DB field that may contain a JSON array or a plain string into a list."""
    if not db_value:
        return ['']
    try:
        parsed = json.loads(db_value)
        if isinstance(parsed, list):
            return parsed if parsed else ['']
    except (ValueError, TypeError):
        pass
    return [db_value]


def serialize_links(values_list):
    """Serialize a list of link input values into a JSON string for DB storage."""
    if not values_list:
        return None
    links = [v.strip() for v in values_list if v and v.strip()]
    if not links:
        return None
    return json.dumps(links)


# --- Callback Utilities ---

def get_trigger_id():
    """Return the component ID that triggered the current callback, or '' if none."""
    triggered = dash.callback_context.triggered
    return triggered[0]['prop_id'].split('.')[0] if triggered else ""


def get_all_triggered_ids(triggered_props=None):
    """Return the set of ALL component IDs that fired in this callback cycle.

    When multiple Dash Inputs change within the same update cycle (e.g. a
    double-click fires both tapNodeData and edit-trigger-input), only
    ``triggered[0]`` is returned by :func:`get_trigger_id`.  This helper
    exposes the full set so callers can detect batched triggers.
    """
    if triggered_props is None:
        triggered_props = dash.callback_context.triggered
    return {t['prop_id'].split('.')[0] for t in triggered_props}


def should_open_editor(all_triggered_ids, trigger_id, search_val):
    """Decide whether the sidebar editor should slide open.

    Checks ALL triggered IDs (not just the primary) so that an edit trigger
    batched with tapNodeData in the same Dash cycle still opens the sidebar.
    """
    return bool(all_triggered_ids & {'btn-edit-node', 'edit-trigger-input', 'details-edit-trigger-input'}) or \
           (trigger_id == 'search-node' and bool(search_val))


def resolve_active_node_id(all_triggered_ids, trigger_id, edit_trigger_data,
                           search_val, tapped_node, current_name):
    """Determine which node the editor should display.

    Prefers ``edit-trigger-input`` (carries the node ID explicitly) even when
    it is batched with another trigger like tapNodeData.
    """
    if ('edit-trigger-input' in all_triggered_ids or 'details-edit-trigger-input' in all_triggered_ids) and edit_trigger_data:
        return edit_trigger_data.split('|')[0]
    if trigger_id in ('background-click-input', 'btn-editor-new'):
        return None
    if trigger_id == 'search-node' and search_val:
        if search_val.startswith('alias:'):
            from graph_manager import GraphManager
            _mgr = GraphManager()
            alias_key = search_val[6:]
            # Case-insensitive resolve so 'alias:mathnotes' finds 'MathNotes'.
            resolved = _mgr.resolve_alias(alias_key)
            return resolved if resolved is not None else search_val
        return search_val
    if trigger_id == 'cytoscape-graph' and tapped_node:
        return tapped_node.get('id')
    return current_name


def node_options(nodes, exclude=None):
    """Build dropdown options from a list of nodes, optionally excluding one by name."""
    return [{'label': n.name, 'value': n.name} for n in nodes if n.name != exclude]


def build_filters(f_context, f_subcontext, f_done, f_value=1, f_interest=1,
                  f_time=None, f_difficulty="All", f_node_types=None,
                  f_time_unit="hours", f_show_dormant=None):
    """Build a filter dict from sidebar filter component values for use with GraphManager.filter_nodes()."""
    filters = {}

    # Show-dormant gate: when the sidebar's "Show Dormant" switch is on, this
    # flag flows into filter_nodes which then keeps dormant rows in the
    # filtered set. Default off matches the original "dormant nodes are
    # hidden from the main canvas" behavior.
    if f_show_dormant and "show_dormant" in f_show_dormant:
        filters['show_dormant'] = True

    contexts = []
    if f_context and f_context != "All":
        if isinstance(f_context, list):
            contexts = f_context
        elif f_context != "None":
            contexts = [f_context]
        else:
            contexts = [None]

    # Subcontext dropdown values are encoded as "ctx\x1fsub" composites by
    # update_filter_subcontexts so the (value -> context) mapping is explicit.
    # ASCII unit-separator (\x1f) is used instead of "::" because Dash mangles
    # values containing "::" during layout serialization. Plain strings
    # (legacy state / test fixtures that haven't adopted composites) are
    # accepted as context-agnostic subcontext names.
    ctx_to_subs: dict = {}
    plain_subs: list = []
    if f_subcontext and f_subcontext != "All":
        values = f_subcontext if isinstance(f_subcontext, list) else [f_subcontext]
        for v in values:
            if not v or not isinstance(v, str):
                continue
            # Only strip standard ASCII whitespace — NOT all `str.isspace()`
            # chars, because the composite separator \x1f is whitespace by
            # Python's definition and would silently drop the "None" sentinel
            # (`"Body\x1f"` → `"Body"`).
            v = v.strip(" \t\n\r\v\f")
            if not v:
                continue
            if "\x1f" in v:
                c, s = v.split("\x1f", 1)
                ctx_to_subs.setdefault(c, []).append(s if s else None)
            elif "::" in v:
                # Legacy persisted state from before the separator change.
                c, s = v.split("::", 1)
                ctx_to_subs.setdefault(c, []).append(s if s else None)
            else:
                plain_subs.append(v)

    if contexts and ctx_to_subs:
        # Selective union: for each selected context, use the subcontexts the user
        # explicitly tagged to that context. Contexts with no selection fall back
        # to "include all nodes of that context" (per UX introduced in 58b4866:
        # "show all Mind, but only specific STEM").
        pairs = [(c, ctx_to_subs.get(c) or None) for c in contexts]
        filters['context_subcontext_union'] = pairs
    elif contexts and plain_subs:
        # Legacy path: plain subcontext names with contexts selected — apply the
        # bare list against every selected context (pre-composite behavior).
        filters['context_subcontext_union'] = [(c, plain_subs) for c in contexts]
    elif contexts:
        filters['context'] = contexts
    elif ctx_to_subs or plain_subs:
        flat = [s for subs in ctx_to_subs.values() for s in subs] + plain_subs
        filters['subcontext'] = flat
    if f_node_types:
        if isinstance(f_node_types, list):
            if f_node_types:
                filters['node_types'] = f_node_types
        elif f_node_types != "All":
            filters['node_types'] = [f_node_types]
    # "Show Done" switch: ON ("show_done" in f_done) = no filter; OFF
    # (empty list, or any legacy value) = hide done. Default is hidden.
    if not (f_done and "show_done" in f_done):
        filters['hide_done'] = True
    if f_value and f_value > 1:
        filters['min_value'] = f_value
    if f_interest and f_interest > 1:
        filters['min_interest'] = f_interest
    if f_time is not None and f_time != "" and f_time != 0:
        try:
            multiplier = ConfigManager.get_time_multiplier(f_time_unit or "hours")
            filters['max_time'] = float(f_time) * multiplier
        except (ValueError, TypeError) as e:
            logger.warning("Invalid max_time filter (%r, unit=%r): %s", f_time, f_time_unit, e)
    if f_difficulty and f_difficulty != "All":
        try: filters['max_difficulty'] = int(f_difficulty)
        except (ValueError, TypeError) as e:
            logger.warning("Invalid max_difficulty filter (%r): %s", f_difficulty, e)
    return filters


def is_filters_active(*, node_type=None, context=None, subcontext=None,
                      community=None, community_method=None,
                      value=None, interest=None, difficulty=None,
                      time=None, done=None):
    """Returns True if any sidebar filter has a non-default value.

    Defaults match the "Clear Filters" reset state in
    callbacks.clear_filters. Pass None for filters that don't affect the
    calling canvas (e.g. the Details canvas ignores Community)
    so the indicator only fires on filters that actually narrow what
    the user sees.
    """
    if node_type:
        return True
    if context:
        return True
    if subcontext:
        return True
    if community and community != "All":
        return True
    if community_method == "orphans":
        return True
    if value is not None and value > 1:
        return True
    if interest is not None and interest > 1:
        return True
    if difficulty is not None and difficulty < 10:
        return True
    if time:
        return True
    # New default for done is empty list ("Show Done" off → done hidden).
    # Anything non-default — including legacy "hide_done" left over from
    # before the relabel — is treated as user-touched.
    if done is not None and list(done) != []:
        return True
    return False


# --- Habit-mode time conversion ---


def _habit_day_count(days) -> int:
    """Count selected weekdays from a list/tuple or comma-separated string."""
    if days is None:
        return 0
    if isinstance(days, (list, tuple, set)):
        return len([d for d in days if d is not None and str(d).strip() != ''])
    return len([p for p in str(days).split(',') if p.strip() != ''])


def habit_to_hours(duration: float, duration_unit: str,
                   intensity: float, intensity_unit: str, days=None) -> float:
    """Convert a (duration, intensity) habit estimate to total hours.

    intensity_unit is '{min|hr}_per_{day|week|session}'. duration_unit is one
    of 'days' / 'weeks' / 'months' / 'years'. Months use a 30-day approximation
    and years use 365 — the blend is for ROI cost, not calendar precision.

    For the '_per_session' cadence, ``days`` selects which weekdays the session
    happens on (a list of indices or a comma-separated string); the per-session
    amount is applied on each selected day. Selecting all seven days reproduces
    the legacy '_per_day' total. Returns 0.0 if either side is zero.
    """
    if not duration or not intensity:
        return 0.0
    if duration_unit == 'weeks':
        days_total = float(duration) * 7
    elif duration_unit == 'months':
        days_total = float(duration) * 30
    elif duration_unit == 'years':
        days_total = float(duration) * 365
    else:
        days_total = float(duration)
    # Per-session cadence: the amount applies on each selected weekday, so the
    # number of weekly sessions scales the total. All seven days ⇒ identical to
    # the legacy per-day total.
    if intensity_unit and intensity_unit.endswith('_per_session'):
        num_days = _habit_day_count(days)
        if num_days == 0:
            return 0.0
        hours_per_session = (
            float(intensity) / 60.0
            if intensity_unit.startswith('min') else float(intensity)
        )
        sessions = (days_total / 7.0) * num_days
        return round(sessions * hours_per_session, 2)
    parts = (intensity_unit or 'min_per_day').split('_per_')
    mag_unit, period = parts[0], (parts[1] if len(parts) == 2 else 'day')
    hours_per_mag = (1 / 60.0) if mag_unit == 'min' else 1.0
    if period == 'week':
        hours_per_day = float(intensity) * hours_per_mag / 7.0
    else:
        hours_per_day = float(intensity) * hours_per_mag
    return round(days_total * hours_per_day, 2)


def compute_habit_time_omp(duration, duration_unit,
                           int_o, int_m, int_p, intensity_unit, days=None):
    """Convert PERT bands on intensity into PERT bands on total hours."""
    return (
        habit_to_hours(duration, duration_unit, int_o, intensity_unit, days),
        habit_to_hours(duration, duration_unit, int_m, intensity_unit, days),
        habit_to_hours(duration, duration_unit, int_p, intensity_unit, days),
    )


ALL_WEEKDAYS = [0, 1, 2, 3, 4, 5, 6]


def parse_habit_days(days):
    """Normalize stored/widget weekday data to a list of ints (0-6).

    Accepts a list/tuple of ints or a comma-separated string. None falls back
    to all seven days (the safe default for rows predating the column)."""
    if days is None:
        return list(ALL_WEEKDAYS)
    if isinstance(days, (list, tuple, set)):
        seq = days
    else:
        seq = str(days).split(',')
    out = []
    for x in seq:
        s = str(x).strip()
        if s.lstrip('-').isdigit():
            d = int(s)
            if 0 <= d <= 6:
                out.append(d)
    return out


def habit_editor_view(intensity_unit, int_o, int_m, int_p, habit_days):
    """Map stored habit fields to the minutes-per-session editor widgets.

    The editor expresses cadence as minutes per session over a set of weekdays,
    so every stored breakdown is normalized to that form. Hour-based legacy
    amounts are converted to minutes (×60). Legacy ``*_per_day`` units map to
    all seven days; legacy ``*_per_week`` units spread the weekly amount across
    seven days. The computed total hours are preserved in every case.
    Returns ``(unit, o, m, p, days_list)`` with unit always ``min_per_session``.
    """
    unit = intensity_unit or 'min_per_day'
    o, m, p = (int_o or 0), (int_m or 0), (int_p or 0)
    if unit.startswith('hr'):
        o, m, p = o * 60, m * 60, p * 60
    if unit.endswith('_per_session'):
        return 'min_per_session', o, m, p, parse_habit_days(habit_days)
    if unit.endswith('_per_week'):
        return ('min_per_session', round(o / 7.0, 4), round(m / 7.0, 4),
                round(p / 7.0, 4), list(ALL_WEEKDAYS))
    # per_day (or anything unrecognized): every day, amount unchanged.
    return 'min_per_session', o, m, p, list(ALL_WEEKDAYS)


def habit_preview_text(duration, dur_unit, intensity_m, int_unit, days=None):
    """Human-readable live preview of the habit estimate's total hours."""
    int_unit = int_unit or 'min_per_session'
    total = habit_to_hours(duration or 0, dur_unit or 'weeks',
                           intensity_m or 0, int_unit, days)
    if total <= 0:
        return ""
    if int_unit.endswith('_per_session'):
        n = _habit_day_count(days)
        mag = 'min' if int_unit.startswith('min') else 'hr'
        day_str = f"{n} day{'' if n == 1 else 's'}/wk"
        dur_str = f"{(duration or 0):g} {dur_unit or 'weeks'}"
        return (f"≈ {round(total, 1)} h total — "
                f"{(intensity_m or 0):g} {mag} × {day_str} × {dur_str}")
    return f"Computes to ~{round(total, 1)} h total"


def resolve_time_mode(n_type, time_mode_val, time_habit_mode_val):
    """Map node type + form widget values to the canonical time_mode string.

    Goal and Milestone are container types whose time is the sum of their
    children's; they must always use ``time_mode='inherited'``. The editor
    locks the toggle for these types, but this resolver is the canonical
    server-side enforcement — used by every save path (main editor,
    dormant-node creation, details-panel save) so that any future caller
    (convert-type, programmatic save, etc.) can't accidentally bypass the
    invariant. Otherwise, habit > inherited > manual.
    """
    if n_type in ('Goal', 'Milestone'):
        return 'inherited'
    if time_habit_mode_val and 'habit' in time_habit_mode_val:
        return 'habit'
    if time_mode_val and 'inherited' in time_mode_val:
        return 'inherited'
    return 'manual'


def resolve_value_mode(n_type, value_mode_val):
    """Map node type + the value-inherit toggle to the canonical value_mode.

    Milestones are transparent checkpoints whose own value/interest/effort
    must not enter scoring, so they always use ``value_mode='inherited'``.
    The editor locks the toggle for Milestones, but this resolver is the
    canonical server-side enforcement — used by every save path (main editor,
    details-panel add, dormant-node creation) so no caller can bypass the
    invariant. ``Node.__post_init__`` enforces the same rule as a final
    safety net.

    Unlike ``resolve_time_mode``, Goals are NOT forced here: a Goal carries
    its own value and interest (see docs/modeling.md), which feed the Goal
    ranking. Only Milestones are transparent. Otherwise the toggle wins.
    """
    if n_type == 'Milestone':
        return 'inherited'
    if value_mode_val and 'inherited' in value_mode_val:
        return 'inherited'
    return 'manual'


# --- Editor Dirty-State Check (snapshot-based) ---


def _norm_str(s):
    return (s or '').strip()


def _norm_list(lst):
    """Canonicalize a list: drop empty strings, sort."""
    return sorted([v for v in (lst or []) if v])


# Pristine snapshot for the new-node form — mirrors the def_out defaults
# emitted by populate_editor when the user clicks "+ New Node".
NEW_NODE_SNAPSHOT = {
    'name': '', 'n_type': 'Learn', 'desc': '',
    'context': '', 'subctx': '',
    'status_done': [],
    'val': 5, 'interest': 5, 'diff': 5,
    'time_o': 2, 'time_m': 4, 'time_p': 6, 'time_unit': 'weeks',
    'e_needs_h': [], 'e_needs_s': [],
    'e_supp_h': [], 'e_supp_s': [], 'e_helps': [],
    'obs_links': [''], 'drive_links': [''], 'website_links': [''],
    'time_mode': [],
    'time_habit_mode': [],
    'habit_duration': 0,
    'habit_duration_unit': 'weeks',
    'habit_intensity_o': 0, 'habit_intensity_m': 0, 'habit_intensity_p': 0,
    'habit_intensity_unit': 'min_per_session',
    'habit_days': list(ALL_WEEKDAYS),
    'value_mode': [],
    'priority_rank': 'none',
    'aliases': [''],
}


def build_editor_snapshot(manager, node_name):
    """Build a snapshot of the editor form state for an existing node.

    The snapshot dict mirrors exactly what populate_editor writes into the form
    fields, *including* any post-display transformations (e.g. Drive paths after
    strip_gdrive_prefix). The dirty check compares form State against this
    snapshot so display transformations don't produce false-positives.

    Returns None if the node doesn't exist.
    """
    # Local import — _friendly_time_estimates lives in callbacks.py which
    # imports from this module, so we defer to avoid a circular import.
    from callbacks import _friendly_time_estimates

    node = manager.get_node(node_name) if node_name else None
    if node is None:
        return None

    edges = manager.get_edges()
    # The editor's edge dropdowns get their options from manager.get_all_nodes(),
    # which excludes dormant nodes. A dcc.Dropdown silently filters its `value`
    # to entries present in `options`, so any edge to/from a dormant node is
    # invisible to the form's State. The snapshot must mirror this filter, or
    # the dirty check fires every X-close on nodes with dormant prerequisites.
    non_dormant_names = {n.name for n in manager.get_all_nodes()}
    needs_h = sorted({e['source'] for e in edges
                      if e['target'] == node_name and e['type'] == EDGE_NEEDS_HARD
                      and e['source'] in non_dormant_names})
    needs_s = sorted({e['source'] for e in edges
                      if e['target'] == node_name and e['type'] == EDGE_NEEDS_SOFT
                      and e['source'] in non_dormant_names})
    supp_h = sorted({e['target'] for e in edges
                     if e['source'] == node_name and e['type'] == EDGE_NEEDS_HARD
                     and e['target'] in non_dormant_names})
    supp_s = sorted({e['target'] for e in edges
                     if e['source'] == node_name and e['type'] == EDGE_NEEDS_SOFT
                     and e['target'] in non_dormant_names})
    helps_set = {e['target'] for e in edges
                 if e['source'] == node_name and e['type'] == EDGE_HELPS
                 and e['target'] in non_dormant_names}
    helps_set |= {e['source'] for e in edges
                  if e['target'] == node_name and e['type'] == EDGE_HELPS
                  and e['source'] in non_dormant_names}
    helps = sorted(helps_set)

    priority_goals = ConfigManager.get_priority_goals()
    if node.type == 'Goal' and node.name in priority_goals:
        priority_rank = str(priority_goals.index(node.name) + 1)
    else:
        priority_rank = 'none'

    friendly_o, friendly_m, friendly_p, friendly_unit = _friendly_time_estimates(
        node.time_o, node.time_m, node.time_p
    )

    aliases = manager.get_aliases(node_name) or ['']

    return {
        'name': node.name,
        'n_type': node.type,
        'desc': node.description or '',
        'context': node.context or '',
        'subctx': node.subcontext or '',
        'status_done': [STATUS_DONE] if node.status == STATUS_DONE else [],
        'val': node.value or 5,
        'interest': node.interest or 5,
        'diff': node.difficulty or 5,
        'time_o': friendly_o,
        'time_m': friendly_m,
        'time_p': friendly_p,
        'time_unit': friendly_unit,
        'e_needs_h': needs_h,
        'e_needs_s': needs_s,
        'e_supp_h': supp_h,
        'e_supp_s': supp_s,
        'e_helps': helps,
        # Drive paths are stripped of the configured GDrive root prefix in
        # render_drive_links before display, so the form's State value is the
        # stripped form. Snapshot must match.
        'obs_links': parse_links(node.obsidian_path),
        'drive_links': strip_gdrive_prefix(parse_links(node.google_drive_path)),
        'website_links': parse_links(node.website),
        'time_mode': ['inherited'] if node.time_mode == 'inherited' else [],
        'time_habit_mode': ['habit'] if node.time_mode == 'habit' else [],
        'habit_duration': node.habit_duration or 0,
        'habit_duration_unit': node.habit_duration_unit or 'weeks',
        **(lambda hu, ho, hm, hp, hd: {
            'habit_intensity_o': ho, 'habit_intensity_m': hm,
            'habit_intensity_p': hp, 'habit_intensity_unit': hu,
            'habit_days': hd,
        })(*habit_editor_view(
            node.habit_intensity_unit, node.habit_intensity_o,
            node.habit_intensity_m, node.habit_intensity_p, node.habit_days)),
        'value_mode': ['inherited'] if node.value_mode == 'inherited' else [],
        'priority_rank': priority_rank,
        'aliases': aliases,
    }


def snapshot_from_form_state(form_values, linted_name, linted_aliases):
    """Build a pristine snapshot directly from the form State just saved.

    Unlike build_editor_snapshot (DB round-trip + display transforms),
    this snapshots what the form actually holds — so the post-save dirty
    check can't trip on heuristic drift (e.g. _friendly_time_estimates
    picking a different time_unit from DB hours than the user selected).

    linted_name / linted_aliases are the only values the app legitimately
    rewrites in the form after save (via the title-case linter). Pass them
    in so the snapshot agrees with the form's post-save rewritten state.
    """
    return {
        'name': linted_name,
        'n_type': form_values.get('n_type'),
        'desc': form_values.get('desc') or '',
        'context': form_values.get('context') or '',
        'subctx': form_values.get('subctx') or '',
        'status_done': form_values.get('status_done') or [],
        'val': form_values.get('val', 5),
        'interest': form_values.get('interest', 5),
        'diff': form_values.get('diff', 5),
        'time_o': form_values.get('time_o'),
        'time_m': form_values.get('time_m'),
        'time_p': form_values.get('time_p'),
        'time_unit': form_values.get('time_unit'),
        'e_needs_h': form_values.get('e_needs_h') or [],
        'e_needs_s': form_values.get('e_needs_s') or [],
        'e_supp_h': form_values.get('e_supp_h') or [],
        'e_supp_s': form_values.get('e_supp_s') or [],
        'e_helps': form_values.get('e_helps') or [],
        'obs_links': form_values.get('obs_links') or [''],
        'drive_links': form_values.get('drive_links') or [''],
        'website_links': form_values.get('website_links') or [''],
        'time_mode': form_values.get('time_mode') or [],
        'time_habit_mode': form_values.get('time_habit_mode') or [],
        'habit_duration': form_values.get('habit_duration') or 0,
        'habit_duration_unit': form_values.get('habit_duration_unit') or 'weeks',
        'habit_intensity_o': form_values.get('habit_intensity_o') or 0,
        'habit_intensity_m': form_values.get('habit_intensity_m') or 0,
        'habit_intensity_p': form_values.get('habit_intensity_p') or 0,
        'habit_intensity_unit': form_values.get('habit_intensity_unit') or 'min_per_session',
        'habit_days': form_values.get('habit_days') or list(ALL_WEEKDAYS),
        'value_mode': form_values.get('value_mode') or [],
        'priority_rank': form_values.get('priority_rank') or 'none',
        'aliases': linted_aliases or [''],
    }


def editor_form_values(
    *,
    name, n_type, desc, context, subctx, status_done,
    val, interest, diff,
    time_o, time_m, time_p, time_unit,
    e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
    obs_links, drive_links, website_links,
    time_mode, value_mode, priority_rank, aliases,
    time_habit_mode=None,
    habit_duration=0, habit_duration_unit='weeks',
    habit_intensity_o=0, habit_intensity_m=0, habit_intensity_p=0,
    habit_intensity_unit='min_per_session',
    habit_days=None,
):
    """Assemble the canonical editor form-values dict for the dirty check.

    This is the single source of truth for the key set that
    is_form_dirty_vs_snapshot compares against a snapshot. Every call site that
    needs a dirty check must build its form dict through here, so the schema
    can't drift per-call-site. Per-call-site drift — a call site omitting a
    field that the snapshot carries — was the historical cause of spurious
    "unsaved changes" prompts: an omitted field read back as a coercion default
    that disagreed with the snapshot, flagging an unchanged form as dirty.

    All args are keyword-only so a forgotten field is a loud TypeError at the
    call site rather than a silent omission. The habit_* defaults mirror the
    editor's component defaults (see sidebars_layout.py) so they stay aligned
    with NEW_NODE_SNAPSHOT for any caller that legitimately has no habit state.
    """
    return {
        'name': name, 'n_type': n_type, 'desc': desc,
        'context': context, 'subctx': subctx,
        'status_done': status_done,
        'val': val, 'interest': interest, 'diff': diff,
        'time_o': time_o, 'time_m': time_m, 'time_p': time_p,
        'time_unit': time_unit,
        'e_needs_h': e_needs_h, 'e_needs_s': e_needs_s,
        'e_supp_h': e_supp_h, 'e_supp_s': e_supp_s, 'e_helps': e_helps,
        'obs_links': obs_links, 'drive_links': drive_links,
        'website_links': website_links,
        'time_mode': time_mode,
        'time_habit_mode': time_habit_mode,
        'habit_duration': habit_duration,
        'habit_duration_unit': habit_duration_unit,
        'habit_intensity_o': habit_intensity_o,
        'habit_intensity_m': habit_intensity_m,
        'habit_intensity_p': habit_intensity_p,
        'habit_intensity_unit': habit_intensity_unit,
        'habit_days': habit_days if habit_days is not None else list(ALL_WEEKDAYS),
        'value_mode': value_mode,
        'priority_rank': priority_rank,
        'aliases': aliases,
    }


def is_form_dirty_vs_snapshot(snapshot, form_values):
    """Compare current editor form State to the pristine snapshot.

    snapshot:    dict from build_editor_snapshot / NEW_NODE_SNAPSHOT, or None.
    form_values: dict of current State values keyed the same as the snapshot.
                 Build it via editor_form_values() so the key set can't drift.

    Returns False if snapshot is None — no baseline means we can't tell, and
    treating as not-dirty lets the X button always close in that edge case.
    """
    if snapshot is None:
        return False

    # Scalar string fields — strip whitespace before comparing.
    for k in ('name', 'desc', 'context', 'subctx'):
        if _norm_str(form_values.get(k)) != _norm_str(snapshot.get(k)):
            return True

    # Type / time_unit / priority_rank / habit unit selectors — direct
    # equality with empty-coercion.
    if (form_values.get('n_type') or '') != (snapshot.get('n_type') or ''):
        return True
    if (form_values.get('time_unit') or '') != (snapshot.get('time_unit') or ''):
        return True
    if (form_values.get('priority_rank') or 'none') != (snapshot.get('priority_rank') or 'none'):
        return True
    if (form_values.get('habit_duration_unit') or 'weeks') != (snapshot.get('habit_duration_unit') or 'weeks'):
        return True
    if (form_values.get('habit_intensity_unit') or 'min_per_session') != (snapshot.get('habit_intensity_unit') or 'min_per_session'):
        return True

    # Integer fields with a default-of-5 convention.
    for k in ('val', 'interest', 'diff'):
        if int(form_values.get(k) or 5) != int(snapshot.get(k) or 5):
            return True

    # Time fields — compare with 2-decimal rounding to match form display.
    for k in ('time_o', 'time_m', 'time_p',
              'habit_duration',
              'habit_intensity_o', 'habit_intensity_m', 'habit_intensity_p'):
        if round(float(form_values.get(k) or 0), 2) != round(float(snapshot.get(k) or 0), 2):
            return True

    # Checkbox-list fields — set comparison (weekday picker order-insensitive).
    for k in ('status_done', 'time_mode', 'time_habit_mode', 'value_mode',
              'habit_days'):
        if set(form_values.get(k) or []) != set(snapshot.get(k) or []):
            return True

    # Multi-value list fields — drop empties, sort, compare.
    for k in ('e_needs_h', 'e_needs_s', 'e_supp_h', 'e_supp_s', 'e_helps',
              'obs_links', 'drive_links', 'website_links', 'aliases'):
        if _norm_list(form_values.get(k)) != _norm_list(snapshot.get(k)):
            return True

    return False


# --- Node CRUD Helpers ---

def handle_save(manager, name, n_type, desc, val, time_o, time_m, time_p, interest, diff,
                status_done, context, subctx, obs_path, drive_path, website_path,
                e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps,
                time_mode='manual', value_mode='manual',
                habit_duration=0.0, habit_duration_unit='weeks',
                habit_intensity_o=0.0, habit_intensity_m=0.0, habit_intensity_p=0.0,
                habit_intensity_unit='min_per_day', habit_days=None):
    """Create or update a node and sync its edges. Returns a status message.

    Caller is responsible for converting habit-mode inputs to time_o/m/p
    before calling — this function just persists what it's given. The
    habit_* fields are stored alongside time_o/m/p so the editor can
    repopulate the habit form on re-open.
    """
    from models import Node

    target_status = STATUS_DONE if (status_done and STATUS_DONE in status_done) else STATUS_OPEN

    ctx = context or None
    sub = (subctx or '').strip() or None
    if ctx is None:
        sub = None
    elif sub is not None and sub not in ConfigManager.get_subcontexts().get(ctx, []):
        sub = None

    node = Node(
        name=name, type=n_type, description=desc or "",
        value=val, time_o=time_o or 0, time_m=time_m or 0, time_p=time_p or 0,
        interest=interest, difficulty=diff,
        status=target_status, context=ctx, subcontext=sub,
        obsidian_path=(obs_path or '').strip() or None,
        google_drive_path=(drive_path or '').strip() or None,
        website=(website_path or '').strip() or None,
        time_mode=time_mode,
        value_mode=value_mode,
        habit_duration=habit_duration or 0,
        habit_duration_unit=habit_duration_unit or 'weeks',
        habit_intensity_o=habit_intensity_o or 0,
        habit_intensity_m=habit_intensity_m or 0,
        habit_intensity_p=habit_intensity_p or 0,
        habit_intensity_unit=habit_intensity_unit or 'min_per_day',
        **({'habit_days': habit_days} if habit_days is not None else {}),
    )
    existing = manager.get_node(name)
    if existing:
        # Preserve fields that aren't represented in the editor form, otherwise
        # update_node would overwrite them with the Node dataclass defaults.
        node.dormant = existing.dormant
        node.actual_time_lower = existing.actual_time_lower
        node.actual_time_upper = existing.actual_time_upper
        node.actual_time_point = existing.actual_time_point
        node.actual_time_unit = existing.actual_time_unit
        node.calibration_dismissed = existing.calibration_dismissed
        # The Now flag is mutated by dispatch_now_toggle (a direct DB
        # write outside this form), so preserve the latest DB value. Same
        # for the lifecycle dates and reflection columns — set elsewhere or
        # not yet wired into the editor.
        node.now = existing.now
        node.start_date = existing.start_date
        node.done_date = existing.done_date
        node.reflect_value = existing.reflect_value
        node.reflect_interest = existing.reflect_interest
        node.reflect_difficulty = existing.reflect_difficulty
        manager.update_node(node)
        msg = f"Updated node '{name}'"
    else:
        manager.add_node(node)
        msg = f"Added node '{name}'"
    manager.sync_edges(name, e_needs_h, e_needs_s, e_supp_h, e_supp_s, e_helps)
    return msg


def handle_delete(manager, name):
    """Delete a single node by name. Returns a status message."""
    manager.delete_node(name)
    return f"Deleted node '{name}'"


def handle_toggle_done(manager, tapped_node):
    """Toggle a node's status between Done and Open. Returns a status message."""
    node = manager.get_node(tapped_node.get('id'))
    if node:
        node.status = STATUS_OPEN if node.status == STATUS_DONE else STATUS_DONE
        manager.update_node(node)
        return f"Toggled status of '{node.name}' to {node.status}"
    return ""


def handle_group_delete(manager, group_delete_data):
    """Delete multiple nodes from a JSON-encoded list. Returns a status message."""
    # JS sends '["name1","name2"]|timestamp' — strip the timestamp suffix
    raw = group_delete_data.split('|')[0] if isinstance(group_delete_data, str) else ''
    names = json.loads(raw) if raw else []
    for node_name in names:
        manager.delete_node(node_name)
    return f"Deleted {len(names)} node(s)" if names else ""


# --- UI Formatting Helpers ---

def _bool_icon(val):
    """Render a boolean as a styled checkmark or cross."""
    if val:
        return html.Span("\u2713", style={"color": "#198754", "fontWeight": "bold"})
    return html.Span("\u2717", style={"color": "#dc3545"})


_MONO_FONT = "ui-monospace, SFMono-Regular, Menlo, monospace"


def _suggestion_micro_bar(val, label):
    """One bar of the V/I/E micro-chart (6×22 track with bottom-anchored fill, native title tooltip)."""
    try:
        raw = float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        raw = 0.0
    pct = max(0.0, min(100.0, (raw / 10.0) * 100.0))
    display_val = int(raw) if raw == int(raw) else round(raw, 1)
    return html.Span(
        html.Span(style={
            "position": "absolute", "left": 0, "right": 0, "bottom": 0,
            "height": f"{pct}%", "background": "#adb5bd", "borderRadius": "1px",
        }),
        title=f"{label}: {display_val}",
        style={
            "position": "relative", "width": "6px", "height": "22px",
            "background": "rgba(255,255,255,0.06)", "borderRadius": "1px",
            "overflow": "hidden", "display": "inline-block", "cursor": "default",
        },
    )


def _suggestion_dot(on, label, fill_color):
    """One link-presence indicator dot (filled when a link is set, hollow otherwise)."""
    border_color = fill_color if on else "#6c757d"
    return html.Span(
        title=label,
        style={
            "width": "8px", "height": "8px", "borderRadius": "8px",
            "background": fill_color if on else "transparent",
            "border": f"1.2px solid {border_color}",
            "display": "inline-block",
        },
    )


def format_suggestions_table(suggs, manager, selected_node_id=None, override_set=None):
    """Render the top-scored nodes as bar-chart rows with normalized priority scores (0-100).

    Each row encodes:
      - rank (two-digit monospace label, leftmost)
      - name + context line
      - priority bar (color = type, or override color if pinned; length = priority/maxPriority)
      - time + V/I/E micro-chart + Obsidian/Drive/Website link dots
    """
    if not suggs:
        return html.P("No suggestions found based on current filters and graph state.", className="text-muted")

    # When an override pin is active and the suggestion list mixes priority
    # and non-priority nodes, normalize each tier separately so that no
    # non-priority row can display a higher score than the lowest priority
    # row. This is a display-only transform — `priority_score` values and
    # row ordering are unchanged. Tier 1 (overrides) maps to its own
    # [min%, 100] range; tier 2 (non-overrides) maps to [0, tier1_min% - 2],
    # so after rounding the highest non-priority row sits at least one
    # point below the lowest priority row.
    override_names = override_set or set()
    tier1_raw = [getattr(s, 'priority_score', 0) for s in suggs if s.name in override_names]
    tier2_raw = [getattr(s, 'priority_score', 0) for s in suggs if s.name not in override_names]

    if tier1_raw and tier2_raw:
        tier1_max = max(tier1_raw)
        tier1_min = min(tier1_raw)
        tier2_max = max(tier2_raw)
        tier1_min_displayed = (tier1_min / tier1_max * 100) if tier1_max > 0 else 0.0
        tier2_ceiling = max(0.0, tier1_min_displayed - 2.0)

        def normalize(score, is_override):
            if is_override:
                return round((score / tier1_max) * 100, 1) if tier1_max > 0 else 0.0
            return round((score / tier2_max) * tier2_ceiling, 1) if tier2_max > 0 else 0.0
    else:
        max_score = max(tier1_raw + tier2_raw) if (tier1_raw or tier2_raw) else 0

        def normalize(score, is_override=False):
            if max_score == 0:
                return 0.0
            return round((score / max_score) * 100, 1)

    normalized_scores = [
        normalize(getattr(s, 'priority_score', 0), s.name in override_names)
        for s in suggs
    ]
    max_priority = max(normalized_scores) if normalized_scores else 0

    # Bar colors come from the static BADGE_PALETTE (in config.py), NOT the
    # user-configurable canvas Type Colors. See the BADGE_PALETTE comment for
    # the rationale — short version: canvas needs vivid hues, bars need a
    # quieter register, and the two are decoupled by design.
    override_color = BADGE_PALETTE['Override'][0]

    # Fixed name column width — long names ellipsize rather than pushing
    # the bar/meta columns around, which keeps the list scan-friendly.
    name_col_width = 250

    rows = []
    for rank, s in enumerate(suggs, start=1):
        is_selected = (s.name == selected_node_id)
        is_override = bool(override_set and s.name in override_set)

        eff_time = manager.get_effective_time(s.name)

        priority_int = round(normalize(getattr(s, 'priority_score', 0), is_override))
        if max_priority > 0:
            bar_width_pct = max(8.0, (priority_int / max_priority) * 100.0)
        else:
            bar_width_pct = 8.0
        bar_color = override_color if is_override else BADGE_PALETTE.get(s.type, ('#6c757d', '#fff'))[0]

        # Column 1 — rank
        rank_col = html.Div(
            str(rank),
            style={
                "fontFamily": _MONO_FONT, "fontSize": "20px",
                "color": "#6c757d", "textAlign": "center",
                "lineHeight": "1",
            },
        )

        # Column 2 — name + context line
        ctx_text = str(s.context) if s.context else ""
        sub_text = str(s.subcontext) if s.subcontext else ""
        if ctx_text and sub_text:
            ctx_children = [html.Span(ctx_text), html.Span("·", style={"opacity": 0.5, "padding": "0 4px"}), html.Span(sub_text)]
        elif ctx_text:
            ctx_children = [html.Span(ctx_text)]
        elif sub_text:
            ctx_children = [html.Span(sub_text)]
        else:
            ctx_children = []

        name_col = html.Div([
            html.Div(
                html.Span(
                    s.name,
                    style={
                        "fontSize": "14.5px", "color": "#dee2e6",
                        "lineHeight": "1.35",
                    },
                ),
                style={"minWidth": 0, "overflow": "hidden",
                       "whiteSpace": "nowrap", "textOverflow": "ellipsis",
                       "lineHeight": "1.35", "marginBottom": "1px"},
            ),
            html.Div(ctx_children, style={
                "fontSize": "12px", "color": "#6c757d",
                "fontFamily": _MONO_FONT,
                "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
                "lineHeight": "1.35",
            }),
        ], style={"minWidth": 0, "overflow": "hidden"})

        # Column 3 — priority bar
        bar_fill = html.Div(
            html.Span(
                str(priority_int),
                style={
                    "fontFamily": _MONO_FONT, "fontSize": "14px",
                    "fontWeight": 600, "color": "#fff",
                    "textShadow": "0 1px 1px rgba(0,0,0,0.5)",
                },
            ),
            style={
                "width": f"{bar_width_pct}%", "height": "100%",
                "background": bar_color, "borderRadius": "3px",
                "display": "flex", "alignItems": "center",
                "justifyContent": "flex-end", "paddingRight": "10px",
            },
        )
        bar_col = html.Div(
            bar_fill,
            style={
                "position": "relative", "height": "26px",
                "background": "rgba(255,255,255,0.03)",
                "borderRadius": "3px", "overflow": "hidden",
            },
        )

        # Column 4 — time + V/I/E + R/O/D
        # force_one_decimal keeps the column aligned (1.0w / 1.5w / 11.4h
        # all render with the same decimal width).
        time_label = html.Span(
            ConfigManager.format_time_friendly(eff_time, force_one_decimal=True),
            style={"color": "#adb5bd", "minWidth": "52px", "textAlign": "right",
                   "fontSize": "15px"},
        )

        v_val = s.value if s.value is not None else 0
        i_val = getattr(s, 'interest', None) if getattr(s, 'interest', None) is not None else 0
        e_val = s.difficulty if s.difficulty is not None else 0

        micro_chart = html.Span([
            _suggestion_micro_bar(v_val, "Value"),
            _suggestion_micro_bar(i_val, "Interest"),
            _suggestion_micro_bar(e_val, "Effort"),
        ], style={
            "display": "inline-flex", "alignItems": "flex-end",
            "gap": "3px", "height": "22px",
        })

        dots = html.Span([
            _suggestion_dot(bool(getattr(s, 'obsidian_path', None)), "Obsidian", "#dee2e6"),
            _suggestion_dot(bool(getattr(s, 'google_drive_path', None)), "Drive", "#dee2e6"),
            _suggestion_dot(bool(getattr(s, 'website', None)), "Website", "#dee2e6"),
        ], style={"display": "flex", "gap": "6px", "alignItems": "center"})

        meta_col = html.Div([time_label, micro_chart, dots], style={
            "display": "flex", "alignItems": "center", "gap": "32px",
            "fontFamily": _MONO_FONT, "fontSize": "11px",
        })

        row_style = {
            "display": "grid",
            "gridTemplateColumns": f"32px {name_col_width}px 1fr auto",
            "alignItems": "center",
            "gap": "14px",
            "padding": "9px 12px",
            "borderBottom": "1px solid #343a40",
        }
        if is_selected:
            row_style["backgroundColor"] = "#2b3035"

        rows.append(html.Div(
            [rank_col, name_col, bar_col, meta_col],
            id={"type": "suggestion-row", "index": s.name},
            className="suggestion-bar-row",
            style=row_style,
            **{
                "data-obsidian-path": s.obsidian_path or "",
                "data-google-drive-path": s.google_drive_path or "",
            },  # type: ignore[reportArgumentType]
        ))

    bar_list = html.Div(rows, style={"flex": "1", "minWidth": "0"})

    return [bar_list]


def format_now_nodes_section(now_nodes, cap, manager, selected_node_id=None):
    """Render the 'Now' section for the Next tab as a row of rich cards.

    Each Now node gets a wide horizontal card with a left accent bar in
    the node's type color, the name + context/subcontext, a type badge pill,
    time estimate, V/I/E micro-chart, and Obsidian/Drive/Website link dots.
    Cards sit in a responsive flex row (1–3 items).

    When there are no Now nodes the section is suppressed entirely —
    return [] so the Next heading sits at the top of the tab.

    The `cap` argument is accepted for forward-compatibility but no longer
    surfaced — the cap is enforced in the toggle/context-menu callbacks.
    """
    if not now_nodes:
        return []

    heading = html.Div([
        html.H6("Now", className="text-muted mb-0", style=SECTION_TITLE_STYLE),
    ], className="d-flex align-items-center", style={"gap": "12px", "marginBottom": "0.75rem"})

    cards = []
    for n in now_nodes:
        is_selected = (n.name == selected_node_id)
        eff_time = manager.get_effective_time(n.name)
        accent_color = BADGE_PALETTE.get(n.type, ('#6c757d', '#fff'))[0]

        # --- Context / subcontext line ---
        ctx_text = str(n.context) if n.context else ""
        sub_text = str(n.subcontext) if n.subcontext else ""
        if ctx_text and sub_text:
            ctx_children = [
                html.Span(ctx_text),
                html.Span("·", style={"opacity": 0.5, "padding": "0 4px"}),
                html.Span(sub_text),
            ]
        elif ctx_text:
            ctx_children = [html.Span(ctx_text)]
        elif sub_text:
            ctx_children = [html.Span(sub_text)]
        else:
            ctx_children = []

        # --- Time estimate ---
        time_label = html.Span(
            ConfigManager.format_time_friendly(eff_time, force_one_decimal=True),
            style={"color": "#adb5bd", "fontSize": "17px",
                   "fontFamily": _MONO_FONT, "fontWeight": "500",
                   "flexShrink": "0"},
        )

        # --- Top row: name + time ---
        top_row = html.Div([
            html.Div(
                html.Span(
                    n.name,
                    style={"fontSize": "18px", "color": "#dee2e6",
                           "fontWeight": "700", "lineHeight": "1.3"},
                ),
                style={"minWidth": 0, "overflow": "hidden", "whiteSpace": "nowrap",
                       "textOverflow": "ellipsis", "flex": "1"},
            ),
            time_label,
        ], style={
            "display": "flex", "alignItems": "baseline", "gap": "12px",
            "marginBottom": "4px",
        })

        # --- Context subtitle ---
        ctx_line = html.Div(ctx_children, style={
            "fontSize": "12.5px", "color": "#6c757d", "fontFamily": _MONO_FONT,
            "whiteSpace": "nowrap", "overflow": "hidden", "textOverflow": "ellipsis",
            "lineHeight": "1.35",
            "minHeight": "17px",
        }) if ctx_children else html.Div(style={"minHeight": "17px"})

        # --- Card body (right of the accent bar) ---
        card_body = html.Div(
            [top_row, ctx_line],
            style={"flex": "1", "minWidth": 0, "overflow": "hidden"},
        )

        # --- Accent bar (left edge) ---
        accent_bar = html.Div(style={
            "width": "4px",
            "borderRadius": "2px",
            "backgroundColor": accent_color,
            "alignSelf": "stretch",
            "flexShrink": "0",
        })

        # --- Card container ---
        card_style = {
            "display": "flex",
            "gap": "14px",
            "padding": "16px 20px",
            "borderRadius": "6px",
            "backgroundColor": "#2b3035" if is_selected else "#212529",
            "border": f"2px solid #0d6efd" if is_selected else "1px solid #495057",
            "cursor": "pointer",
            "transition": "background-color 0.2s, border-color 0.2s",
            "flex": "0 0 310px",
            "width": "310px",
        }

        cards.append(html.Div(
            [accent_bar, card_body],
            id={"type": "now-row", "index": n.name},
            className="now-card",
            style=card_style,
            **{
                "data-obsidian-path": n.obsidian_path or "",
                "data-google-drive-path": n.google_drive_path or "",
            },  # type: ignore[reportArgumentType]
        ))

    cards_row = html.Div(cards, style={
        "display": "flex",
        "gap": "1rem",
        "marginBottom": "1.5rem",
    })

    return [heading, cards_row]


def format_traversal_ui(tapped_node, active_node_id, manager):
    """Build the dependency chains (hard/soft) and synergies display for the selected node.

    Returns (hard_chains_ui, soft_chains_ui, synergies_ui, description).
    """
    empty_msg = "Select a node to see dependencies."
    hard_ui = html.Div(className="text-muted", children=empty_msg)
    soft_ui = html.Div(className="text-muted", children=empty_msg)
    synergies_ui = html.Div(className="text-muted", children="Select a node to see synergies.")
    description = ""

    node_id = active_node_id or (tapped_node.get('id') if tapped_node else None)

    if not node_id:
        return hard_ui, soft_ui, synergies_ui, description

    node = manager.get_node(node_id)
    if node:
        description = node.description.strip() if node.description else "No description available."
    else:
        description = ""

    typed_chains = manager.get_prerequisite_chains_typed(node_id)

    edges = manager.get_edges()
    synergies = [e['target'] for e in edges if e['source'] == node_id and e['type'] == EDGE_HELPS]
    synergies += [e['source'] for e in edges if e['target'] == node_id and e['type'] == EDGE_HELPS]
    synergies = list(set(synergies))

    hard_items, soft_items = [], []
    for chain, chain_type in typed_chains:
        display_chain = chain[:-1] if chain and chain[-1] == active_node_id else chain
        if display_chain:
            item = html.Div(" \u2192 ".join(display_chain), style={"overflowWrap": "break-word"})
            if chain_type == "Hard":
                hard_items.append(item)
            else:
                soft_items.append(item)

    hard_ui = html.Div(hard_items) if hard_items else html.P("None", className="text-dark")
    soft_ui = html.Div(soft_items) if soft_items else html.P("None", className="text-dark")

    synergies_ui = html.Div([html.Div(s) for s in synergies]) if synergies else html.P("None", className="text-dark")

    return hard_ui, soft_ui, synergies_ui, description


# --- Link Row UI Helper ---

def render_link_rows(links, link_type, has_browse=False, has_open=True):
    """Build a list of input rows for a resource type.

    link_type: e.g. 'obsidian-link', 'drive-link', 'goal-add-obsidian-link'
    The browse/open/remove button IDs are derived from link_type automatically.
    """
    link_list = links or ['']
    prefix = link_type.replace('-link', '')  # e.g. 'obsidian', 'goal-add-obsidian'
    rows = []
    for i, path in enumerate(link_list):
        # The input and its trailing icon button(s) share one bordered shell
        # (.editor-field-group) so the row spans full width and lines up with
        # the other editor fields. Buttons are flat ghost icons (.editor-icon-btn).
        children = [dbc.Input(
            id={"type": link_type, "index": i}, type="text",
            value=path or '', placeholder="Enter path or URL...",
        )]
        if has_browse:
            children.append(dbc.Button(
                html.I(className="bi bi-folder2-open"),
                id={"type": f"btn-{prefix}-browse", "index": i},
                title="Browse", className="editor-icon-btn",
            ))
        if has_open:
            children.append(dbc.Button(
                html.I(className="bi bi-box-arrow-up-right"),
                id={"type": f"btn-{prefix}-open", "index": i},
                title="Open", className="editor-icon-btn",
            ))
        if len(link_list) > 1:
            children.append(dbc.Button(
                html.I(className="bi bi-x-lg"),
                id={"type": f"btn-{link_type}-remove", "index": i},
                title="Remove", className="editor-icon-btn editor-icon-btn-danger",
            ))
        rows.append(html.Div(children, className="d-flex editor-field-group mb-1"))
    return rows


def render_alias_rows(aliases, input_type="alias-input", remove_type="btn-alias-remove"):
    """Build the alias input rows (one unified field per alias, trailing ×).

    Shared by the main node editor and the add-node modals (dormant / subtask);
    callers pass the prefixed pattern-matching id types so each surface keeps
    its own component namespace. Mirrors render_link_rows' visual style.
    """
    alias_list = aliases or ['']
    rows = []
    for i, val in enumerate(alias_list):
        rows.append(html.Div([
            dbc.Input(id={'type': input_type, 'index': i}, type='text',
                      value=val or '', placeholder=''),
            dbc.Button(html.I(className='bi bi-x-lg'),
                       id={'type': remove_type, 'index': i}, title='Remove alias',
                       className='editor-icon-btn editor-icon-btn-danger'),
        ], className='d-flex editor-field-group mb-1'))
    return rows


def spawn_local_file_picker(initial_dir, title, filetypes_list):
    """Launch a blocking Windows file-picker dialog in a subprocess. Returns the selected path or ''."""
    import logging
    import tempfile
    import sys
    import subprocess
    import os

    _logger = logging.getLogger(__name__)
    filetypes_str = str(filetypes_list)
    script = f'''import os
import tkinter as tk
from tkinter import filedialog
import ctypes

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)

abs_path = filedialog.askopenfilename(
    initialdir=r"{initial_dir}",
    title="{title}",
    filetypes={filetypes_str}
)

if abs_path:
    print(os.path.normpath(abs_path), end="")
'''
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(script)
            tmp_path = f.name
        result = subprocess.run([sys.executable, tmp_path], capture_output=True, text=True)
        os.remove(tmp_path)
        return result.stdout.strip()
    except Exception as e:
        _logger.error(f"Error launching file picker: {e}")
        return ""


# ---------------------------------------------------------------------------
# Explain Score modal renderer
# ---------------------------------------------------------------------------

# Maps the `via` field from scoring.explain_score to a bar color.
# Cool & quiet palette. Hard is a darker rugged blue (matches subtasks-
# table Hard and the HardRelPri badge in the node-info stack); Soft
# neutral slate; Synergy cyan-teal (categorically different — mutual,
# multiplicative reinforcement, not a weaker prereq). Self is a warm
# sand off the cool axis entirely so it can't be confused with Soft.
_VIA_COLORS = {
    'Self':    '#685e52',  # warm sand — the node itself, off the edge axis
    'Hard':    '#2a4d6e',  # darker rugged blue (must-have)
    'Soft':    '#576068',  # neutral slate (should-have)
    'Synergy': '#466a78',  # cyan-teal (mutual, multiplicative — categorically different)
}


def _trunc(name: str, max_len: int = 25) -> str:
    """Truncate long names with an ellipsis; full name goes in hover."""
    return name if len(name) <= max_len else name[:max_len - 1] + '\u2026'


def _explain_summary_table(breakdown: dict, normalized):
    """Grouped summary table: Value / Cost / Score.

    Every row maps to a field in scoring.explain_score's output. Edge
    cases: ineligible nodes show '—' for Raw and Normalized and annotate
    with the block reason; leaf nodes show zero-valued downstream rows in
    muted style; inherited-time nodes annotate the Cost row; `normalized`
    may be None (displays '—') when the caller could not determine a
    normalization base.

    Goal breakdowns (`is_goal`, produced by analyze_callbacks.explain_goal)
    are scored on the inverted prereq graph: the cascade rows describe the
    prerequisite subtree rather than what the node unlocks, and the Cost
    section reports beta-compressed prereq-subtree time.
    """
    comp = breakdown['composition']
    cost_info = breakdown['cost']
    boost = breakdown['goal_boost']
    eligible = breakdown['eligible']
    is_goal = breakdown.get('is_goal', False)
    downstream = comp['hard_cascade'] + comp['soft_cascade'] + comp['synergy']

    header_style = {
        "fontWeight": "700",
        "letterSpacing": "0.06em",
        "textTransform": "uppercase",
        "fontSize": "1.05rem",
        "color": "#ffffff",
        "backgroundColor": "#212529",
        "borderTop": "1px solid #495057",
        "paddingTop": "10px",
        "paddingBottom": "8px",
    }
    total_style = {"fontWeight": "600", "borderTop": "1px solid #495057"}
    num_style = {"textAlign": "right", "fontVariantNumeric": "tabular-nums",
                 "whiteSpace": "nowrap"}
    muted_style = {"color": "#adb5bd", "fontSize": "0.88rem"}
    muted_num_style = {**num_style, **muted_style}
    zero_num_style = {**num_style, "color": "#6c757d"}

    def _fmt(v: float) -> str:
        return f"{v:.2f}"

    def _num_cell(v: float, style=None):
        s = dict(style) if style else dict(num_style)
        if abs(v) < 1e-9 and style is not total_style:
            s = dict(zero_num_style)
        return html.Td(_fmt(v), style=s)

    rows = []

    # --- Value section ------------------------------------------------
    rows.append(html.Tr([html.Td("Value", colSpan=2, style=header_style)]))
    rows.append(html.Tr([html.Td("Intrinsic"), _num_cell(comp['iv'])]))

    # Synergy multiplier on intrinsic — kicks in only when at least one
    # synergy partner is Done. Hidden when inactive (multiplier == 1.0)
    # to keep the table tight.
    iv_multiplier = comp.get('iv_multiplier', 1.0)
    iv_mult_contribution = comp.get('iv_multiplier_contribution', 0.0)
    if iv_multiplier > 1.0 + 1e-9:
        done_count = comp.get('done_synergy_count', 0)
        partner_word = "partner" if done_count == 1 else "partners"
        label = f"Synergy multiplier (×{iv_multiplier:.2f}, {done_count} Done {partner_word})"
        rows.append(html.Tr([
            html.Td(label),
            _num_cell(iv_mult_contribution),
        ]))

    # For a Goal the cascade walks the *inverted* graph, so these rows are
    # the value of its prerequisite subtree rather than what it unlocks.
    cascade_label = "Prerequisite subtree" if is_goal else "Downstream"
    rows.append(html.Tr([html.Td(cascade_label), _num_cell(downstream)]))
    for label, value in (
        ("via Hard", comp['hard_cascade']),
        ("via Soft", comp['soft_cascade']),
        ("via Synergy (pair bonus)", comp['synergy']),
    ):
        rows.append(html.Tr([
            html.Td(label, className="ps-4", style=muted_style),
            html.Td(_fmt(value),
                    style=muted_num_style if value > 1e-9 else zero_num_style),
        ]))
    rows.append(html.Tr([
        html.Td("Total", style=total_style),
        html.Td(_fmt(comp['total_value']), style={**num_style, **total_style}),
    ]))

    # --- Cost section -------------------------------------------------
    rows.append(html.Tr([html.Td("Cost", colSpan=2, style=header_style)]))
    if is_goal:
        # A Goal's own perceived cost is meaningless (its time is inherited
        # from children). Cost is instead the time still owed across its
        # hard-prerequisite subtree, beta-compressed — see _rank_goals.
        rows.append(html.Tr([
            html.Td([html.Span("Remaining hard-prereq time"),
                     html.Span(" (summed over the prereq subtree)",
                               style={**muted_style, "marginLeft": "4px"})]),
            html.Td(_fmt(cost_info.get('remaining_time', 0.0)),
                    style=muted_num_style),
        ]))
        rows.append(html.Tr([
            html.Td([html.Span("Perceived cost"),
                     html.Span(" (compressed prereq time)",
                               style={**muted_style, "marginLeft": "4px"})]),
            _num_cell(cost_info['cost']),
        ]))
    else:
        cost_label = [html.Span("Perceived cost")]
        if cost_info['time_overridden']:
            cost_label.append(html.Span(" (container — inherited time treated as 0)",
                                        style={**muted_style, "marginLeft": "4px"}))
        rows.append(html.Tr([
            html.Td(cost_label),
            _num_cell(cost_info['cost']),
        ]))

    # --- Adjustments section (shown only if any multiplier is non-trivial) --
    ctx_adj = breakdown.get('context_adjustment') or {}
    ctx_weight = ctx_adj.get('weight', 1.0)
    density_mult = ctx_adj.get('density_mult', 1.0)
    n_bucket = ctx_adj.get('n_bucket', 1)
    alpha_val = ctx_adj.get('alpha', 0.0)
    has_boost = boost is not None
    has_weight = abs(ctx_weight - 1.0) > 1e-9
    has_density = abs(density_mult - 1.0) > 1e-9
    has_any_adjustment = has_boost or has_weight or has_density

    if has_any_adjustment:
        rows.append(html.Tr([html.Td("Adjustments", colSpan=2, style=header_style)]))
        combined = 1.0
        if has_boost:
            rows.append(html.Tr([
                html.Td([html.Span("Goal Boost"),
                         html.Span(f" (rank #{boost['rank']} · {boost['goal']})",
                                   style={**muted_style, "marginLeft": "4px"})]),
                html.Td(f"\u00d7{boost['multiplier']:.3f}", style=num_style),
            ]))
            combined *= boost['multiplier']
        if has_weight:
            rows.append(html.Tr([
                html.Td("Context Weight"),
                html.Td(f"\u00d7{ctx_weight:.3f}", style=num_style),
            ]))
            combined *= ctx_weight
        if has_density:
            rows.append(html.Tr([
                html.Td([html.Span("Density"),
                         html.Span(f" (n={n_bucket}, \u03b1={alpha_val:.2f})",
                                   style={**muted_style, "marginLeft": "4px"})]),
                html.Td(f"\u00d7{density_mult:.3f}", style=num_style),
            ]))
            combined *= density_mult
        rows.append(html.Tr([
            html.Td("Combined", style=total_style),
            html.Td(f"\u00d7{combined:.3f}", style={**num_style, **total_style}),
        ]))

    # --- Score section ------------------------------------------------
    rows.append(html.Tr([html.Td("Score", colSpan=2, style=header_style)]))
    if eligible:
        raw_label = [html.Span("Raw")]
        if has_any_adjustment:
            raw_label.append(html.Span(
                " (all adjustments applied)",
                style={**muted_style, "marginLeft": "4px"},
            ))
        rows.append(html.Tr([
            html.Td(raw_label),
            _num_cell(breakdown['score']),
        ]))
        norm_display = f"{normalized}" if normalized is not None else "—"
        rows.append(html.Tr([
            html.Td("Normalized"),
            html.Td(norm_display, style=num_style),
        ]))
    else:
        rows.append(html.Tr([
            html.Td([html.Span("Raw"),
                     html.Span(f" (ineligible: {breakdown['block_reason']})",
                               style={**muted_style, "marginLeft": "4px"})]),
            html.Td("—", style=num_style),
        ]))
        rows.append(html.Tr([
            html.Td("Normalized"),
            html.Td("—", style=num_style),
        ]))

    return dbc.Table(
        [html.Tbody(rows)],
        borderless=True, size="sm",
        className="mb-0",
        style={"color": "#dee2e6", "marginTop": "4px"},
    )


def _explain_bar_chart(contributors: list, top_n: int):
    """Horizontal Plotly bar of top-N contributors, colored by `via`.

    Long node names are truncated for the y-axis tick labels (full name
    preserved in hover); `ticksuffix` adds breathing room between labels
    and bar starts — both patterns lifted from analyze_callbacks._trunc.
    """
    rows = list(reversed(contributors[:top_n]))  # Plotly stacks bottom-up
    full_names = [r['name'] for r in rows]
    display_names = [_trunc(n) for n in full_names]
    vals = [r['contribution'] for r in rows]
    colors = [_VIA_COLORS.get(r['via'], '#6c757d') for r in rows]
    bar_texts = [f"{r['contribution']:.2f}" for r in rows]
    customdata = [
        [full_names[i], rows[i]['via'], rows[i]['pct_of_tv'],
         rows[i]['depth'], rows[i]['weight'], rows[i]['iv']]
        for i in range(len(rows))
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=vals, y=display_names,
        orientation='h',
        marker_color=colors,
        text=bar_texts,
        textposition='outside',
        cliponaxis=False,
        customdata=customdata,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Contribution: %{x:.2f} (%{customdata[2]:.1f}% of total value)<br>"
            "Via: %{customdata[1]}<br>"
            "Depth: %{customdata[3]}<br>"
            "Weight: %{customdata[4]:.3f}<br>"
            "Intrinsic value: %{customdata[5]:.2f}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='#1a1d21',
        plot_bgcolor='#1a1d21',
        margin=dict(l=10, r=40, t=10, b=40),
        xaxis_title="Contribution to Total Value",
        yaxis=dict(automargin=True, ticksuffix="  "),
        showlegend=False,
        height=max(260, 30 * len(rows) + 80),
    )
    return fig


def build_explain_summary(breakdown: dict, normalized=None):
    """Dash component for the Value/Cost/Score summary table.

    `breakdown` is the dict from scoring.explain_score. `normalized` is
    the integer 0–100 score the Next tab would show, or None to render
    as '—'. Returns a single component; the caller slots it into the
    static modal body in details_layout.
    """
    if breakdown is None:
        return html.Div("Node not found.", className="text-muted",
                        style={"padding": "16px"})
    return _explain_summary_table(breakdown, normalized)


def build_explain_chart(contributors, top_n: int = 10):
    """Plotly figure for the Top Contributors bar chart.

    `contributors` is the sorted list from scoring.explain_score (or the
    serialized copy stored in dcc.Store). Returns a go.Figure; the
    callback assigns it to the static dcc.Graph's figure prop.
    """
    return _explain_bar_chart(contributors or [], top_n)
