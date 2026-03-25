from dataclasses import dataclass, asdict
from typing import Optional
import math

# Edge type constants used across the codebase
EDGE_NEEDS_HARD = 'Needs_Hard'
EDGE_NEEDS_SOFT = 'Needs_Soft'
EDGE_HELPS = 'Helps'
EDGE_RESOURCE = 'Resource'


@dataclass
class Node:
    """
    Represents a Node in the Skill Tree.
    """
    name: str               # Primary key
    type: str               # [Learn, Goal, Habit, Resource]
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
    frequency: Optional[str] = None          # Daily, Weekly, Monthly, Yearly
    session_lower: Optional[float] = None    # Minutes (lower bound)
    session_expected: Optional[float] = None # Minutes (expected)
    session_upper: Optional[float] = None    # Minutes (upper bound)
    habit_status: Optional[str] = None       # Active, Paused, Retired
    progress: Optional[int] = None           # 0-100
    website: Optional[str] = None
    dormant: int = 0
    priority_score: Optional[float] = None

    def __post_init__(self):
        """Coerce and validate field types after construction."""
        self.value = int(self.value) if self.value is not None else 5
        self.time_o = float(self.time_o) if self.time_o else 0.0
        self.time_m = float(self.time_m) if self.time_m else 0.0
        self.time_p = float(self.time_p) if self.time_p else 0.0
        self.interest = int(self.interest) if self.interest is not None else 5
        self.difficulty = int(self.difficulty) if self.difficulty is not None else 5
        self.value = max(1, min(10, self.value))
        self.interest = max(1, min(10, self.interest))
        self.difficulty = max(1, min(10, self.difficulty))
        if self.progress is not None:
            self.progress = max(0, min(100, int(self.progress)))
        if self.session_lower is not None:
            self.session_lower = float(self.session_lower)
        if self.session_expected is not None:
            self.session_expected = float(self.session_expected)
        if self.session_upper is not None:
            self.session_upper = float(self.session_upper)
        self.dormant = int(self.dormant) if self.dormant is not None else 0

    @property
    def time(self) -> float:
        """Calculates blended PERT time estimation.

        Uses a weighted blend of arithmetic and logarithmic (geometric) means:
        - Low uncertainty (P/O <= 2): pure arithmetic PERT mean
        - High uncertainty (P/O >= 10): pure geometric PERT mean
        - Medium: smooth log-interpolation between the two

        Includes fallbacks when only partial estimates are provided.
        """
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
        """Returns dictionary representation of the node."""
        d = asdict(self)
        d['time'] = self.time
        return d

    @classmethod
    def from_dict(cls, data):
        """Creates a Node instance from a dictionary."""
        data.pop('time', None)
        if 'difficulty' not in data and 'effort' in data:
            data['difficulty'] = data.pop('effort')
        return cls(**data)


@dataclass
class Event:
    """Represents an Event — an activation gate for dormant nodes."""
    name: str
    description: str = ""
    status: str = "Pending"  # Pending | Triggered
    trigger_date: str = None  # ISO date string or None for manual-only

    def __post_init__(self):
        self.trigger_date = self.trigger_date or None

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)
