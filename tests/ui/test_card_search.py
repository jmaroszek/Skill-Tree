"""What a search found on a list card, shown only when the card doesn't show it."""
from dash import html

from skilltree.ui.canvas.view import node_options
from skilltree.ui.components.card_search import (
    alias_line, card_description, card_matches,
)
from support.graphs import make_node


def test_a_search_finds_a_card_by_name_alias_or_description():
    assert card_matches("sle", "Sleep")
    assert card_matches("shut", "Sleep", aliases=["Shuteye"])
    assert card_matches("rest", "Sleep", "Good rest matters")
    assert not card_matches("cook", "Sleep", "Good rest", ["Shuteye"])
    assert card_matches("  ", "Sleep") and card_matches(None, "Sleep")


def test_a_name_match_changes_nothing_on_the_card():
    preview = card_description("Sleep well", "sleep", "Sleep")
    assert preview.children == "Sleep well"
    assert alias_line("sleep", "Sleep", ["Sleep Well"]) is None


def test_no_search_shows_the_description_as_it_is():
    assert card_description("Sleep well", None, "Sleep").children == "Sleep well"
    assert card_description("  ", None, "Sleep") is None


def test_an_alias_match_gets_a_line():
    line = alias_line("shut", "Sleep", ["Nap", "Shuteye"])
    assert line.children[0] == "Also called "
    assert isinstance(line.children[1], html.Mark) and line.children[1].children == "Shut"
    assert line.children[2] == "eye"
    # The description isn't why, so it isn't marked.
    assert card_description("shut the door", "shut", "Sleep", ["Shuteye"]).children == "shut the door"


def test_a_description_match_marks_the_words():
    before, mark, after = card_description("Get good rest daily", "good", "Sleep").children
    assert (before, mark.children, after) == ("Get ", "good", " rest daily")
    assert isinstance(mark, html.Mark)


def test_a_match_below_the_two_lines_shows_an_excerpt():
    text = "Lots of words about something unrelated to the subject " * 3 + "circadian rhythm here"
    head, mark, tail = card_description(text, "circadian", "Sleep").children
    assert head.startswith("…") and mark.children == "circadian"
    # It starts at a word, with a little lead-in.
    assert not head[1].isspace() and 0 < len(head) < 60
    assert tail == " rhythm here"


def test_a_long_description_is_cut_to_what_two_lines_can_show():
    assert len(card_description("word " * 200, None, "Sleep").children) <= 240


def test_dropdowns_find_a_node_by_its_aliases():
    options = node_options([make_node("Sleep"), make_node("Rest")], exclude=None,
                           aliases={"Shuteye": "Sleep", "Nap": "Sleep"})
    assert options[0] == {"label": "Sleep", "value": "Sleep", "search": "Sleep Shuteye Nap"}
    assert options[1] == {"label": "Rest", "value": "Rest"}
