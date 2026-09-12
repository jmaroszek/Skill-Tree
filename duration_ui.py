"""Shared estimate guidance and compact duration forecast explanations."""
from dash import html
import dash_bootstrap_components as dbc


def estimate_guidance():
    return html.Small(
        "Lower: 10% chance of finishing sooner. Expected: a 50/50 estimate. "
        "Upper: 10% chance of taking longer. With only Expected filled in, "
        "that number is used directly as the mean. With a bracket, the mean "
        "work hours are calculated from all supplied values.",
        className="text-muted d-block mb-2")


def simulation_caption(meta):
    def hours(value):
        return '—' if value is None else f'{value:,.1f}'

    trials = f"{meta['trials']:,} trials per scenario"
    if meta['trials'] < meta['requested_trials']:
        trials += f" (requested {meta['requested_trials']:,}; limited for responsiveness)"
    children = [html.Div(trials), html.Div(
        f"Mean work hours: {hours(meta['mean_hours'])} · "
        f"Shared estimate error: {meta['correlation']:g}")]
    rows = [html.Tr([
        html.Td(f"{row['correlation']:g}" +
                (" (current)" if row['correlation'] == meta['correlation'] else "")),
        *[html.Td(hours(row[key])) for key in ('p10', 'p50', 'p90')],
    ]) for row in meta['sensitivity']]
    children.append(html.Details([
        html.Summary("Compare shared-error assumptions"),
        html.Div("Illustrative cases, not a calibrated range. Mean work hours "
                 "are unchanged; the median and forecast range can move.", className="my-1"),
        dbc.Table([
            html.Thead(html.Tr([html.Th(label) for label in
                               ('Shared error', 'P10 (h)', 'P50 (h)', 'P90 (h)')])),
            html.Tbody(rows),
        ], size='sm', responsive=True, className='mb-1'),
    ], className='mt-1'))
    diagnostics = meta['diagnostics']
    if diagnostics:
        noun = 'task bracket differs' if len(diagnostics) == 1 else 'task brackets differ'
        children.append(html.Details([
            html.Summary(f"Approximate percentiles: {len(diagnostics)} "
                         f"{noun} by more than 10%"),
            html.Div("The fit preserves the mean and lower-to-upper ratio, "
                     "so individual percentiles may move. Values below are hours; "
                     "a dash means no middle value was supplied.", className='my-1'),
            *[html.Div([
                html.Strong(row['name']),
                html.Div('Entered P10 / P50 / P90: ' +
                         ' / '.join(hours(v) for v in row['supplied'])),
                html.Div('Fitted P10 / P50 / P90: ' +
                         ' / '.join(hours(v) for v in row['fitted'])),
            ], className='mb-2') for row in diagnostics],
        ], className='mt-1'))
    return html.Div(children, style={'maxHeight': '180px', 'overflowY': 'auto',
                                    'flexShrink': '0'})
