"""Rules for the left sidebars (editor, Goals, Events), which share one slot."""


def left_sidebar_is_open(style):
    """True when a left sidebar (editor, goals, events) is slid into view.

    A missing or blank style is the initial closed state, so absence reads as
    closed.
    """
    return bool(style) and style.get('transform') == 'translateX(0px)'


def should_open_editor(all_triggered_ids, trigger_id, search_val):
    """Decide whether the sidebar editor should slide open.

    Checks ALL triggered IDs (not just the primary) so that an edit trigger
    batched with tapNodeData in the same Dash cycle still opens the sidebar.
    """
    return bool(all_triggered_ids & {'btn-edit-node', 'edit-trigger-input', 'details-edit-trigger-input'}) or \
           (trigger_id == 'search-node' and bool(search_val))
