from dataclasses import dataclass, asdict
from typing import Optional
import math

@dataclass
class Node:
    """
    Represents a Node in the Skill Tree.
    """
    name: str               # Primary key
    type: str               # [Goal, Topic, Skill, Habit, Resource]
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

    @property
    def time(self) -> float:
        """Calculates blended PERT time estimation."""
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
