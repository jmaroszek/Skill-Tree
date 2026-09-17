"""Shared goal ranking and explanations, independent of Dash callback registration."""
from collections import defaultdict
from config import ConfigManager
from models import EDGE_NEEDS_HARD, STATUS_DONE
from scoring import (build_adjacency as _scoring_build_adjacency, total_value,
                     explain_score, time_cost_term, GOAL_TIME_REF_HOURS)

def _rank_goals(goals, all_nodes, edges, priority_goals, hp,
                with_scores=False, with_components=False):
    """Rank goals by ROI — prerequisite-subtree value per unit of time,
    scaled by priority-rank boost and context weight.

    Reverse Hard edges only and count each prerequisite beneficiary through
    its strongest route. Optional Soft/Helps work is outside both value and
    cost. Completed prerequisite value remains part of the capacity's value.
    Cost is 1 + w_t * (remaining hard hours / GOAL_TIME_REF_HOURS)**beta;
    no second future-work discount or aggregate difficulty penalty applies.
    Goal density uses alpha_goal and counts non-Done Goals in each bucket.

    rank_boost gives priority rank 1 the full ``goal_boost``, rank 2 66%
    of the bump, rank 3 33%. Returns goals sorted by score descending;
    with ``with_scores`` returns ``(goal, score)`` tuples instead.
    """
    w_v = hp.get('w_v', 1.0)
    w_i = hp.get('w_i', 1.0)
    d_H = hp.get('d_H', 0.6)
    d_S = hp.get('d_S', 0.40)
    d_Syn_pair = hp.get('d_Syn_pair', 0.10)
    d_Syn_mul = hp.get('d_Syn_mul', 0.40)
    cross_context_mult = hp.get('cross_context_mult', 1.0)
    value_exponent = hp.get('value_exponent', 1.0)
    w_t = hp.get('w_t', 1.0)
    beta = hp.get('beta', 0.85)
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

    # Goal value and cost both stay inside its required Hard scope.
    inverted = []
    for e in edges:
        if e['type'] == EDGE_NEEDS_HARD:
            inverted.append({'source': e['target'], 'target': e['source'],
                             'type': e['type']})

    # Milestones are stored as pure containers (both modes inherited, enforced
    # in Node.__post_init__), so they carry no own value or time and pass
    # prerequisite value through transparently — no in-memory transform needed.
    all_nodes_dict = {n.name: n for n in all_nodes}
    H_out, S_out, Syn, _ = _scoring_build_adjacency(
        inverted, set(all_nodes_dict.keys()))

    def _hard_subtree_remaining(goal_name):
        """Sum of remaining (non-Done) time over the hard-prereq subtree.
        Inverted H_out walks goal -> prereqs, so this is the whole body
        of hard work still owed before the goal can complete."""
        visited = set()
        queue = list(H_out.get(goal_name, []))
        while queue:
            cur = queue.pop()
            if cur in visited:
                continue
            visited.add(cur)
            for nxt in H_out.get(cur, []):
                if nxt not in visited:
                    queue.append(nxt)
        total = 0.0
        for name in visited:
            n = all_nodes_dict.get(name)
            if n is not None and n.status != STATUS_DONE:
                total += n.time
        return total

    memo: dict = {}
    scored = []
    for g in goals:
        tv = total_value(
            g.name, set(), all_nodes_dict, H_out, S_out, Syn,
            w_v, w_i, d_H, d_S, d_Syn_pair, d_Syn_mul, memo,
            cross_context_mult=cross_context_mult,
            value_exponent=value_exponent,
        )
        remaining_time = _hard_subtree_remaining(g.name)
        # A Goal's cost is its whole remaining hard subtree, which runs ~33x
        # larger than a single node's estimate (median ~1300h vs ~40h). It
        # therefore normalizes against GOAL_TIME_REF_HOURS rather than the leaf
        # TIME_REF_HOURS, so that w_t and beta carry the same meaning here as
        # they do in perceived_cost instead of silently denoting a much
        # heavier time penalty.
        cost = 1.0 + time_cost_term(remaining_time, w_t, beta,
                                    ref=GOAL_TIME_REF_HOURS)
        raw = tv / cost
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
            'remaining_time': remaining_time, 'rank_mult': rank_mult,
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
    node unlocks. Goals are sinks (work flows into them, nothing flows out),
    so that forward cascade collapses to the Goal's own intrinsic value and
    explain_score correctly reports them as not-ranked. The meaningful
    question for a Goal is the inverse: how much prerequisite value/work
    does it subsume, and what is that worth per unit of remaining time —
    exactly what ``_rank_goals`` scores.

    This stitches the two correct halves together:

      * value composition + contributors — ``explain_score`` run on the
        Hard-only inverted edge set, so its forward cascade now walks the
        prerequisite subtree. Optional Soft and Helps edges are excluded.
      * headline score + cost — taken straight from ``_rank_goals`` so the
        modal's number matches the Goals sidebar and Analyze tab exactly.

    Fields that have no meaning for a Goal are neutralised rather than left
    showing stale forward-graph values: eligibility is forced True (Goals
    *are* ranked, just on the inverted graph). The density adjustment is
    populated from ``_rank_goals`` (Goal-only bucket count + ``alpha_goal``),
    not from ``score_nodes`` (which excludes Goals from leaf-level buckets).

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

    # Use the same Hard-only scope as the Goal ranker.
    inverted = []
    for e in edges:
        if e['type'] == EDGE_NEEDS_HARD:
            inverted.append({'source': e['target'], 'target': e['source'],
                             'type': e['type']})

    # Milestones are stored as pure containers (see _rank_goals), so they're
    # already transparent — pass all_nodes straight through.
    bd = explain_score(goal_name, all_nodes, inverted,
                       dict(hp, future_work_half_credit_hours=0.0), priority_goals)
    if bd is None:
        return None

    bd['is_goal'] = True
    bd['eligible'] = True
    bd['block_reason'] = None
    bd['score'] = round(me['score'], 2)
    bd['raw_score'] = me['raw']
    bd['cost'] = {
        'goal': True,
        'remaining_time': me['remaining_time'],
        'cost': me['cost'],
        'time_overridden': False,
    }
    if me['rank_idx'] is not None:
        bd['goal_boost'] = {
            'multiplier': me['rank_mult'],
            'goal': goal_name,
            'rank': me['rank_idx'] + 1,
        }
    else:
        bd['goal_boost'] = None
    bd['context_adjustment'] = {
        'weight': me['context_weight'],
        'n_bucket': me['bucket_count'],
        'alpha': me['alpha_goal'],
        'density_mult': me['density_mult'],
        'combined_multiplier': me['context_weight'] * me['density_mult'],
    }
    return bd, normalized
