"""Application-owned services; construction does not open the database."""
from dataclasses import dataclass, field

from skilltree.store.events import EventManager
from skilltree.store.graph.manager import GraphManager


@dataclass
class AppServices:
    graph: GraphManager = field(default_factory=GraphManager)
    events: EventManager = field(default_factory=EventManager)
