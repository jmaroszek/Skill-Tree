"""The Wakes cell's Add to Now marker.

The flag is only a promise while the node is asleep. Once it wakes the intent is
spent, and the Awake badge is the honest report.
"""

from events_layout import _wakes_cell
from models import Node


def _en(*, dormant=1, now_on_trigger=False, activated=False, delay_days=0,
        activation_date=None):
    node = Node(
        name="N", type="Learn", description="", value=5,
        time_o=1, time_m=2, time_p=4, interest=5, difficulty=5,
        status="Open", dormant=dormant,
    )
    return {"node": node, "delay_days": delay_days, "activated": activated,
            "activation_date": activation_date, "now_on_trigger": now_on_trigger}


def _has_marker(cell):
    return isinstance(cell, list) and any(
        "dormant-now-marker" in (getattr(c, "className", "") or "") for c in cell)


class TestMarker:
    def test_a_flagged_sleeping_node_gets_the_marker(self):
        assert _has_marker(_wakes_cell(_en(now_on_trigger=True), None))

    def test_a_scheduled_flagged_node_gets_it_beside_its_date(self):
        cell = _wakes_cell(
            _en(now_on_trigger=True, delay_days=7, activation_date="2030-01-05"),
            None)

        assert _has_marker(cell)

    def test_an_unflagged_node_does_not(self):
        assert not _has_marker(_wakes_cell(_en(), None))

    def test_an_awake_node_does_not_even_if_flagged(self):
        cell = _wakes_cell(
            _en(dormant=0, activated=True, now_on_trigger=True), None)

        assert not _has_marker(cell)
