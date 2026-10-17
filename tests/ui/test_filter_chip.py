"""The "Filtered" chip's label list must agree with is_filters_active."""
import pytest

from skilltree.ui.filters import filter_chip_state, filter_summary, is_filters_active

CASES = [
    {},
    {"node_type": ["Learn"]},
    {"context": ["Health", "Mind"]},
    {"subcontext": ["Health|Sleep"]},
    {"value": [6, 10]},
    {"interest": [1, 10]},
    {"difficulty": [1, 7]},
    {"time_min": 2},
    {"time": 20},
    {"time_min": 10, "time": 2},
    {"search": {"text": "sleep", "descriptions": False}},
    {"search": {"text": "  ", "descriptions": True}},
    {"community": "All"},
    {"community": "3"},
    {"community_method": "orphans"},
]


@pytest.mark.parametrize("kwargs", CASES)
def test_summary_is_empty_exactly_when_no_filter_is_active(kwargs):
    assert bool(filter_summary(**kwargs)) == is_filters_active(**kwargs)


def test_labels_name_the_filters_context_first():
    labels = filter_summary(node_type=["Learn"], context=["Health"],
                            value=[6, 10], time=20, time_unit="hours")
    assert [short for short, _ in labels] == [
        "Health", "Learn", "Value 6–10", "Time ≤ 20 hours"]


def test_three_or_more_contexts_shorten_to_a_count_but_keep_names_in_full():
    (short, full), = filter_summary(context=["Health", "Mind", "Money"])
    assert short == "3 contexts"
    assert full == "Health, Mind, Money"
    (short, _), = filter_summary(context=["Health", "Mind"])
    assert short == "Health, Mind"


def test_chip_shows_three_labels_and_counts_the_rest():
    labels = [(c, c) for c in "ABCDE"]
    text, title, hidden = filter_chip_state(labels)
    assert text == "A · B · C +2"
    assert title == "A\nB\nC\nD\nE"
    assert hidden is False


def test_chip_is_hidden_without_labels():
    assert filter_chip_state([]) == ("", "", True)
