"""Shared goal ranking and explanations, independent of Dash callback registration."""
import math
from collections import defaultdict
from config import ConfigManager
from models import EDGE_NEEDS_HARD, STATUS_DONE
from scoring import (build_adjacency as _scoring_build_adjacency, intrinsic_value,
                     perceived_cost, _done_names, _goals_above, _milestone_names,
                     _strongest_routes)


def _hard_subtree(goal_name, hard_in):
    """Every node with a Hard path into `goal_name`, the Goal excluded."""
    seen, stack = set(), list(hard_in.get(goal_name, ()))
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(hard_in.get(name, ()))
    return seen


def _goal_work(all_nodes_dict, edges, hp):
    """Each unfinished task's worth and effort, the same whichever Goal counts it.

    A task is worth its own ratings plus the credit it earns for the Goals
    above it, as on the Home tab: d_H for its nearest Goals and one more d_H
    per parent level. Nothing it unlocks is added, since that work sits in
    the average in its own right or belongs to other Goals. Credit pays as
    the work gets done, so no future-work discount applies. Effort is the
    task's ordinary perceived cost.

    Returns (hard_in, rows): rows maps each task to a dict with 'own',
    'credit' ({goal: amount}), 'value', 'cost' and 'hours'. Tasks are the
    unfinished nodes with hours of their own; Goals, Milestones and
    inherited-time containers hold no work.
    """
    w_v = hp.get('w_v', 1.0)
    w_i = hp.get('w_i', 1.0)
    d_H = hp.get('d_H', 0.6)
    value_exponent = hp.get('value_exponent', 1.0)
    w_e = hp.get('w_e', 2.5)
    w_t = hp.get('w_t', 1.0)
    beta = hp.get('beta', 0.85)

    H_out, _, _, hard_in = _scoring_build_adjacency(edges, set(all_nodes_dict))
    memo: dict = {}
    nearest, goal_order = _goals_above(H_out, all_nodes_dict, memo,
                                       _done_names(all_nodes_dict, memo))
    goal_iv = {g: intrinsic_value(all_nodes_dict[g], w_v, w_i, value_exponent)
               for g in goal_order}

    rows = {}
    for name, node in all_nodes_dict.items():
        if (node.type in ('Goal', 'Milestone') or node.has_no_own_work
                or node.status == STATUS_DONE):
            continue
        weights = {g: d_H for g in nearest.get(name, ())}
        for goal in goal_order:  # sub-Goals come before their parents
            if goal in weights:
                for parent in nearest.get(goal, ()):
                    weights[parent] = max(weights.get(parent, 0.0), weights[goal] * d_H)
        own = intrinsic_value(node, w_v, w_i, value_exponent)
        credit = {g: w * goal_iv[g] for g, w in weights.items()}
        effort = 0.0 if node.value_mode == 'inherited' else None
        rows[name] = {
            'own': own,
            'credit': credit,
            'value': own + math.fsum(credit.values()),
            'cost': perceived_cost(node, w_e, w_t, beta, effort_override=effort),
            'hours': node.time,
        }
    return hard_in, rows


