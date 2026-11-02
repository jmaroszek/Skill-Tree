"""What a search found on a list card, shown only when the card doesn't show it.

A name match needs nothing: the name is on the card. An alias match gets a line
of its own. A description match marks the words, and when they may fall below
the card's two lines of description, the card shows the part that holds them.
"""
from dash import html

from skilltree.ui import tokens

# Enough for two lines at any list width. Hidden text only adds to the payload.
PREVIEW_CHARS = 240
# A match ending past here may be cut off by the two lines.
VISIBLE_CHARS = 70
EXCERPT_LEAD = 24


def _clean(query):
    return (query or "").strip().lower()


def card_matches(query, name, description="", aliases=()):
    """Whether a search finds this card by its name, an alias or its description."""
    q = _clean(query)
    return (not q or q in (name or "").lower()
            or any(q in alias.lower() for alias in aliases)
            or q in (description or "").lower())


def _matched_alias(q, name, aliases):
    if not q or q in (name or "").lower():
        return None
    return next((alias for alias in aliases if q in alias.lower()), None)


def _marked(text, q):
    """``text`` with its first match of ``q`` marked."""
    at = text.lower().find(q) if q else -1
    if at < 0:
        return text
    end = at + len(q)
    parts = [text[:at], html.Mark(text[at:end], className="search-match"), text[end:]]
    return [part for part in parts if part]


def _excerpt(text, q):
    """The part of ``text`` that shows its match, starting at a word."""
    at = text.lower().find(q)
    if at < 0 or at + len(q) <= VISIBLE_CHARS:
        return text
    start = text.rfind(" ", 0, max(at - EXCERPT_LEAD, 0)) + 1
    return "…" + text[start:]


def alias_line(query, name, aliases=()):
    """The line saying which alias a search found the card by, or None."""
    q = _clean(query)
    alias = _matched_alias(q, name, aliases)
    if alias is None:
        return None
    return html.Small(["Also called ", *_as_list(_marked(alias, q))],
                      className="text-muted d-block", style={"fontSize": tokens.FS_SM})


def _as_list(children):
    return children if isinstance(children, list) else [children]


def card_description(description, query=None, name="", aliases=()):
    """A card's two-line description, or None for a card without one."""
    text = (description or "").strip()
    if not text:
        return None
    q = _clean(query)
    found_here = (q and q not in (name or "").lower()
                  and _matched_alias(q, name, aliases) is None and q in text.lower())
    if found_here:
        text = _marked(_excerpt(text, q)[:PREVIEW_CHARS], q)
    else:
        text = text[:PREVIEW_CHARS]
    return html.Small(text, className="list-card-description text-muted")
