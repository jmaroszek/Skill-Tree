"""The trigger confirmation summary.

Firing takes every node an event holds, so this summary is the last place to
notice one you did not mean to release — the job the row checkboxes used to do
badly. These tests pin what it must say, particularly that it never claims to
wake a node that is already awake.
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
    def test_a_node_that_is_already_awake_is_not_promised_a_wake(self):
        text = _text(trigger_confirmation_body("Music", [
            _row("Composition"),
            _row("Audio for Video", dormant=0),
        ]))

        assert "1 node will wake now: Composition." in text
        assert "Audio for Video" not in text

    def test_an_event_holding_only_awake_nodes_reads_as_empty(self):
        text = _text(trigger_confirmation_body("E", [
            _row("A", dormant=0), _row("B", dormant=0),
        ]))

        assert "will wake now" not in text
        assert "no dormant nodes left to wake" in text


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


class TestAddToNow:
    """The flag lands when a node wakes, so the summary has to say which
    moment that is for each node."""

    def test_a_flagged_node_waking_now_is_named(self):
        row = _row("Flagged")
        row["now_on_trigger"] = True

        text = _text(trigger_confirmation_body("E", [row, _row("Plain")]))

        assert "Added to Now, if there is room: Flagged." in text

    def test_it_is_absent_when_nothing_is_flagged(self):
        assert "Added to Now" not in _text(
            trigger_confirmation_body("E", [_row("N1")]))

    def test_a_delayed_flagged_node_says_it_is_added_when_it_wakes(self):
        row = _row("Later", delay_days=14)
        row["now_on_trigger"] = True

        text = _text(trigger_confirmation_body("E", [row]))

        assert "then added to Now" in text
        assert "Added to Now, if there is room" not in text

    def test_a_collapsed_schedule_still_counts_the_flagged(self):
        rows = [_row(f"N{i}", delay_days=7 * (i + 1)) for i in range(6)]
        for row in rows[:2]:
            row["now_on_trigger"] = True

        text = _text(trigger_confirmation_body("E", rows))

        assert "2 of them will be added to Now when they wake." in text
