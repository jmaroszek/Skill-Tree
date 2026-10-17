"""Explicit process revisions and per-manager caches for the single-database app.

Revision publication happens only after an outer transaction commits. Read/cache
coordination remains database.state_lock; changing lock duration is a separate,
measurement-driven optimization.
"""
from collections import OrderedDict
from dataclasses import dataclass, field
import threading

from skilltree.store import database


@dataclass
class GraphRevisions:
    graph: int = 0
    scoring: int = 0

    def changed(self, *, scoring=True):
        def bump_graph():
            self.graph += 1

        def bump_scoring():
            self.scoring += 1

        database.on_commit(bump_graph, key='graph_version')
        if scoring:
            database.on_commit(bump_scoring, key='scoring_version')


revisions = GraphRevisions()


# Fields whose mutation changes a node's priority_score. Anything else
# (description, paths, aliases) is cosmetic
# for scoring purposes and must not invalidate the scoring memo.
# context/subcontext are in the list because they are what a node is
# discounted against for suggestion variety, and they also pick its context
# weight and decide which cascade hops count as cross-context.
# `now` is in the list because Now *membership* changes other nodes' numbers:
# scoring.variety_divisors builds its pool from the non-Now nodes, so flipping
# one both drops its own divisor and stops it charging a repetition against its
# context peers, and get_priority_normalizer takes its max over non-Now nodes.
# Only membership matters, not rank -- reorder_now_nodes writes the rank in raw
# SQL and correctly stays scoring=False.
SCORING_RELEVANT_FIELDS = frozenset({
    'type', 'value', 'interest', 'difficulty',
    'time_o', 'time_m', 'time_p', 'time_mode',
    'value_mode',
    'status', 'dormant', 'now',
    'context', 'subcontext',
})


@dataclass
class GraphCaches:
    communities: OrderedDict = field(default_factory=OrderedDict)
    scoring_memo: dict = field(default_factory=dict)
    scoring_key: object = None
    normalizer: float = 0.0
    normalizer_key: object = None
    subtrees: dict = field(default_factory=dict)
    # (graph version, graph_queries.inherited_times result)
    inherited_times: object = None
    read_epoch: object = None
    lock: object = field(default_factory=threading.Lock)
