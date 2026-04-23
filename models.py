"""Core data models for the Skill Tree.

A `Node` is the fundamental unit — a task, goal, or reference that the
scoring algorithm can rank. Nodes are related to one another by typed
edges (see the EDGE_* constants).

An `Event` is an activation gate: zero-or-more dormant nodes can be
attached to it, and when the event triggers (manually, by date, or when
a specific node completes) the dormant nodes become active.
"""

from dataclasses import dataclass, asdict
from typing import Optional
import math

# Edge type constants used across the codebase
EDGE_NEEDS_HARD = 'Needs_Hard'
EDGE_NEEDS_SOFT = 'Needs_Soft'
EDGE_HELPS = 'Helps'


@dataclass
class Node:
    """A task, goal, or reference in the graph.

    `name` is the primary key — renaming a node cascades through edges,
    overrides, goal orderings, and events (see GraphManager.rename_node).
    `time_mode='inherited'` means a parent node draws its time estimate
    from its hard prerequisites rather than its own time_o/m/p fields.
    """
    name: str               # Primary key
    type: str               # [Learn, Goal, Action, Resource]
    description: str
    value: int              # 1-10
    time_o: float           # Optimistic Hours
    time_m: float           # Most Likely Hours
    time_p: float           # Pessimistic Hours
    interest: int           # 1-10
    difficulty: int         # 1-10
    status: str             # [Open, Blocked, Done]
    competence: Optional[str] = None
    context: Optional[str] = None
    subcontext: Optional[str] = None
    obsidian_path: Optional[str] = None
    google_drive_path: Optional[str] = None
    website: Optional[str] = None
    dormant: int = 0
    time_mode: str = 'manual'  # 'manual' or 'inherited'
    priority_score: Optional[float] = None

    def __post_init__(self):
        self.value = int(self.value) if self.value is not None else 5
        self.time_o = float(self.time_o) if self.time_o else 0.0
        self.time_m = float(self.time_m) if self.time_m else 0.0
        self.time_p = float(self.time_p) if self.time_p else 0.0
        self.interest = int(self.interest) if self.interest is not None else 5
        self.difficulty = int(self.difficulty) if self.difficulty is not None else 5
        self.value = max(1, min(10, self.value))
        self.interest = max(1, min(10, self.interest))
        self.difficulty = max(1, min(10, self.difficulty))
        self.dormant = int(self.dormant) if self.dormant is not None else 0
        if self.time_mode not in ('manual', 'inherited'):
            self.time_mode = 'manual'
        if self.time_mode == 'inherited':
            self.time_o = 0.0
            self.time_m = 0.0
            self.time_p = 0.0

    @property
    def time(self) -> float:
        """Calculates blended PERT time estimation.

        Uses a weighted blend of arithmetic and logarithmic (geometric) means:
        - Low uncertainty (P/O <= 2): pure arithmetic PERT mean
        - High uncertainty (P/O >= 10): pure geometric PERT mean
        - Medium: smooth log-interpolation between the two

        Includes fallbacks when only partial estimates are provided.
        """
        if self.time_mode == 'inherited':
            return 0.0
        o, m, p = self.time_o, self.time_m, self.time_p
        
        # Fallback 1: Only M is provided
        if m > 0 and o == 0 and p == 0:
            return m
            
        # Fallback 2: Only O and P are provided
        if m == 0 and o > 0 and p > 0:
            return math.sqrt(o * p)
            
        # Fallback 3: All missing
        if o == 0 and m == 0 and p == 0:
            return 1.0

        if o <= 0: o = 0.1
        if m < o: m = o
        if p < m: p = m
            
        e_arith = (o + 4*m + p) / 6.0
        try:
            e_log = math.exp((math.log(o) + 4*math.log(m) + math.log(p)) / 6.0)
        except ValueError:
            e_log = e_arith
            
        ratio = p / o if o > 0 else 1
        
        if ratio <= 2:
            w = 0
        elif 2 < ratio < 10:
            w = (math.log(ratio) - math.log(2)) / (math.log(10) - math.log(2))
        else:
            w = 1
            
        return round((1 - w) * e_arith + w * e_log, 2)

    def to_dict(self):
        d = asdict(self)
        d['time'] = self.time  # include the derived blended PERT estimate
        return d

    @classmethod
    def from_dict(cls, data):
        data.pop('time', None)
        # Historical rename: `effort` → `difficulty`. Some old DB rows or
        # tests still use the legacy key.
        if 'difficulty' not in data and 'effort' in data:
            data['difficulty'] = data.pop('effort')
        return cls(**data)


@dataclass
class Event:
    """An activation gate for a set of dormant nodes.

    An Event has exactly one trigger: manual (user clicks "trigger"),
    date-based (`trigger_date` elapses), or node-based (`trigger_node`
    is marked Done). When it fires, every dormant node attached to it
    flips to active — see event_manager.EventManager.
    """
    name: str
    description: str = ""
    status: str = "Pending"  # Pending | Triggered
    trigger_date: Optional[str] = None   # ISO date string — used for date-based triggers
    trigger_node: Optional[str] = None   # Node name — used for node-completion triggers

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
