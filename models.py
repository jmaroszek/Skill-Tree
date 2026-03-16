from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Node:
    """
    Represents a Node in the Skill Tree.
    """
    name: str               # Primary key
    type: str               # [Goal, Topic, Skill, Habit, Resource]
    description: str
    value: int              # 1-10
    time: float             # Hours (can be fractional, e.g. 0.5)
    interest: int           # 1-10
    effort: int             # mapped from [Easy, Medium, Hard] -> [1, 2, 3]
    status: str             # [Open, In Progress, Blocked, Done]
    competence: Optional[str] = None    # [Reciter, Processor, Thinker, Creator, Master, Innovator]
    context: Optional[str] = None       # [None, Mind, Body, Social, Action]
    subcontext: Optional[str] = None
    priority_score: Optional[float] = None  # Computed at runtime, never stored in DB

    def __post_init__(self):
        """Coerce and validate field types after construction."""
        self.value = int(self.value) if self.value is not None else 5
        self.time = float(self.time) if self.time is not None else 1.0
        self.interest = int(self.interest) if self.interest is not None else 5
        self.effort = int(self.effort) if self.effort is not None else 2
        self.value = max(1, min(10, self.value))
        self.interest = max(1, min(10, self.interest))
        self.effort = max(1, min(3, self.effort))
        self.time = max(0.1, self.time)

    def to_dict(self):
        """Returns dictionary representation of the node."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        """Creates a Node instance from a dictionary."""
        return cls(**data)
