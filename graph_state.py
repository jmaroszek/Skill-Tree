"""Explicit process revisions and per-manager caches for the single-database app.

Revision publication happens only after an outer transaction commits. Read/cache
coordination remains database.state_lock; changing lock duration is a separate,
measurement-driven optimization.
"""
from collections import OrderedDict
from dataclasses import dataclass, field
import threading


@dataclass
class GraphRevisions:
    graph: int = 0
    scoring: int = 0

    def changed(self, *, scoring=True):
        import database

        def bump_graph():
            self.graph += 1

        def bump_scoring():
            self.scoring += 1

        database.on_commit(bump_graph, key='graph_version')
        if scoring:
            database.on_commit(bump_scoring, key='scoring_version')


revisions = GraphRevisions()


@dataclass
class GraphCaches:
    communities: OrderedDict = field(default_factory=OrderedDict)
    scoring_memo: dict = field(default_factory=dict)
    scoring_key: object = None
    normalizer: float = 0.0
    normalizer_key: object = None
    subtrees: dict = field(default_factory=dict)
    read_epoch: object = None
    lock: object = field(default_factory=threading.Lock)


class RevisionValue:
    """Read compatibility for GraphManager's former class-level counters."""
    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        return getattr(revisions, self.name)


class CacheValue:
    """Compatibility for callers inspecting a manager's existing private caches."""
    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        return self if instance is None else getattr(instance.caches, self.name)

    def __set__(self, instance, value):
        setattr(instance.caches, self.name, value)
