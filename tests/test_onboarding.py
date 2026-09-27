"""A new user's first minutes: the welcome, the Getting Started steps, and the
empty states (P5.1)."""
import dash
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

import onboarding
import onboarding_callbacks
from config import DEFAULT_CONTEXTS, ConfigManager
from graph_manager import GraphManager
from layout import build_app_layout
from models import EDGE_NEEDS_HARD, STATUS_DONE, Node


def _node(name, node_type="Learn", **overrides):
    fields = dict(name=name, type=node_type, description="", value=5, time_o=1.0,
                  time_m=2.0, time_p=4.0, interest=5, difficulty=5, status="Open",
                  context="Mind")
    fields.update(overrides)
    return Node(**fields)


def _callbacks(register):
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    register(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


def _find(component, component_id):
    if getattr(component, "id", None) == component_id:
        return component
    children = getattr(component, "children", None)
    for child in children if isinstance(children, (list, tuple)) else [children]:
        if hasattr(child, "children") or hasattr(child, "id"):
            found = _find(child, component_id)
            if found is not None:
                return found
    return None


def _clicked(fn, button, *args):
    token = context_value.set(AttributeDict(triggered_inputs=[
        {"prop_id": f"{button}.n_clicks", "value": 1}]))
    try:
        return fn(*args)
    finally:
        context_value.reset(token)


# --- The welcome --------------------------------------------------------------

def test_a_new_user_is_welcomed():
    assert onboarding.should_welcome() is True
    modal = _find(build_app_layout([], env="sandbox"), "welcome-modal")
    assert modal is not None and modal.is_open is True


def test_someone_with_a_graph_is_not_welcomed_even_the_first_time():
    """An existing user upgrading has never seen the welcome, and needn't."""
    GraphManager().add_node(_node("Sleep"))
    assert onboarding.should_welcome() is False


def test_the_welcome_shows_once():
    ConfigManager.set_welcome_done(True)
    assert onboarding.should_welcome() is False
    assert _find(build_app_layout([], env="sandbox"), "welcome-modal").is_open is False


@pytest.fixture
def welcome():
    return _callbacks(onboarding_callbacks.register_onboarding_callbacks)["welcome_choice"]


def test_keeping_the_suggested_contexts(welcome):
    is_open, reload, settings_open, tab = _clicked(welcome, "btn-welcome-suggested", 1, None, None)
    assert is_open is False and reload is dash.no_update
    assert settings_open is dash.no_update
    assert ConfigManager.get_contexts() == DEFAULT_CONTEXTS
    assert ConfigManager.get_welcome_done() is True


def test_starting_plain_leaves_one_context_and_reloads(welcome):
    """Every node needs a context, so none at all would leave a new user
    unable to save anything."""
    is_open, reload, _open, _tab = _clicked(welcome, "btn-welcome-empty", None, 1, None)
    assert is_open is False and reload
    assert ConfigManager.get_contexts() == ["General"]
    assert ConfigManager.get_subcontexts() == {"General": []}
    assert ConfigManager.get_welcome_done() is True


def test_importing_opens_settings_on_the_data_tab(welcome):
    is_open, reload, settings_open, tab = _clicked(welcome, "btn-welcome-import", None, None, 1)
    assert is_open is False and reload is dash.no_update
    assert settings_open is True and tab == "tab-data"
    assert ConfigManager.get_welcome_done() is True


# --- Getting Started ------------------------------------------------------------

def _done(steps):
    return {step.key: step.done for step in steps}


def test_the_steps_tick_themselves_off_as_the_graph_grows():
    manager = GraphManager()
    assert not any(_done(onboarding.getting_started(manager)).values())

    manager.add_node(_node("Sleep", "Goal"))
    assert _done(onboarding.getting_started(manager))["goal"] is True

    manager.add_node(_node("Sleep hygiene"))
    manager.add_edge("Sleep hygiene", "Sleep", EDGE_NEEDS_HARD)
    assert _done(onboarding.getting_started(manager))["connect"] is True

    manager.add_node(_node("Blackout curtains", "Action", now=1))
    assert _done(onboarding.getting_started(manager))["now"] is True

    curtains = manager.get_node("Blackout curtains")
    curtains.status = STATUS_DONE
    manager.update_node(curtains)
    assert all(_done(onboarding.getting_started(manager)).values())


@pytest.fixture
def card():
    return _callbacks(onboarding_callbacks.register_onboarding_callbacks)


def test_the_card_shows_until_every_step_is_done(card):
    shown = card["render_getting_started"](1)
    text = str(shown)
    assert "Getting started" in text and "Add a goal" in text

    # Each change bumps the graph version, which re-renders the card.
    manager = GraphManager()
    manager.add_node(_node("Sleep", "Goal"))
    manager.add_node(_node("Rest", now=1))
    manager.add_edge("Rest", "Sleep", EDGE_NEEDS_HARD)
    assert card["render_getting_started"](2) is not None
    rest = manager.get_node("Rest")
    rest.status = STATUS_DONE   # which clears its Now flag; the step stays done
    manager.update_node(rest)
    assert card["render_getting_started"](3) is None


def test_the_card_can_be_dismissed(card):
    assert card["dismiss_getting_started"]([None]) is dash.no_update   # rendered, not clicked
    card["dismiss_getting_started"]([1])
    assert ConfigManager.get_getting_started_dismissed() is True
    assert card["render_getting_started"](1) is None


# --- Empty states ------------------------------------------------------------

def test_an_empty_graph_says_how_to_begin():
    from callback_helpers import format_suggestions_table
    empty = str(format_suggestions_table([], GraphManager()))
    assert "Add a goal" in empty and "No suggestions found" not in empty

    manager = GraphManager()
    manager.add_node(_node("Sleep", "Goal"))
    only_goals = str(format_suggestions_table([], manager))
    assert "Nothing to suggest yet" in only_goals

    manager.add_node(_node("Rest"))
    assert "No suggestions found" in str(format_suggestions_table([], manager))


def test_a_disabled_save_says_why():
    from callbacks import register_callbacks
    validate = _callbacks(register_callbacks)["validate_time_estimates"]
    message, _style, disabled, _disabled_close, title, _title_close = validate(
        None, None, None, [], [])
    assert disabled is True and "Expected" in title
    _message, _style, disabled, _dc, title, _tc = validate(None, 2, None, [], [])
    assert disabled is False and title == ""
