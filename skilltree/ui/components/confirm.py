"""The confirmation that a change would reopen Done nodes."""
from dash import html

# How many reopened nodes the confirmation names before it counts the rest.
_LISTED = 25


def reopen_body(reopened):
    """The confirmation's text for the Done nodes a change would reopen: a
    link menu change, or an editor save that adds a Hard prerequisite."""
    count = len(reopened)
    lead = ("This change reopens a Done node" if count == 1
            else f"This change reopens {count} Done nodes")
    children = [
        html.P(f"{lead}, because it gives "
               f"{'it' if count == 1 else 'them'} a Hard prerequisite "
               "that isn't Done yet:"),
        html.Ul([html.Li(name) for name in reopened[:_LISTED]], className="mb-2"),
    ]
    if count > _LISTED:
        children.append(html.Div(f"...and {count - _LISTED} more.",
                                 className="text-muted small mb-2"))
    children.append(html.P(
        f"Undoing the change later won't mark {'it' if count == 1 else 'them'} Done again.",
        className="text-muted small mb-0"))
    return children
