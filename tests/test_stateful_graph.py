"""Random sequences of real graph operations keep the graph consistent (P6.1).

Hypothesis drives the same entry points the UI uses (node_commands, the
GraphManager and EventManager methods callbacks call) over a small pool of
names, some of them hostile, so operations collide: renames onto existing
names, edges that would close a cycle, deletes of nodes with relationships.
A refusal (ValueError) is fine. Anything else must leave these true after
every step:

- statuses need no repair: recompute_all_statuses() changes nothing;
- the Needs edges form no cycle;
- at most one Helps row per pair of nodes;
- a node is dormant exactly when it sits in an event that hasn't fired;
- done_date is set exactly on Done nodes;
- no setting names a node that no longer exists;
- no two nodes share a name, ignoring case;
- every score is a finite number, and scoring twice gives the same scores.

It runs 25 sequences by default, to keep CI quick. For a deep run:
    STATEFUL_EXAMPLES=300 pytest tests/test_stateful_graph.py
"""
import math
import os
import tempfile
from pathlib import Path

import networkx as nx
from hypothesis import HealthCheck, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule

import database
from config import ConfigManager
from event_manager import EventManager
from graph_manager import GraphManager
from models import (EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, STATUS_DONE,
                    Event, Node)
import node_commands

# Half the draws come from a few plain names, so operations keep meeting the
# same nodes; the rest are hostile ("sleep" collides with "Sleep" by case).
CORE = ["Sleep", "Rest", "Nap", "Walk"]
HOSTILE = ["A|B", "O'Brien \"quoted\"", "back\\slash", "a: b", "Grüße", "Moon 🌙", "sleep"]
NAMES = CORE + HOSTILE
TYPES = ["Learn", "Action", "Resource", "Goal", "Milestone"]
EDGE_TYPES = [EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, EDGE_HELPS]
EVENTS = ["Winter", "Launch|Day"]

names = st.one_of(st.sampled_from(CORE), st.sampled_from(HOSTILE))


def _refused(action):
    """Run one operation; a ValueError is the app saying no, which is fine."""
    try:
        return action()
    except ValueError:
        return None


