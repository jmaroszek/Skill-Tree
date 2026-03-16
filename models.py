from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Node:
    """
    Represents a Node in the Skill Tree.
    """
    name: str # Primary key
    type: str # [Goal, Topic, Skill, Habit, Resource]
    description: str
    value: int # 1-10
    time: int # Hours
    interest: int # 1-10
    effort: int # mapped from [Easy, Medium, Hard] -> [1, 2, 3]
    status: str # [Open, In Progress, Blocked, Done]
    competence: Optional[str] = None # [Reciter, Processor, Thinker, Creator, Master, Innovator]
    context: Optional[str] = None # [Mind, Body, Social, Action (Implied but in subcontexts)]
    subcontext: Optional[str] = None
    
    # Priority Score: Dynamically assigned at runtime depending on the graph
    priority_score: Optional[float] = None
    
    def to_dict(self):
        """Returns dictionary representation of the node"""
        return asdict(self)
        
    @classmethod
    def from_dict(cls, data):
        """Creates a Node instance from a dictionary"""
        return cls(**data)
