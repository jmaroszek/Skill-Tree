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

# Status constants. The full enum is small but referenced from many files;
# importing the constants prevents typos that would silently break filtering
# and scoring (a misspelled "Block" would never compare equal to "Blocked").
STATUS_OPEN = 'Open'
STATUS_BLOCKED = 'Blocked'
STATUS_DONE = 'Done'
ALL_STATUSES = (STATUS_OPEN, STATUS_BLOCKED, STATUS_DONE)


@dataclass
class Node:
    """A task, goal, or reference in the graph.

    `name` is the primary key — renaming a node cascades through edges,
    overrides, goal orderings, and events (see GraphManager.rename_node).
    `time_mode='inherited'` means a parent node draws its time estimate
    from its hard prerequisites rather than its own time_o/m/p fields.
    `value_mode='inherited'` is the symmetric flag for ratings: when set,
    the node's intrinsic value AND its own effort cost are both zeroed
    in scoring, so the node is a pure structural conduit. Its priority
    score depends entirely on the cascade from its descendants — value,
    interest, and effort all "inherit" from children. Use for container-
    only Learn/Goal nodes that shouldn't inject their own ratings into
    their subtree.
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
    context: Optional[str] = None
    subcontext: Optional[str] = None
    obsidian_path: Optional[str] = None
    google_drive_path: Optional[str] = None
    website: Optional[str] = None
    dormant: int = 0
    time_mode: str = 'manual'  # 'manual', 'inherited', or 'habit'
    value_mode: str = 'manual'  # 'manual' or 'inherited'
    # Habit-mode breakdown — preserved across mode toggles so re-enabling
    # Habit restores the user's last (duration, intensity) inputs. The
    # canonical hours used by scoring still live in time_o/m/p; these are
    # the source of truth for repopulating the habit form.
    habit_duration: float = 0.0
    habit_duration_unit: str = 'weeks'         # 'days' | 'weeks' | 'months' | 'years'
    habit_intensity_o: float = 0.0
    habit_intensity_m: float = 0.0
    habit_intensity_p: float = 0.0
    habit_intensity_unit: str = 'min_per_day'  # '{min|hr}_per_{day|week}'
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
        if self.time_mode not in ('manual', 'inherited', 'habit'):
            self.time_mode = 'manual'
        if self.value_mode not in ('manual', 'inherited'):
            self.value_mode = 'manual'
        self.habit_duration = float(self.habit_duration) if self.habit_duration else 0.0
        self.habit_intensity_o = float(self.habit_intensity_o) if self.habit_intensity_o else 0.0
        self.habit_intensity_m = float(self.habit_intensity_m) if self.habit_intensity_m else 0.0
        self.habit_intensity_p = float(self.habit_intensity_p) if self.habit_intensity_p else 0.0
        if self.habit_duration_unit not in ('days', 'weeks', 'months', 'years'):
            self.habit_duration_unit = 'weeks'
        if self.habit_intensity_unit not in (
            'min_per_day', 'hr_per_day', 'min_per_week', 'hr_per_week'
        ):
            self.habit_intensity_unit = 'min_per_day'
        # Note: time_o/m/p are NOT zeroed when time_mode='inherited'. The
        # `time` property short-circuits to 0 for inherited mode regardless,
        # so the stored values are inert at read time — and preserving them
        # means a user who toggles inherited→manual gets their original
        # estimates back instead of losing them silently. Same precedent
        # for value_mode: v/i/d are preserved even when 'inherited' so a
        # toggle back to 'manual' restores the user's original ratings.

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
            
        # `o > 0` is guaranteed by the clamp on line 97; the conditional was
        # dead code preserved from earlier defensive patterns.
        ratio = p / o
        
        if ratio <= 2:
            w = 0
        elif 2 < ratio < 10:
            w = (math.log(ratio) - math.log(2)) / (math.log(10) - math.log(2))
        else:
            w = 1
            
        return round((1 - w) * e_arith + w * e_log, 2)

    @property
    def is_container(self) -> bool:
        """True when both ratings and time inherit from descendants.

        A pure structural conduit: contributes no own intrinsic value, no
        own effort, and no own time to scoring. Such nodes are skipped by
        the recommender entirely — their children, if any, are surfaced
        instead. Cascade still flows through them (`_tv_dag` still walks
        their H/S edges), so they can act as connective tissue without
        ever being recommended themselves.
        """
        return self.value_mode == 'inherited' and self.time_mode == 'inherited'

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
