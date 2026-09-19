"""The trigger confirmation summary.

Firing takes every node an event holds, so this summary is the last place to
notice one you did not mean to release — the job the row checkboxes used to do
badly. These tests pin what it must say, particularly that it never claims to
wake a node some other event already woke.
"""

from datetime import date, timedelta

from events_layout import trigger_confirmation_body
from models import Node


def _node(name, dormant=1):
    return Node(
        name=name, type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open", dormant=dormant,
    )


def _row(name, *, delay_days=0, activated=False, dormant=1):
    return {"node": _node(name, dormant=dormant), "delay_days": delay_days,
            "activated": activated}


def _text(children):
    """Flattens a Dash tree to one string so a test can read the copy."""
    if children is None:
        return ""
    if isinstance(children, str):
        return children
    if isinstance(children, list):
        return " ".join(_text(c) for c in children)
    return _text(getattr(children, "children", None))


class TestWhatItSays:
    def test_it_names_the_nodes_waking_now(self):
        body = trigger_confirmation_body("Adopt a Dog", [
            _row("Buy supplies"), _row("Find a vet"),
        ])

        text = _text(body)
        assert 'Trigger "Adopt a Dog"?' in text
        assert "2 nodes will wake now: Buy supplies, Find a vet." in text

    def test_one_node_reads_in_the_singular(self):
        body = trigger_confirmation_body("E", [_row("Only One")])

        assert "1 node will wake now: Only One." in _text(body)

    def test_delayed_nodes_are_listed_with_their_wake_dates(self):
        body = trigger_confirmation_body("E", [
            _row("Now"), _row("Later", delay_days=14),
        ])

        text = _text(body)
        expected = (date.today() + timedelta(days=14))
        stamp = f"{expected.strftime('%b')} {expected.day}"
        assert "1 will be scheduled for later:" in text
        assert "Later" in text and stamp in text

    def test_a_long_schedule_collapses_to_a_count(self):
        """Six wake dates stop being scannable."""
        rows = [_row(f"N{i}", delay_days=7 * (i + 1)) for i in range(6)]

        text = _text(trigger_confirmation_body("E", rows))

        assert "6 will be scheduled for later." in text
        assert "wakes" not in text

    def test_an_empty_event_says_so_plainly(self):
        body = trigger_confirmation_body("Write a Book", [])

        text = _text(body)
        assert "no dormant nodes left to wake" in text
        assert "just mark it Triggered" in text


class TestAlreadyAwake:
    """Without this line the summary lies, and multi-event membership makes
    that happen on real data."""

    def test_a_node_another_event_woke_is_counted_separately(self):
        body = trigger_confirmation_body("Music", [
            _row("Composition"),
            _row("Audio for Video", dormant=0),
        ])

        text = _text(body)
        assert "1 node will wake now: Composition." in text
        assert "1 node already awake: Audio for Video." in text

    def test_it_is_absent_when_nothing_is_already_awake(self):
        assert "already awake" not in _text(
            trigger_confirmation_body("E", [_row("N1")]))

    def test_an_event_holding_only_awake_nodes_promises_no_wakes(self):
        text = _text(trigger_confirmation_body("E", [
            _row("A", dormant=0), _row("B", dormant=0),
        ]))

        assert "will wake now" not in text
        assert "2 nodes already awake: A, B." in text


class TestAlreadyFiredRows:
    def test_rows_this_event_already_activated_are_left_out(self):
        """They are this event's own past work, not part of what it is about
        to do."""
        body = trigger_confirmation_body("E", [
            _row("Old", activated=True, dormant=0),
            _row("New"),
        ])

        text = _text(body)
        assert "1 node will wake now: New." in text
        assert "Old" not in text

    def test_an_event_with_nothing_left_pending_reads_as_empty(self):
        text = _text(trigger_confirmation_body("E", [
            _row("Old", activated=True, dormant=0),
        ]))

        assert "no dormant nodes left to wake" in text
