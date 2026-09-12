"""Unblocking steps: the work the Next tab pins toward a Now node you can't start.

Replaces the manual-priority-override suite. The override anchored on one node
and pinned a computed set above the ranking; the only part of that worth
keeping was surfacing a blocked target's actionable prerequisites, and that now
hangs off the Now list instead.
"""

import pytest

from callback_helpers import format_suggestions_table
from config import ConfigManager
from graph_manager import GraphManager
from models import Node, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT


@pytest.fixture
def mgr():
    return GraphManager()


def _node(name, **overrides):
    fields = dict(
        name=name, type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open", context="Mind",
    )
    fields.update(overrides)
    return Node(**fields)


def _chain(mgr, target, *prereqs, **kw):
    """`target` gated behind each of `prereqs` by a hard edge."""
    mgr.add_node(_node(target, **kw))
    for name in prereqs:
        mgr.add_node(_node(name))
        mgr.add_edge(name, target, EDGE_NEEDS_HARD)
    return mgr.get_node(target)


def _names(steps):
    return [node.name for node, _ in steps]


# ---------------------------------------------------------------------------
# Which targets earn steps
# ---------------------------------------------------------------------------

def test_an_actionable_target_earns_no_steps(mgr):
    """Its own row is the answer, and its hard prereqs are Done by definition."""
    mgr.add_node(_node("Ready"))
    assert mgr.get_node("Ready").status == "Open"
    assert mgr.get_unblocking_steps(["Ready"]) == []


def test_a_blocked_target_earns_its_prerequisites(mgr):
    _chain(mgr, "Publishing", "Editing", "Drafting")
    assert mgr.get_node("Publishing").status == "Blocked"
    assert sorted(_names(mgr.get_unblocking_steps(["Publishing"]))) == ["Drafting", "Editing"]


def test_a_goal_target_earns_steps_even_though_it_is_never_scorable(mgr):
    """Goals carry a flat -1.0 by type, which is exactly the case steps exist for."""
    _chain(mgr, "Career", "Resume", type="Goal")
    assert sorted(_names(mgr.get_unblocking_steps(["Career"]))) == ["Resume"]


def test_a_target_whose_subtree_is_entirely_blocked_earns_nothing(mgr):
    """Filtering on a non-negative score drops prereqs that are blocked in turn."""
    _chain(mgr, "Far", "Near")
    mgr.add_node(_node("Deep"))
    mgr.add_edge("Deep", "Near", EDGE_NEEDS_HARD)
    mgr.update_node(_node("Deep", status="Blocked"))
    assert mgr.get_node("Near").status == "Blocked"
    assert _names(mgr.get_unblocking_steps(["Far"])) == []


def test_an_unknown_target_is_skipped(mgr):
    assert mgr.get_unblocking_steps(["Ghost"]) == []
    assert mgr.get_unblocking_steps([]) == []
    assert mgr.get_unblocking_steps([None]) == []


# ---------------------------------------------------------------------------
# Which steps, and how many
# ---------------------------------------------------------------------------

def test_steps_come_back_best_first_and_respect_the_limit(mgr):
    _chain(mgr, "Target", "Low", "Mid", "High")
    mgr.update_node(_node("Low", value=1, interest=1))
    mgr.update_node(_node("Mid", value=5, interest=5))
    mgr.update_node(_node("High", value=10, interest=10))

    assert _names(mgr.get_unblocking_steps(["Target"])) == ["High", "Mid", "Low"]
    assert _names(mgr.get_unblocking_steps(["Target"], limit=2)) == ["High", "Mid"]
    assert mgr.get_unblocking_steps(["Target"], limit=0) == []


def test_the_walk_is_transitive_not_just_direct_prerequisites(mgr):
    mgr.add_node(_node("Top"))
    mgr.add_node(_node("Middle"))
    mgr.add_node(_node("Bottom"))
    mgr.add_edge("Bottom", "Middle", EDGE_NEEDS_HARD)
    mgr.add_edge("Middle", "Top", EDGE_NEEDS_HARD)
    # Middle is blocked by Bottom, so only Bottom is startable.
    assert _names(mgr.get_unblocking_steps(["Top"])) == ["Bottom"]


def test_soft_prerequisites_are_not_steps(mgr):
    """Soft edges are preparation, not a gate — they can't be what unblocks you."""
    mgr.add_node(_node("Target"))
    mgr.add_node(_node("Gate"))
    mgr.add_node(_node("Nice"))
    mgr.add_edge("Gate", "Target", EDGE_NEEDS_HARD)
    mgr.add_edge("Nice", "Target", EDGE_NEEDS_SOFT)
    assert _names(mgr.get_unblocking_steps(["Target"])) == ["Gate"]


def test_each_step_is_named_with_the_target_it_serves(mgr):
    _chain(mgr, "Publishing", "Editing")
    assert mgr.get_unblocking_steps(["Publishing"])[0][1] == "Publishing"


def test_a_step_is_not_repeated_across_targets(mgr):
    """A prerequisite two Now nodes share belongs to the first that claims it."""
    mgr.add_node(_node("Shared"))
    for target in ("First", "Second"):
        mgr.add_node(_node(target))
        mgr.add_edge("Shared", target, EDGE_NEEDS_HARD)

    steps = mgr.get_unblocking_steps(["First", "Second"])
    assert steps == [(steps[0][0], "First")]
    assert steps[0][0].name == "Shared"


