"""Explore Goals: the Goals the Details tab offers when nothing is selected."""
from skilltree.domain.models import EDGE_NEEDS_HARD, STATUS_DONE


def select_explore_goals(ranked_goals, nodes, edges, count=5,
                         candidate_names=None, seed_names=()):
    """Choose the Details Explore Goals from the Goal ranking, in its order.

    Explore lists Goals as the Goals sidebar's Priority sort does, skipping a
    few so the list is worth scanning:

    * Goals the active filters hide, and the ``seed_names`` already shown
      above as Priority Goals.
    * Goals with no unfinished hard prerequisite, which have nothing to look
      into.
    * A Goal inside, or containing, the hard scope of a Goal already listed,
      while an unrelated Goal is still available. Opening the parent shows the
      child anyway. Nested Goals fill the list only when nothing else can.

    Skipping never reorders, so the priority numbers still descend.
    """
    if count is None or count <= 0:
        return []

    status = {node.name: node.status for node in nodes}
    prereqs = {}
    for edge in edges:
        if edge.get("type") == EDGE_NEEDS_HARD:
            prereqs.setdefault(edge["target"], []).append(edge["source"])

    scopes = {}

    def hard_scope(name):
        if name not in scopes:
            seen, stack = set(), list(prereqs.get(name, ()))
            while stack:
                current = stack.pop()
                if current not in seen:
                    seen.add(current)
                    stack.extend(prereqs.get(current, ()))
            scopes[name] = seen
        return scopes[name]

    def nested(a, b):
        return a in hard_scope(b) or b in hard_scope(a)

    shown = [name for name in seed_names if name in status]
    chosen, nested_goals = [], []
    for goal in ranked_goals:
        if len(chosen) == count:
            break
        if goal.name in shown:
            continue
        if candidate_names is not None and goal.name not in candidate_names:
            continue
        if not any(status.get(name, STATUS_DONE) != STATUS_DONE
                   for name in hard_scope(goal.name)):
            continue
        if any(nested(goal.name, other) for other in shown):
            nested_goals.append(goal)
            continue
        chosen.append(goal)
        shown.append(goal.name)

    chosen += nested_goals[:count - len(chosen)]
    rank = {goal.name: index for index, goal in enumerate(ranked_goals)}
    return sorted(chosen, key=lambda goal: rank[goal.name])