def _rank_goals(goals, all_nodes, edges, priority_goals, hp,
                with_scores=False, with_components=False):
    """Rank Goals by the average worth of their remaining work, scaled by
    priority-rank boost, context weight and Goal density.

    A Goal's base score is the summed worth of the unfinished tasks in its
    hard subtree over their summed effort (see _goal_work). Every task counts
    alike, however deep it sits, and a Goal's size counts neither for nor
    against it: adding work of the same quality leaves the score unchanged.
    The Goal's own rating enters through the credit each task earns for it.
    Soft and Helps work is outside the subtree. A Goal with no work left
    scores 0. Goal density uses alpha_goal and counts non-Done Goals in each
    bucket.

    rank_boost gives priority rank 1 the full ``goal_boost``, rank 2 66%
    of the bump, rank 3 33%. Returns goals sorted by score descending;
    with ``with_scores`` returns ``(goal, score)`` tuples instead.
    """
    goal_boost = hp.get('goal_boost', 1.5)
    alpha_goal = hp.get('alpha_goal', 0.20)
    rank_multipliers = [
        goal_boost,
        1 + (goal_boost - 1) * 0.66,
        1 + (goal_boost - 1) * 0.33,
    ]
    context_weights = ConfigManager.get_context_weights() or {}

    # Goal-only bucket counts for the density correction. Done Goals are
    # excluded — they're not competing for sidebar attention. Null-context
    # Goals (rare) keep their own bucket via the None key, mirroring how
    # scored-node bucketing treats (None, None) below.
    goal_bucket_counts: dict = defaultdict(int)
    for g in all_nodes:
        if g.type != 'Goal' or g.status == STATUS_DONE:
            continue
        goal_bucket_counts[(g.context, g.subcontext)] += 1

    all_nodes_dict = {n.name: n for n in all_nodes}
    hard_in, work = _goal_work(all_nodes_dict, edges, hp)

    scored = []
    for g in goals:
        tasks = [work[name] for name in _hard_subtree(g.name, hard_in) if name in work]
        tv = math.fsum(t['value'] for t in tasks)
        cost = math.fsum(t['cost'] for t in tasks)
        remaining_time = math.fsum(t['hours'] for t in tasks)
        raw = tv / cost if cost > 0 else 0.0
        rank_mult = 1.0
        rank_idx = None
        if g.name in priority_goals:
            ri = priority_goals.index(g.name)
            if ri < 3:
                rank_mult = rank_multipliers[ri]
                rank_idx = ri
        context_weight = context_weights.get(g.context, 1.0) if g.context else 1.0
        bucket_count = goal_bucket_counts.get((g.context, g.subcontext), 1)
        # Done Goals are excluded from the bucket count, so they would key to
        # 0 (defaultdict default) if requested directly — but Done Goals also
        # rarely flow into _rank_goals callers. Floor at 1 to mirror the
        # max(1, ...) guard in scoring.score_nodes.
        bucket_count = max(1, bucket_count)
        density_mult = 1.0 / (bucket_count ** alpha_goal) if alpha_goal > 0 else 1.0
        score = raw * rank_mult * context_weight * density_mult
        scored.append((g, score, {
            'score': score, 'raw': raw, 'tv': tv, 'cost': cost,
            'remaining_time': remaining_time, 'n_tasks': len(tasks),
            'rank_mult': rank_mult,
            'rank_idx': rank_idx, 'context_weight': context_weight,
            'bucket_count': bucket_count, 'alpha_goal': alpha_goal,
            'density_mult': density_mult,
        }))

    scored.sort(key=lambda x: x[1], reverse=True)
    if with_components:
        return [(g, comp) for g, _, comp in scored]
    if with_scores:
        return [(g, s) for g, s, _ in scored]
    return [g for g, _, _ in scored]


def normalize_goal_scores(ranked, all_nodes, edges):
    """Each unfinished Goal's priority as 0-100, on one base for the whole app.

    The Goals sidebar, the Explain modal and the Details suggestions all print
    this number, so a Goal reads the same wherever it appears. The base is the
    top score among unfinished Goals, whatever a search or filter hides. A
    number measured against the visible list would describe the list, not the
    Goal.

    A finished Goal gets no number and doesn't set the base. It is finished
    when it is Done or every hard prerequisite beneath it is. With no work
    left, its cost bottoms out, so its score would dwarf every Goal still in
    play.

    ``ranked`` holds ``(goal, score)`` pairs from ``_rank_goals``. Returns a
    name -> int map.
    """
    status = {n.name: n.status for n in all_nodes}
    prereqs = defaultdict(list)
    for e in edges:
        if e['type'] == EDGE_NEEDS_HARD:
            prereqs[e['target']].append(e['source'])

    def is_finished(goal):
        if goal.status == STATUS_DONE:
            return True
        seen, stack = set(), list(prereqs.get(goal.name, ()))
        while stack:
            name = stack.pop()
            if name in seen or name not in status:
                continue
            if status[name] != STATUS_DONE:
                return False
            seen.add(name)
            stack.extend(prereqs.get(name, ()))
        return bool(seen)

    open_scores = {g.name: score for g, score in ranked if not is_finished(g)}
    top = max(open_scores.values(), default=0.0)
    if top <= 0:
        return {}
    return {name: round(score / top * 100) for name, score in open_scores.items()}


