"""A node can't sleep in the event it triggers, and a delay has a limit.

A node put to sleep in an event it triggered could never be finished, so the
event never fired. A delay past about 2.9 million days made every event sweep
raise OverflowError, and every click runs the sweeps.
"""
import logging
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from skilltree.store import database
from skilltree.store.events import EventManager, MAX_DELAY_DAYS
from skilltree.domain.models import Event, Node


def _node(name):
    return Node(name=name, type="Learn", description="", value=5, time_o=1.0,
                time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                context="Mind")


@pytest.fixture
def events(services):
    manager, events = services.graph, services.events
    for name in ("Draft", "Edit", "Publish"):
        manager.add_node(_node(name))
    events.add_event(Event(name="Ready", trigger_nodes=["Draft"]))
    events.add_event(Event(name="Later"))
    return events


def test_a_trigger_node_cant_sleep_in_its_event(events):
    with pytest.raises(ValueError, match="'Draft' triggers 'Ready'"):
        events.add_node_to_event("Ready", "Draft")
    assert events.get_node_membership("Draft") is None


def test_it_cant_be_moved_into_it_either(events):
    events.add_node_to_event("Later", "Draft")

    with pytest.raises(ValueError, match="'Draft' triggers 'Ready'"):
        events.move_node_to_event("Later", "Draft", "Ready")
    assert events.get_node_membership("Draft")["event"] == "Later"


def test_a_sleeping_node_cant_become_its_events_trigger(events):
    events.add_node_to_event("Later", "Publish")

    with pytest.raises(ValueError, match="'Publish' triggers 'Later'"):
        events.update_event("Later", Event(name="Later", trigger_nodes=["Publish"]))
    assert events.get_event("Later").trigger_nodes == []


def test_another_event_can_hold_it(events):
    events.add_node_to_event("Later", "Draft")
    assert events.get_node_membership("Draft")["event"] == "Later"


@pytest.mark.parametrize("delay, message", [
    (MAX_DELAY_DAYS + 1, "at most 100 years"),
    (10 ** 9, "at most 100 years"),
    (-1, "can't be negative"),
])
def test_a_delay_out_of_range_is_refused(events, delay, message):
    with pytest.raises(ValueError, match=message):
        events.add_node_to_event("Later", "Publish", delay_days=delay)

    events.add_node_to_event("Later", "Publish", delay_days=MAX_DELAY_DAYS)
    with pytest.raises(ValueError, match=message):
        events.set_node_delay("Later", "Publish", delay)
    with pytest.raises(ValueError, match=message):
        events.move_node_to_event("Later", "Publish", "Ready", delay_days=delay)


def test_a_huge_delay_saved_before_the_limit_still_fires(events):
    events.add_node_to_event("Later", "Publish")
    with database.transaction() as conn:
        conn.execute("UPDATE EventNodes SET delay_days=? WHERE node_name='Publish'",
                     (10 ** 9,))

    result = events.trigger_event("Later")

    assert result["scheduled"] == ["Publish"]
    wake = events.get_node_membership("Publish")["activation_date"]
    assert wake == (date.today() + timedelta(days=MAX_DELAY_DAYS)).isoformat()


def test_a_failing_sweep_is_logged_and_the_other_still_runs(events, caplog):
    with patch.object(EventManager, "check_pending_activations",
                      side_effect=OverflowError("date value out of range")), \
            patch.object(EventManager, "check_scheduled_triggers",
                         return_value=["Spring"]) as scheduled, \
            caplog.at_level(logging.ERROR):
        assert events.run_sweeps() is True

    scheduled.assert_called_once()
    assert "The event sweep check_pending_activations failed" in caplog.text