def test_a_target_is_never_its_own_step(mgr):
    """Every Now node is passed in as a target, so none can come back as a step."""
    _chain(mgr, "Target", "Prereq")
    steps = mgr.get_unblocking_steps(["Target", "Prereq"])
    assert _names(steps) == []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _scored(mgr, *pairs):
    """Add each node to the graph and hand back a copy carrying a score.

    priority_score is computed, never stored, so a node read back from the DB
    has None there and the 0-100 normalization would divide by nothing.
    """
    nodes = []
    for name, score in pairs:
        mgr.add_node(_node(name))
        nodes.append(_node(name, priority_score=score))
    return nodes


def _rows(table):
    return table[0].children


def _row_ids(table):
    return [row.id for row in _rows(table)]


def test_a_step_row_stays_an_ordinary_suggestion_row(mgr):
    """next_selection.js styles rows as a positional ALL-list through
    `.suggestion-bar-row`, so a step cannot be rendered as some other kind of
    element."""
    step, plain = _scored(mgr, ("Step", 10), ("Plain", 8))
    table = format_suggestions_table([step, plain], mgr,
                                     pinned_steps={"Step": "Publishing"})

    assert _row_ids(table) == [
        {"type": "suggestion-row", "index": "Step"},
        {"type": "suggestion-row", "index": "Plain"},
    ]
    assert all(row.className == "suggestion-bar-row" for row in _rows(table))


def test_a_step_shows_a_turnstile_and_its_target_and_leaves_the_ranking_at_one(mgr):
    step, plain = _scored(mgr, ("Step", 10), ("Plain", 8))
    table = format_suggestions_table([step, plain], mgr,
                                     pinned_steps={"Step": "Publishing"})

    step_row, plain_row = _rows(table)
    assert step_row.children[0].children == "↳"
    assert plain_row.children[0].children == "1"
    assert "Publishing" in str(step_row.children[1])
    assert "Publishing" not in str(plain_row.children[1])


def _step_context_line(mgr, step, target):
    """The rendered second line of a step row, as plain text."""
    mgr.add_node(step)
    mgr.add_node(target)
    scored = _node(step.name, context=step.context, subcontext=step.subcontext,
                   priority_score=10)
    table = format_suggestions_table([scored], mgr,
                                     pinned_steps={step.name: target.name})
    return _rows(table)[0].children[1].children[1].children


def _text(children):
    """Flatten a context line down to the strings it actually prints."""
    out = []
    def walk(node):
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
        else:
            walk(getattr(node, 'children', []))
    walk(children)
    return [t for t in out if t.strip() and t.strip() != "·"]


def test_a_step_beside_its_target_says_only_the_target(mgr):
    """Naming the target has already given away the whole context."""
    line = _step_context_line(
        mgr,
        _node("Newtons Laws", context="STEM", subcontext="Physics"),
        _node("Classical Mechanics", context="STEM", subcontext="Physics"),
    )
    assert _text(line) == ["toward ", "Classical Mechanics"]


def test_a_step_in_a_sibling_subcontext_keeps_the_subcontext(mgr):
    """Same context, different subcontext — the subcontext is the news."""
    line = _step_context_line(
        mgr,
        _node("Functions", context="STEM", subcontext="Math"),
        _node("Classical Mechanics", context="STEM", subcontext="Physics"),
    )
    assert _text(line) == ["toward ", "Classical Mechanics", "Math"]


def test_a_step_from_another_context_keeps_both(mgr):
    """A step from elsewhere in your life is exactly what shouldn't be trimmed."""
    line = _step_context_line(
        mgr,
        _node("Typing Speed", context="Self", subcontext="Productivity"),
        _node("Classical Mechanics", context="STEM", subcontext="Physics"),
    )
    assert _text(line) == ["toward ", "Classical Mechanics", "Self", "Productivity"]


def test_an_unresolvable_target_leaves_the_context_alone(mgr):
    """Nothing to compare against, so print everything rather than guess."""
    mgr.add_node(_node("Orphan", context="STEM", subcontext="Physics"))
    table = format_suggestions_table(
        [_node("Orphan", context="STEM", subcontext="Physics", priority_score=10)],
        mgr, pinned_steps={"Orphan": "Deleted Since"})
    assert _text(_rows(table)[0].children[1].children[1].children) == [
        "toward ", "Deleted Since", "STEM", "Physics"]


def test_without_steps_the_table_numbers_from_one(mgr):
    table = format_suggestions_table(_scored(mgr, ("A", 10), ("B", 8)), mgr)
    assert [row.children[0].children for row in _rows(table)] == ["1", "2"]


# ---------------------------------------------------------------------------
# The Now list itself — previously untested
# ---------------------------------------------------------------------------

def test_now_nodes_come_back_in_rank_order_and_exclude_dormant(mgr):
    mgr.add_node(_node("Second", now=2))
    mgr.add_node(_node("First", now=1))
    mgr.add_node(_node("Shelved", now=3, dormant=1))
    mgr.add_node(_node("Idle"))
    assert [n.name for n in mgr.get_now_nodes()] == ["First", "Second"]


def test_reorder_only_touches_nodes_already_on_the_list(mgr):
    """A stale card in the DOM must not be able to re-pin itself."""
    mgr.add_node(_node("A", now=1))
    mgr.add_node(_node("B", now=2))
    mgr.add_node(_node("Unpinned"))

    mgr.reorder_now_nodes(["B", "Unpinned", "A"])

    assert [n.name for n in mgr.get_now_nodes()] == ["B", "A"]
    assert mgr.get_node("Unpinned").now == 0


def test_the_step_count_is_configurable(mgr):
    _chain(mgr, "Target", "One", "Two", "Three")
    assert ConfigManager.get_unblocking_steps_per_now() == 3
    ConfigManager.set_unblocking_steps_per_now(1)
    assert ConfigManager.get_unblocking_steps_per_now() == 1
    assert len(mgr.get_unblocking_steps(
        ["Target"], limit=ConfigManager.get_unblocking_steps_per_now())) == 1