class GraphMachine(RuleBasedStateMachine):
    @initialize()
    def fresh_database(self):
        self._dir = tempfile.mkdtemp(prefix="stateful-")
        path = str(Path(self._dir) / "graph.db")
        database.get_db_path = lambda: path
        database._initialized = False
        database.init_db()
        self.manager = GraphManager()
        self.events = EventManager()

    # --- Operations ---------------------------------------------------------

    @rule(name=names, node_type=st.sampled_from(TYPES), now=st.booleans())
    def add_node(self, name, node_type, now):
        _refused(lambda: self.manager.add_node(Node(
            name=name, type=node_type, description="", value=5, time_o=1.0,
            time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
            context="Mind", now=1 if now and node_type != "Goal" else 0)))

    # (rule() reserves "target", hence "dest".)
    @rule(source=names, dest=names, edge_type=st.sampled_from(EDGE_TYPES))
    def add_edge(self, source, dest, edge_type):
        if source != dest and self.manager.get_node(source) and self.manager.get_node(dest):
            _refused(lambda: self.manager.add_edge(source, dest, edge_type))

    @rule(source=names, dest=names, edge_type=st.sampled_from(EDGE_TYPES))
    def remove_edge(self, source, dest, edge_type):
        _refused(lambda: self.manager.remove_edge(source, dest, edge_type))

    @rule(name=names)
    def toggle_done(self, name):
        # What the context menu's Toggle Done does.
        _refused(lambda: node_commands.handle_toggle_done(self.manager, {"id": name}))

    @rule(name=names)
    def toggle_now(self, name):
        node = self.manager.get_node(name)
        if node is None or node.type == "Goal":
            return
        node.now = 0 if node.now else 1
        _refused(lambda: self.manager.update_node(node))

    @rule(old=names, new=names)
    def rename(self, old, new):
        if self.manager.get_node(old):
            _refused(lambda: self.manager.rename_node(old, new))

    @rule(name=names)
    def delete(self, name):
        if self.manager.get_node(name):
            _refused(lambda: self.manager.delete_node(name))

    @rule(name=names)
    def prioritize_goal(self, name):
        node = self.manager.get_node(name)
        if node is not None and node.type == "Goal":
            goals = [g for g in ConfigManager.get_priority_goals() if g != name]
            ConfigManager.set_priority_goals([name] + goals[:2])

    @rule(event=st.sampled_from(EVENTS), trigger=names)
    def add_event(self, event, trigger):
        if self.events.get_event(event) is None and self.manager.get_node(trigger):
            _refused(lambda: self.events.add_event(Event(name=event, trigger_nodes=[trigger])))

    @rule(event=st.sampled_from(EVENTS), name=names)
    def put_to_sleep(self, event, name):
        if self.events.get_event(event) and self.manager.get_node(name):
            _refused(lambda: self.events.add_node_to_event(event, name))

    @rule(event=st.sampled_from(EVENTS))
    def fire_event(self, event):
        if self.events.get_event(event):
            _refused(lambda: self.events.trigger_event_manually(event))

    @rule()
    def restart(self):
        """What a relaunch does before the window opens."""
        self.events.check_pending_activations()
        self.events.reconcile_dormant_flags()

    # --- Invariants ---------------------------------------------------------

    @invariant()
    def statuses_need_no_repair(self):
        if hasattr(self, "manager"):
            assert self.manager.recompute_all_statuses() == 0

    @invariant()
    def needs_edges_form_no_cycle(self):
        if not hasattr(self, "manager"):
            return
        graph = nx.DiGraph()
        graph.add_edges_from((e["source"], e["target"]) for e in self.manager.get_edges()
                             if e["type"] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT))
        assert nx.is_directed_acyclic_graph(graph)

    @invariant()
    def one_helps_row_per_pair(self):
        if not hasattr(self, "manager"):
            return
        pairs = [frozenset((e["source"], e["target"])) for e in self.manager.get_edges()
                 if e["type"] == EDGE_HELPS]
        assert len(pairs) == len(set(pairs))

    @invariant()
    def dormant_means_waiting_on_an_event(self):
        if hasattr(self, "events"):
            assert self.events.reconcile_dormant_flags() == 0

    @invariant()
    def done_date_marks_done_nodes(self):
        if not hasattr(self, "manager"):
            return
        for node in self.manager.get_all_nodes(include_dormant=True):
            assert (node.done_date is not None) == (node.status == STATUS_DONE), node.name

    @invariant()
    def settings_name_only_existing_nodes(self):
        if not hasattr(self, "manager"):
            return
        existing = {n.name for n in self.manager.get_all_nodes(include_dormant=True)}
        assert set(ConfigManager.get_priority_goals()) <= existing
        assert set(ConfigManager.get_goal_order() or []) <= existing

    @invariant()
    def names_are_unique_ignoring_case(self):
        if not hasattr(self, "manager"):
            return
        folded = [n.name.casefold() for n in self.manager.get_all_nodes(include_dormant=True)]
        assert len(folded) == len(set(folded))

    @invariant()
    def scores_are_finite_and_repeatable(self):
        if not hasattr(self, "manager"):
            return
        now = self.manager.get_now_nodes()
        first = {n.name: n.priority_score for n in self.manager.calculate_priority_scores(now)}
        again = {n.name: n.priority_score for n in self.manager.calculate_priority_scores(now)}
        assert all(math.isfinite(score) for score in first.values())
        assert first == again


GraphMachine.TestCase.settings = settings(
    max_examples=int(os.environ.get("STATEFUL_EXAMPLES", "25")),
    stateful_step_count=30, deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
TestGraphMachine = GraphMachine.TestCase
