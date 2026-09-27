"""Node, event and alias names are one line of text of a sane length.

Names are identifiers. They key the database and travel through menus, the
canvas and hidden inputs, so a pasted newline or tab, or a paragraph pasted
into the name field, made a node that no list could show properly.
"""
import pytest

from config import ConfigManager
from event_manager import EventManager
from graph_manager import GraphManager
from graph_rules import NAME_MAX_LENGTH, name_problem
from models import Event, Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                status="Open", context="Mind")


class TestRule:
    @pytest.mark.parametrize("name", [
        "Sleep", "A|B", 'Say "hi"', "It's", "C:\\path", "Café au lait",
        "👨\u200d👩\u200d👧 family",  # joiners inside an emoji are fine
        "x" * NAME_MAX_LENGTH,
    ])
    def test_ordinary_names_pass(self, name):
        assert name_problem(name, "Node name") is None

    @pytest.mark.parametrize("name, fragment", [
        ("", "required"),
        ("   ", "required"),
        (None, "required"),
        (" Sleep", "start or end with a space"),
        ("Sleep\n", "start or end with a space"),
        ("Line one\nLine two", "single line"),
        ("Tab\there", "single line"),
        ("Para\u2029graph", "single line"),
        ("x" * (NAME_MAX_LENGTH + 1), "Keep it to"),
    ])
    def test_problem_names_are_explained(self, name, fragment):
        assert fragment in name_problem(name, "Node name")


def test_graph_manager_refuses_a_bad_new_name():
    manager = GraphManager()
    with pytest.raises(ValueError, match="single line"):
        manager.add_node(_node("Two\nlines"))
    assert manager.get_all_nodes() == []


def test_graph_manager_refuses_a_bad_rename():
    manager = GraphManager()
    manager.add_node(_node("Sleep"))
    with pytest.raises(ValueError, match="Keep it to"):
        manager.rename_node("Sleep", "z" * (NAME_MAX_LENGTH + 1))
    assert manager.get_node("Sleep") is not None


def test_aliases_follow_the_same_rule():
    # Title case re-joins words with single spaces, which already removes a
    # tab. With formatting off, the rule is what stops it.
    ConfigManager.set_name_formatting({"mode": "none"})
    manager = GraphManager()
    manager.add_node(_node("Sleep"))
    with pytest.raises(ValueError, match="Alias must be a single line"):
        manager.set_aliases("Sleep", ["Shut\teye"])


def test_event_names_follow_the_same_rule():
    events = EventManager()
    with pytest.raises(ValueError, match="Event name must be a single line"):
        events.add_event(Event(name="Trip\n2027"))
    events.add_event(Event(name="Trip"))
    with pytest.raises(ValueError, match="Event name can't start or end"):
        events.update_event("Trip", Event(name="Trip "))


def test_renaming_an_event_onto_another_says_so():
    """It raised a raw sqlite3.IntegrityError the save path didn't catch."""
    events = EventManager()
    events.add_event(Event(name="Trip"))
    events.add_event(Event(name="Move"))
    with pytest.raises(ValueError, match="'Move' already exists"):
        events.update_event("Trip", Event(name="Move"))
    assert events.get_event("Trip") is not None
