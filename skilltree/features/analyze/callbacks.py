"""
Callback definitions for the Analyze tab.
Computes and renders aggregate analytics about the graph.
"""

from skilltree.features.analyze.data import (
    adjacency_maps,
    compute_overview,
    compute_bottlenecks,
    compute_estimation_accuracy,
    compute_reflection_drift,
    compute_throughput,
    compute_goal_progress,
    compute_rating_distribution,
)

import logging
import threading
import uuid
from datetime import date
from dash import html, Input, Output, State, ctx, no_update
import dash_bootstrap_components as dbc
from skilltree.store import database
from skilltree.store import settings
from skilltree.features.analyze.charts import (
    render_bottleneck_chart as _render_bottleneck_chart,
    render_context_accuracy_boxplot as _render_context_accuracy_boxplot,
    render_estimation_accuracy as _render_estimation_accuracy,
    render_goal_progress as _render_goal_progress, render_overview as _render_overview,
    render_rating_distribution as _render_rating_distribution,
    render_reflection_drift_chart as _render_reflection_drift_chart,
    render_throughput_chart as _render_throughput_chart,
)
from skilltree.store.graph.state import revisions

logger = logging.getLogger(__name__)

# Distinguishes this server process from an earlier one, whose version
# counters restarted from zero, in a signature a page is still holding.
_PROCESS_EPOCH = uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Adjacency helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Compute functions
# ---------------------------------------------------------------------------


def _get_limits():
    """Read analyze limits from user settings, with defaults."""
    return settings.ANALYZE_LIMITS.get()


# ---------------------------------------------------------------------------
# Chart helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


# The most bars the half-width Throughput chart draws. A long history at
# month granularity keeps its latest buckets; earlier ones need quarters,
# years, or a narrower date range.
_THROUGHPUT_MAX_BARS = 24


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------

def register_analyze_callbacks(app, services):
    graph = services.graph
    # Arrival gate. Listening to `main-tabs.active_tab` directly meant every
    # tab switch anywhere in the app posted a request to the server just to
    # have refresh_analyze_tab answer no_update six times — a round-trip that
    # queued behind the real work the user was waiting on. This clientside
    # filter only bumps the store when Analyze is the tab being opened, so
    # switching to Details or Next now costs nothing here.
    app.clientside_callback(
        """
        function(active_tab) {
            if (active_tab !== 'tab-analyze') {
                return window.dash_clientside.no_update;
            }
            return Date.now();
        }
        """,
        Output("analyze-active-store", "data"),
        Input("main-tabs", "active_tab"),
        prevent_initial_call=True,
    )

    # Subtabs show and hide their panes in the browser. Every pane renders
    # together, so a switch needs no server round-trip;
    # assets/analyze_first_paint.js sizes a pane's charts as it appears.
    # An unknown tab, such as the Structure tab a browser may still remember,
    # shows Plan.
    app.clientside_callback(
        """
        function(active) {
            var panes = ['analyze-plan', 'analyze-history'];
            var shown = panes.indexOf(active) >= 0 ? active : 'analyze-plan';
            return panes.map(function (id) {
                return {display: id === shown ? 'block' : 'none'};
            });
        }
        """,
        Output("analyze-pane-plan", "style"),
        Output("analyze-pane-history", "style"),
        Input("analyze-subtabs", "active_tab"),
    )

    # Analyze renders on its first visit, not at startup. Its charts cost the
    # browser about 0.6 s of main-thread work, and the startup cover waited
    # for them. assets/analyze_prewarm.js writes analyze-prewarm-store when
    # the pointer or focus reaches the Analyze tab, so the render starts a
    # moment before the click.
    @app.callback(
        Output("analyze-overview-content", "children"),
        Output("analyze-goals-content", "children"),
        Output("analyze-contexts-content", "children"),
        Output("analyze-time-content", "children"),
        Output("analyze-drift-content", "children"),
        Output("analyze-throughput-content", "children"),
        Output("analyze-bottlenecks-content", "children"),
        Output("analyze-sections", "hidden"),
        Output("analyze-loading-cover", "hidden"),
        Output("analyze-rendered-store", "data"),
        Input("analyze-active-store", "data"),
        Input("analyze-prewarm-store", "data"),
        Input("setting-analyze-bottlenecks", "value"),
        Input("setting-analyze-goals", "value"),
        Input("setting-analyze-throughput-granularity", "value"),
        Input("setting-analyze-throughput-start", "value"),
        Input("setting-analyze-throughput-end", "value"),
        Input("setting-analyze-throughput-color", "value"),
        # save-output is the global "something was saved" channel. Reflection
        # edits via the hub modal don't regenerate Cytoscape elements, so
        # graph-version-store doesn't bump and the usual graph-change signal
        # misses them. Listening to save-output picks them up; the active_tab
        # guard below short-circuits when the user is not on this tab.
        Input("save-output", "children"),
        # Read as State now that arrival is signalled by analyze-active-store.
        # Still needed: the settings and save-output Inputs fire from any tab.
        State("main-tabs", "active_tab"),
        State("analyze-rendered-store", "data"),
        prevent_initial_call=True,
    )
    def refresh_analyze_tab(_arrived, _prewarm, bottlenecks, goals,
                            thru_gran, thru_start, thru_end, thru_color,
                            _save_output, active_tab, rendered_signature):
        skip = (no_update,) * 10
        fired = set(ctx.triggered_prop_ids)
        # A dcc.Store whose data starts as None reports a change with no
        # value when it mounts. That isn't an arrival.
        arrival = ((_arrived and "analyze-active-store.data" in fired)
                   or (_prewarm and "analyze-prewarm-store.data" in fired))
        others = fired - {"analyze-active-store.data",
                          "analyze-prewarm-store.data"}
        signature = _analyze_signature()
        if others and active_tab == "tab-analyze":
            reuse = False
        elif not arrival or rendered_signature == signature:
            # Arrivals and the prewarm render only what's out of date. Every
            # write the charts depend on bumps the graph version.
            return skip
        else:
            reuse = True

        try:
            sections = _render_sections_once(
                graph, signature,
                (bottlenecks, goals, thru_gran, thru_start, thru_end, thru_color),
                reuse)
        except Exception:
            # Never strand the tab behind its cover. Leaving the signature
            # unset retries the render on the next visit.
            logger.exception("Analyze render failed")
            error = html.P("The analysis couldn't be computed. "
                           "See the app log for details.",
                           className="text-danger small")
            return error, "", "", "", "", "", "", False, True, None
        return (*sections, False, True, signature)


