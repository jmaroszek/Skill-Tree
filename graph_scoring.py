"""Scoring orchestration and memo use; the scoring mathematics stays in scoring.py."""
from typing import List, Dict, Optional, Set, Tuple
from collections import deque
import json
import database
import networkx as nx
from config import ConfigManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS, STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE
from scoring import score_nodes


def calculate_priority_scores(manager, now_nodes: List[Node], priority_goals: Optional[List[str]] = None) -> List[Node]:
    """Delegates scoring to the scoring module.

    Reuses per-manager route and required-work maps across calls: a filter toggle,
    priority-goal change, or cosmetic edit (description, tags, paths)
    doesn't alter scoring inputs, so the strongest-route and prerequisite maps
    do not need re-walking. Invalidated only when _scoring_version
    advances (a scoring-relevant node/edge mutation) or a TV-affecting
    hyperparam changes. Cost params (w_e, w_t, beta), goal_boost, and the
    context-adjustment params (alpha, context_weights) don't affect the
    cached structural maps, so they are excluded from the key.
    """
    hypers = ConfigManager.get_hyperparams()
    hypers['context_weights'] = ConfigManager.get_context_weights()
    TV_AFFECTING_KEYS = ('w_v', 'w_i', 'value_exponent', 'd_H', 'd_S',
                         'd_Syn_pair', 'd_Syn_mul', 'cross_context_mult',
                         'future_work_half_credit_hours', 'future_work_exponent')
    hypers_key = tuple((k, hypers.get(k)) for k in TV_AFFECTING_KEYS)
    cache_key = (manager._scoring_version, hypers_key)
    with manager._cache_lock:
        if cache_key != manager._scoring_memo_key:
            manager._scoring_memo = {}
            manager._scoring_memo_key = cache_key
        memo = manager._scoring_memo
    if database.in_transaction():
        memo = {}  # Never read/publish committed caches for pending writes.

    if ConfigManager.get_show_scoring_perf() and not type(manager)._startup_perf_recorded:
        from perf import append_perf_log
        scored, timings = score_nodes(
            now_nodes, manager.get_all_nodes(),
            manager.get_edges(), hypers,
            priority_goals=priority_goals,
            external_memo=memo,
            time_phases=True,
        )
        type(manager)._last_perf_timings = timings
        type(manager)._startup_perf_recorded = True
        append_perf_log(timings)
        return scored

    return score_nodes(
        now_nodes, manager.get_all_nodes(),
        manager.get_edges(), hypers,
        priority_goals=priority_goals,
        external_memo=memo,
    )


def get_priority_normalizer(manager) -> float:
    """The priority score that displays as 100 everywhere in the app.

    Every surface that prints a 0–100 priority divides by this one
    number, so the same node reads the same on the Next tab, in a
    subtask table and in the Explain modal. Normalizing against
    whichever nodes happen to be on screen would make the figure a
    property of the current list instead of the node.

    The base is the top score among nodes that can actually be
    recommended: Now nodes are excluded because the Next list pulls
    them into their own section, and a cheap Now node is often the
    top score overall — including it would shrink every bar on the
    tab below it. Returns 0.0 when nothing is scorable.

    Cached against the scoring version and every hyperparameter that
    can move a score: the Next tab and the subtask tables each want
    this number alongside a ranking they already paid for, and a
    second full scoring pass per render is worth avoiding.
    """
    hypers = ConfigManager.get_hyperparams()
    hypers['context_weights'] = ConfigManager.get_context_weights()
    priority_goals = ConfigManager.get_priority_goals()
    cache_key = (manager._scoring_version,
                 json.dumps(hypers, sort_keys=True, default=str),
                 tuple(priority_goals or ()))
    with manager._cache_lock:
        if cache_key == manager._normalizer_key:
            return manager._normalizer

    scored = manager.calculate_priority_scores(
        manager.get_all_nodes(), priority_goals=priority_goals,
    )
    eligible = [n.priority_score for n in scored
                if getattr(n, 'priority_score', -1) > 0
                and not getattr(n, 'now', 0)]
    base = max(eligible) if eligible else 0.0

    if not database.in_transaction():
        with manager._cache_lock:
            manager._normalizer_key, manager._normalizer = cache_key, base
    return base
