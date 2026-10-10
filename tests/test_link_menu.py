"""The link menu: right-click a link to change its type or direction, or
remove it (node_commands.change_link, link_menu_callbacks)."""
import dash
import pytest

import link_menu_callbacks
from graph_manager import GraphManager
from models import EDGE_HELPS, EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT, Node
from node_commands import change_link, link_change_reopens


def _node(name, **overrides):
    fields = dict(name=name, type="Learn", description="", value=5,
                  time_o=1.0, time_m=2.0, time_p=4.0, interest=5, difficulty=5,
                  status="Open", context="Mind")
    fields.update(overrides)
    return Node(**fields)


@pytest.fixture
def manager():
    manager = GraphManager()
    for name in ("A", "B", "C"):
        manager.add_node(_node(name))
    return manager


def _edges(manager):
    return {(e["source"], e["target"], e["type"]) for e in manager.get_edges()}


def _status(manager, name):
    return manager.get_node(name).status


# --- Changing a link --------------------------------------------------------

def test_a_hard_link_made_soft_unblocks_its_target(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    assert _status(manager, "B") == "Blocked"

    change_link(manager, "A", "B", EDGE_NEEDS_HARD, "soft")

    assert _edges(manager) == {("A", "B", EDGE_NEEDS_SOFT)}
    assert _status(manager, "B") == "Open"


def test_a_soft_link_made_hard_blocks_its_target(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_SOFT)

    change_link(manager, "A", "B", EDGE_NEEDS_SOFT, "hard")

    assert _edges(manager) == {("A", "B", EDGE_NEEDS_HARD)}
    assert _status(manager, "B") == "Blocked"


def test_reversing_a_link_moves_the_block(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)

    change_link(manager, "A", "B", EDGE_NEEDS_HARD, "reverse")

    assert _edges(manager) == {("B", "A", EDGE_NEEDS_HARD)}
    assert (_status(manager, "A"), _status(manager, "B")) == ("Blocked", "Open")


def test_a_reverse_that_would_make_a_circle_leaves_the_link_alone(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_SOFT)
    manager.add_edge("A", "C", EDGE_NEEDS_SOFT)
    manager.add_edge("C", "B", EDGE_NEEDS_SOFT)

    with pytest.raises(ValueError, match="circular dependency"):
        change_link(manager, "A", "B", EDGE_NEEDS_SOFT, "reverse")

    assert ("A", "B", EDGE_NEEDS_SOFT) in _edges(manager)


def test_removing_a_link_unblocks_its_target(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)

    message = change_link(manager, "A", "B", EDGE_NEEDS_HARD, "remove")

    assert _edges(manager) == set()
    assert _status(manager, "B") == "Open"
    assert message == "Removed the link from 'A' to 'B'"


def test_a_synergy_can_only_be_removed(manager):
    manager.add_edge("A", "B", EDGE_HELPS)

    for action in ("hard", "soft", "reverse"):
        with pytest.raises(ValueError, match="Synergy"):
            change_link(manager, "A", "B", EDGE_HELPS, action)
    assert len(_edges(manager)) == 1

    # Either order names a synergy.
    change_link(manager, "B", "A", EDGE_HELPS, "remove")
    assert _edges(manager) == set()


def test_a_synergy_beside_a_prerequisite_is_left_alone(manager):
    manager.add_edge("A", "B", EDGE_NEEDS_SOFT)
    manager.add_edge("A", "B", EDGE_HELPS)

    change_link(manager, "A", "B", EDGE_NEEDS_SOFT, "reverse")

    assert _edges(manager) == {("B", "A", EDGE_NEEDS_SOFT), ("A", "B", EDGE_HELPS)}


def test_a_link_that_is_gone_or_an_unknown_action_is_refused(manager):
    with pytest.raises(ValueError, match="no longer exists"):
        change_link(manager, "A", "B", EDGE_NEEDS_HARD, "soft")
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    with pytest.raises(ValueError, match="Unknown"):
        change_link(manager, "A", "B", EDGE_NEEDS_HARD, "explode")
    assert _edges(manager) == {("A", "B", EDGE_NEEDS_HARD)}


# --- The callback -----------------------------------------------------------

def _callbacks():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    link_menu_callbacks.register_link_menu_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        found[getattr(fn, "__name__", None)] = fn
    return found


def _apply_link_action():
    return _callbacks()["apply_link_action"]


def test_the_menu_request_changes_the_link_and_refreshes_the_canvases(manager):
    # Names are free text; the request is read as JSON, never split on "|".
    manager.add_node(_node("A|x"))
    manager.add_edge("A|x", "B", EDGE_NEEDS_HARD)

    refresh, message, is_open, _body, pending = _apply_link_action()(
        '["soft","A|x","B","Needs_Hard"]|1700000000000')

    assert refresh.startswith("link-")
    assert (message, is_open, pending) == (dash.no_update, dash.no_update, None)
    assert ("A|x", "B", EDGE_NEEDS_SOFT) in _edges(manager)


def test_a_refused_request_reports_an_error_and_redraws_nothing(manager):
    manager.add_edge("A", "B", EDGE_HELPS)

    refresh, message, is_open, _body, _pending = _apply_link_action()(
        '["reverse","A","B","Helps"]|1')

    assert refresh is dash.no_update
    assert is_open is dash.no_update
    assert message.startswith("Error: ")


def test_a_malformed_request_does_nothing(manager):
    assert _apply_link_action()("") == (dash.no_update,) * 5
    assert _apply_link_action()('["remove","A"]|1') == (dash.no_update,) * 5


# --- Done nodes ---------------------------------------------------------------

@pytest.fixture
def done_chain(manager):
    """A is Done and leads to B, also Done, which leads to C. P is open."""
    manager.add_node(_node("P"))
    for name in ("A", "B"):
        node = manager.get_node(name)
        node.status = "Done"
        manager.update_node(node)
    manager.add_edge("A", "B", EDGE_NEEDS_HARD)
    manager.add_edge("B", "C", EDGE_NEEDS_HARD)
    manager.add_edge("P", "A", EDGE_NEEDS_SOFT)
    assert [_status(manager, n) for n in "ABC"] == ["Done", "Done", "Open"]
    return manager


def test_a_dry_run_names_the_done_nodes_a_change_reopens_and_changes_nothing(done_chain):
    edges = _edges(done_chain)

    assert link_change_reopens(done_chain, "P", "A", EDGE_NEEDS_SOFT, "hard") == ["A", "B"]

    assert _edges(done_chain) == edges
    assert [_status(done_chain, n) for n in "ABC"] == ["Done", "Done", "Open"]


def test_changes_that_reopen_nothing_say_so(done_chain):
    # Both ends Done: reversed, each still has only Done prerequisites.
    assert link_change_reopens(done_chain, "A", "B", EDGE_NEEDS_HARD, "reverse") == []
    # Soft and Remove never add a prerequisite.
    assert link_change_reopens(done_chain, "A", "B", EDGE_NEEDS_HARD, "soft") == []
    assert link_change_reopens(done_chain, "B", "C", EDGE_NEEDS_HARD, "remove") == []


def test_a_dry_run_reports_a_refusal(done_chain):
    with pytest.raises(ValueError, match="no longer exists"):
        link_change_reopens(done_chain, "C", "A", EDGE_NEEDS_HARD, "remove")


def test_a_change_that_reopens_done_nodes_waits_for_confirmation(done_chain, monkeypatch):
    request = '["hard","P","A","Needs_Soft"]|1'

    refresh, message, is_open, body, pending = _apply_link_action()(request)

    assert (refresh, message, is_open) == (dash.no_update, dash.no_update, True)
    assert pending == ["hard", "P", "A", EDGE_NEEDS_SOFT]
    assert "reopens 2 Done nodes" in str(body)
    assert ("P", "A", EDGE_NEEDS_SOFT) in _edges(done_chain)

    monkeypatch.setattr(link_menu_callbacks, "get_trigger_id",
                        lambda: "btn-link-reopen-confirm")
    answer = _callbacks()["answer_link_reopen"]
    refresh, message, is_open, cleared = answer(1, None, pending)
    assert refresh.startswith("link-") and is_open is False and cleared is None
    assert ("P", "A", EDGE_NEEDS_HARD) in _edges(done_chain)
    assert [_status(done_chain, n) for n in "AB"] == ["Blocked", "Blocked"]


def test_cancelling_the_confirmation_leaves_the_link(done_chain, monkeypatch):
    monkeypatch.setattr(link_menu_callbacks, "get_trigger_id",
                        lambda: "btn-link-reopen-cancel")

    answer = _callbacks()["answer_link_reopen"]
    result = answer(None, 1, ["hard", "P", "A", EDGE_NEEDS_SOFT])

    assert result == (dash.no_update, dash.no_update, False, None)
    assert ("P", "A", EDGE_NEEDS_SOFT) in _edges(done_chain)
    assert _status(done_chain, "A") == "Done"