_render_lock = threading.Lock()
_last_render = None


def _render_sections_once(graph, signature, args, reuse):
    """Render the sections, sharing one render between a prewarm and the click
    that follows it.

    The prewarm starts on hover, so the click usually arrives while it is
    still computing. Dash drops the earlier request's response in favour of the
    later one's. Without this the click would compute everything a second time
    and wait for both. With it, the click waits for the render already under
    way and returns it. Settings and save refreshes pass reuse=False: a
    reflection edit changes the charts without changing the signature.
    """
    global _last_render
    key = (database.get_db_path(), repr(signature), args)
    with _render_lock:
        if reuse and _last_render is not None and _last_render[0] == key:
            return _last_render[1]
        sections = _render_analyze_sections(graph, *args)
        _last_render = (key, sections)
        return sections


def _analyze_signature():
    """What the Analyze charts are computed from, cheaply. The graph version
    covers nodes, edges, and the scoring and time settings. Contexts are
    listed on their own because adding an empty one bumps nothing, the
    ratings rubric because the tooltips quote it, and the date because the
    charts are dated."""
    return [_PROCESS_EPOCH, revisions.graph,
            settings.CONTEXTS.get(), settings.RATINGS_DEFINITIONS.get(),
            date.today().isoformat()]


def _render_analyze_sections(graph, bottlenecks, goals, thru_gran, thru_start,
                             thru_end, thru_color):
    """The seven section bodies of the Analyze tab, in the callback's output
    order: the overview strip; Goals and Contexts (Plan); Time Estimation
    Accuracy, Rating Accuracy and Throughput (History); then Bottlenecks,
    which sits beside Goals on Plan."""
    # Persist any limit changes made via the gear popovers before rendering.
    al = settings.ANALYZE_LIMITS.get()
    if bottlenecks is not None:
        al['bottlenecks'] = int(bottlenecks)
    if goals is not None:
        al['goals'] = int(goals)
    if thru_gran in ('month', 'quarter', 'year'):
        al['throughput_granularity'] = thru_gran
    if thru_color in ('context', 'type'):
        al['throughput_color'] = thru_color
    # Empty-string date inputs persist as None (auto-extent).
    al['throughput_start'] = thru_start or None
    al['throughput_end'] = thru_end or None
    settings.ANALYZE_LIMITS.set(al)

    return _build_analyze_sections(graph, al)