def explain_goal(goal_name, all_nodes, edges, hp, priority_goals):
    """Explain-modal breakdown for a Goal node.

    ``scoring.explain_score`` walks the prereq DAG *forward*, summing what a
    node unlocks. Goals are sinks, so that answer is empty for them. A Goal
    is ranked by the average worth of the work left beneath it instead, so
    this breakdown is built from the same pieces ``_rank_goals`` uses (see
    _goal_work):

      * composition: the worth of that work, split into the tasks' own
        ratings, the credit they earn for this Goal, and the credit they
        earn for other Goals (its sub-Goals and the Goals above it);
      * contributors: one row per unfinished task, by its worth, with its
        depth on the inverted Hard graph so Focus can draw its route;
      * headline score, cost and adjustments: straight from ``_rank_goals``,
        so the modal's number matches the Goals sidebar exactly.

    Returns ``(breakdown, normalized)``; ``normalized`` is the Goal's 0-100
    priority from ``normalize_goal_scores``, or None once it is finished.
    Returns ``None`` if ``goal_name`` is not a Goal in ``all_nodes``.
    """
    node = next((n for n in all_nodes if n.name == goal_name), None)
    if node is None or node.type != 'Goal':
        return None

    goals = [n for n in all_nodes if n.type == 'Goal']
    ranked = _rank_goals(goals, all_nodes, edges, priority_goals, hp,
                         with_components=True)
    comps = {g.name: c for g, c in ranked}
    me = comps.get(goal_name)
    if me is None:
        return None

    normalized = normalize_goal_scores(
        [(g, c['score']) for g, c in ranked], all_nodes, edges).get(goal_name)

    all_nodes_dict = {n.name: n for n in all_nodes}
    hard_in, work = _goal_work(all_nodes_dict, edges, hp)
    tasks = sorted((name for name in _hard_subtree(goal_name, hard_in) if name in work),
                   key=lambda name: (-work[name]['value'], name))

    # Depths come from the inverted Hard graph, the one Focus traces routes on.
    inverted = [{'source': e['target'], 'target': e['source'], 'type': e['type']}
                for e in edges if e['type'] == EDGE_NEEDS_HARD]
    H_inv, _, _, _ = _scoring_build_adjacency(inverted, set(all_nodes_dict))
    memo: dict = {}
    routes = _strongest_routes(goal_name, H_inv, {}, hp.get('d_H', 0.6), 0.0, memo,
                               free=_milestone_names(all_nodes_dict, memo))

    total = me['tv']
    own = math.fsum(work[t]['own'] for t in tasks)
    for_goal = math.fsum(work[t]['credit'].get(goal_name, 0.0) for t in tasks)
    contributors = [{
        'name': t,
        'via': 'Hard',
        'depth': routes[t][1] if t in routes else 0,
        'iv': work[t]['own'],
        'contribution': work[t]['value'],
        'pct_of_tv': 100.0 * work[t]['value'] / total if total > 0 else 0.0,
        'goal_work': True,
    } for t in tasks]

    goal_iv = intrinsic_value(node, hp.get('w_v', 1.0), hp.get('w_i', 1.0),
                              hp.get('value_exponent', 1.0))
    breakdown = {
        'node': goal_name,
        'context': node.context,
        'subcontext': node.subcontext,
        'is_goal': True,
        'eligible': True,
        'block_reason': None,
        'score': round(me['score'], 2),
        'raw_score': me['raw'],
        'intrinsic': {
            'value': node.value,
            'interest': node.interest,
            'iv': goal_iv,
            'value_overridden': node.value_mode == 'inherited',
        },
        'cost': {
            'goal': True,
            'remaining_time': me['remaining_time'],
            'n_tasks': me['n_tasks'],
            'cost': me['cost'],
            'time_overridden': False,
        },
        'composition': {
            'total_value': total,
            'iv': own,
            'goal_credit': for_goal,
            'other_goal_credit': max(0.0, total - own - for_goal),
            'hard_cascade': 0.0,
            'soft_cascade': 0.0,
            'synergy': 0.0,
            'iv_multiplier_contribution': 0.0,
        },
        'goal_boost': ({'multiplier': me['rank_mult'], 'goal': goal_name,
                        'rank': me['rank_idx'] + 1}
                       if me['rank_idx'] is not None else None),
        'variety': None,
        'context_adjustment': {
            'weight': me['context_weight'],
            'n_bucket': me['bucket_count'],
            'alpha': me['alpha_goal'],
            'density_mult': me['density_mult'],
            'combined_multiplier': me['context_weight'] * me['density_mult'],
        },
        'contributors': contributors,
    }
    return breakdown, normalized
