"""Core data models for the Skill Tree.

A `Node` is the fundamental unit — a task, goal, or reference that the
scoring algorithm can rank. Nodes are related to one another by typed
edges (see the EDGE_* constants).

An `Event` is an activation gate: zero-or-more dormant nodes can be
attached to it, and when the event triggers (manually, by date, or when
a specific node completes) the dormant nodes are added back into play.
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


def pert_blend_weight(ratio: float) -> float:
    """Weight w(r) that blends the arithmetic PERT mean toward the geometric
    (log) one as the uncertainty ratio r = p/o grows.

    0 for r <= 2 (tight bracket, trust the linear mean), 1 for r >= 10 (wide
    bracket, lean fully geometric), log-interpolated between. This is the
    single source of truth for the blend weight — both the point estimate
    (`blend_time_estimate`) and the Monte Carlo sampler
    (`simulation.blended_pert_sample`) call it, so the headline number and the
    simulated distribution can never drift apart.
    """
    if ratio <= 2:
        return 0.0
    if ratio >= 10:
        return 1.0
    return (math.log(ratio) - math.log(2)) / (math.log(10) - math.log(2))


def blend_time_estimate(o: float, m: float, p: float) -> float:
    """Blend optimistic / most-likely / pessimistic values into one expected
    figure. Shared by the forecast estimate (`Node.time`) and the captured
    actual time so both are computed identically and stay comparable.

    - Only M supplied: return M.
    - Only O and P (two-point): geometric mean ``sqrt(O*P)``.
    - All three: weighted blend of the arithmetic and geometric PERT means,
      shifting toward geometric as the P/O uncertainty ratio grows.
    - Nothing supplied: return 1.0.

    Accepts None for any argument (treated as 0) so it can take nullable
    actual-time fields directly.
    """
    o = o or 0.0
    m = m or 0.0
    p = p or 0.0

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

    w = pert_blend_weight(p / o)

    return round((1 - w) * e_arith + w * e_log, 2)


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
    habit_intensity_unit: str = 'min_per_day'  # '{min|hr}_per_{day|week|session}'
    # Selected weekdays for per-session cadence, comma-separated indices
    # (0=Mon … 6=Sun). Only meaningful when habit_intensity_unit ends in
    # '_per_session'; the count of days drives sessions/week. Defaults to all
    # seven, which makes a per-session estimate equivalent to "every day".
    habit_days: str = '0,1,2,3,4,5,6'
    # Time-calibration — actual time spent, captured when the node is marked
    # Done. Stored in canonical hours; None means "not captured". actual_time_unit
    # preserves the unit the user entered, for display round-trip.
    actual_time_lower: Optional[float] = None
    actual_time_upper: Optional[float] = None
    actual_time_point: Optional[float] = None
    actual_time_unit: Optional[str] = None
    # Set when the user picks "Don't ask again" in calibration review — the
    # node is then permanently excluded from the review cycle.
    calibration_dismissed: int = 0
    # Now flag: 1 when the user is currently working on this node.
    # Orthogonal to status — an Open or Blocked node can be Now. The flag
    # also drives the "Now" section on the Next tab and the amber border
    # encoding on every canvas. start_date/done_date are auto-stamped by
    # GraphManager.update_node: start_date on the first 0→1 now flip,
    # done_date on the first transition to Done. Re-flipping Now does not
    # touch dates. reflect_value/interest/difficulty are nullable mirror
    # columns for retrospective re-rating (schema only; UI lands later).
    now: int = 0
    start_date: Optional[str] = None
    done_date: Optional[str] = None
    reflect_value: Optional[int] = None
    reflect_interest: Optional[int] = None
    reflect_difficulty: Optional[int] = None
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
        self.calibration_dismissed = int(self.calibration_dismissed) if self.calibration_dismissed else 0
        self.now = int(self.now) if self.now is not None else 0
        if self.time_mode not in ('manual', 'inherited', 'habit'):
            self.time_mode = 'manual'
        if self.value_mode not in ('manual', 'inherited'):
            self.value_mode = 'manual'
        # Container types always inherit TIME — their duration is the sum of
        # their children's, never an own estimate. This holds for Goals and
        # Milestones alike (mirrors resolve_time_mode at the save layer, and
        # makes it true on every read including legacy DB rows).
        if self.type in ('Goal', 'Milestone'):
            self.time_mode = 'inherited'
        # Milestones additionally inherit VALUE: they are transparent
        # checkpoints marking an achievement, not the effort to reach it, so
        # their own ratings must not enter scoring (a placeholder value would
        # leak into the cascade of whatever unlocks them). With both modes
        # inherited a Milestone is a pure structural conduit on every read path
        # (intrinsic_value and Node.time both short-circuit to 0) — which is
        # what lets the Goal ranker treat Milestones transparently with no
        # in-memory patch. Goals are exempt: they legitimately carry their own
        # value (see docs/modeling.md).
        if self.type == 'Milestone':
            self.value_mode = 'inherited'
        self.habit_duration = float(self.habit_duration) if self.habit_duration else 0.0
        self.habit_intensity_o = float(self.habit_intensity_o) if self.habit_intensity_o else 0.0
        self.habit_intensity_m = float(self.habit_intensity_m) if self.habit_intensity_m else 0.0
        self.habit_intensity_p = float(self.habit_intensity_p) if self.habit_intensity_p else 0.0
        if self.habit_duration_unit not in ('days', 'weeks', 'months', 'years'):
            self.habit_duration_unit = 'weeks'
        if self.habit_intensity_unit not in (
            'min_per_day', 'hr_per_day', 'min_per_week', 'hr_per_week',
            'min_per_session', 'hr_per_session',
        ):
            self.habit_intensity_unit = 'min_per_day'
        # Normalize habit_days: accept a list/tuple or a comma-separated string,
        # keep only valid weekday indices (0-6), dedupe, and sort.
        raw_days = self.habit_days
        if isinstance(raw_days, (list, tuple, set)):
            parts = raw_days
        else:
            parts = str(raw_days or '').split(',')
        valid = sorted({
            d for d in (
                int(p) for p in (
                    str(x).strip() for x in parts
                ) if p.lstrip('-').isdigit()
            ) if 0 <= d <= 6
        })
        self.habit_days = ','.join(str(d) for d in valid)
        # Note: time_o/m/p are NOT zeroed when time_mode='inherited'. The
        # `time` property short-circuits to 0 for inherited mode regardless,
        # so the stored values are inert at read time — and preserving them
        # means a user who toggles inherited→manual gets their original
        # estimates back instead of losing them silently. Same precedent
        # for value_mode: v/i/d are preserved even when 'inherited' so a
        # toggle back to 'manual' restores the user's original ratings.

    @property
    def time(self) -> float:
        """Blended PERT time estimate (in hours), or 0 for inherited-mode
        nodes. See `blend_time_estimate` for the blend rules."""
        if self.time_mode == 'inherited':
            return 0.0
        return blend_time_estimate(self.time_o, self.time_m, self.time_p)

    @property
    def is_container(self) -> bool:
        """True when EITHER ratings or time inherit from descendants.

        This is the user-facing notion of "container": a node that draws at
        least some of its numbers from the work beneath it rather than holding
        them itself. It still competes for recommendations as long as it keeps
        one own dimension — e.g. a node with own ratings but inherited time is
        a container, and is still ranked. See `is_pure_container` for the
        stricter "nothing of its own" case that scoring excludes entirely.
        """
        return self.value_mode == 'inherited' or self.time_mode == 'inherited'

    @property
    def is_pure_container(self) -> bool:
        """True when BOTH ratings and time inherit from descendants.

        A pure structural conduit: contributes no own intrinsic value, no
        own effort, and no own time to scoring. Such nodes are skipped by
        the recommender entirely — their children, if any, are surfaced
        instead. Cascade still flows through them (`_tv_dag` still walks
        their H/S edges), so they can act as connective tissue without
        ever being recommended themselves. This is the scoring-exclusion
        gate; `is_container` is the broader user-facing label.
        """
        return self.value_mode == 'inherited' and self.time_mode == 'inherited'

    def to_dict(self):
        # Shallow-copy the field values rather than dataclasses.asdict(),
        # which recursively deep-copies every field. All Node fields are
        # immutable primitives (str/int/float/None) and __post_init__ adds no
        # non-field attributes, so __dict__ holds exactly the fields and a
        # shallow copy is observationally identical to asdict — but ~7x faster.
        # to_dict runs once per node on every canvas render (generate_elements),
        # so this is a hot path.
        d = dict(self.__dict__)
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