@database.snapshot_read
def _build_analyze_sections(graph, al):
    """Share graph and formatting settings after the limit write has committed."""
    nodes = graph.get_all_nodes(include_dormant=False)
    edges = graph.get_edges()

    if not nodes:
        empty = html.P("No nodes in the graph yet.", className="text-muted small")
        return empty, "", "", "", "", "", ""

    hard_fwd, hard_rev, _, _, _ = adjacency_maps(edges)

    # Compute all sections
    limits = _get_limits()
    overview = compute_overview(nodes, edges)
    bottlenecks = compute_bottlenecks(nodes, hard_fwd, limits)
    goal_rows, total_goal_count = compute_goal_progress(nodes, edges, hard_rev, limits)
    est_accuracy = compute_estimation_accuracy(nodes)
    rating_dist = compute_rating_distribution(nodes)
    drift_rows = compute_reflection_drift(nodes)
    color_by = al['throughput_color']
    throughput_rows = compute_throughput(
        nodes,
        granularity=al['throughput_granularity'],
        start_date=al['throughput_start'],
        end_date=al['throughput_end'],
        by=color_by,
    )

    overview_content = _render_overview(overview)

    goals_content = [
        html.P(
            f"Top {len(goal_rows)} of {total_goal_count} goals, ranked by scoring "
            "algorithm. Progress is the share of estimated work done."
            if total_goal_count > len(goal_rows)
            else "Every goal, ranked by scoring algorithm. Progress is the "
                 "share of estimated work done.",
            className="text-muted small"),
        _render_goal_progress(goal_rows),
    ]

    bottlenecks_content = [
        html.P("Open nodes that gate the most unfinished work. The gray stub "
               "is the node's own time.", className="text-muted small"),
        _render_bottleneck_chart(bottlenecks),
    ]

    contexts_content = [
        html.P("Where your time is allocated, and how you rated it.",
               className="text-muted small"),
        # Full width: three ten-cell strips and a Work left bar per row.
        dbc.Row(dbc.Col(_render_rating_distribution(rating_dist), width=12),
                className="g-3"),
    ]

    # The two charts head their own columns, so the section has no header of
    # its own. Each column's card stretches to the taller one.
    time_content = [
        dbc.Row([
            dbc.Col([
                html.H5("Time Estimates by Node", className="mt-2 mb-1"),
                html.P("Dots above the dashed line took longer than you "
                       "estimated, and dots below took less time.",
                       className="text-muted small"),
                html.Div(_render_estimation_accuracy(est_accuracy), className="flex-grow-1"),
            ], width=6, className="d-flex flex-column"),
            dbc.Col([
                html.H5("Time Estimates by Context", className="mt-2 mb-1"),
                html.P("Boxes to the right of the 1× line ran over your "
                       "estimates, and boxes to the left came in under.",
                       className="text-muted small"),
                html.Div(_render_context_accuracy_boxplot(est_accuracy), className="flex-grow-1"),
            ], width=6, className="d-flex flex-column"),
        ], className="g-3"),
    ]

    drift_content = [
        html.P("How your ratings change when you reflect on completed work.",
               className="text-muted small"),
        _render_reflection_drift_chart(drift_rows),
    ]

    gran = al['throughput_granularity']
    gran_label = {'month': 'month', 'quarter': 'quarter',
                  'year': 'year'}[gran]
    throughput_note = "Hours of completed work per time period."
    if len(throughput_rows) > _THROUGHPUT_MAX_BARS:
        throughput_rows = throughput_rows[-_THROUGHPUT_MAX_BARS:]
        wider = {'month': 'quarters', 'quarter': 'years'}.get(gran)
        throughput_note += (
            f" Showing the latest {_THROUGHPUT_MAX_BARS} {gran_label}s. "
            + (f"Switch to {wider} or narrow the dates to see earlier ones."
               if wider else "Narrow the dates to see earlier ones."))
    throughput_content = [
        html.P(throughput_note, className="text-muted small"),
        _render_throughput_chart(throughput_rows, granularity=gran, by=color_by),
    ]

    return (overview_content, goals_content, contexts_content, time_content,
            drift_content, throughput_content, bottlenecks_content)
