"""The Nodes tab's layout."""


def empty_canvas_detail(hidden):
    """The line under "No nodes match your filters", from `hidden_by_status`.

    When Done or Dormant nodes are the reason, it says how many matching nodes
    they hide. Otherwise it says what else can be done.
    """
    total, done, dormant = hidden['hidden'], hidden['done'], hidden['dormant']
    if not total:
        return "Widen the filters, or clear them."
    noun = "matching node" if total == 1 else "matching nodes"
    verb = "is" if total == 1 else "are"
    if done and dormant:
        return f"{total} {noun} {verb} hidden: {done} Done, {dormant} Dormant."
    return f"{total} {noun} {verb} {'Done' if done else 'Dormant'} and hidden."
