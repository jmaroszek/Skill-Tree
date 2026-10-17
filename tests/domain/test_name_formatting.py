"""Name formatting modes and duplicate-name normalization."""

import json

from skilltree.domain.names import format_name, normalize_name_for_comparison
from skilltree.store import settings


def _formatted(name):
    """`name` as the saved name formatting writes it."""
    return format_name(name, settings.NAME_FORMATTING.get())


def test_default_name_formatting_keeps_names_as_entered():
    formatting = settings.NAME_FORMATTING.get()

    assert formatting["mode"] == "none"
    assert formatting["enabled"] is False
    assert _formatted("learn iOS basics") == "learn iOS basics"


def test_legacy_enabled_switch_migrates_when_read():
    settings.write_stored("TITLECASE_LINTER", json.dumps({
        "enabled": False,
        "exclusions": ["the"],
    }))

    formatting = settings.NAME_FORMATTING.get()

    assert formatting == {
        "mode": "none",
        "enabled": False,
        "exclusions": ["the"],
    }


def test_keep_as_entered_does_not_change_capitalization():
    settings.NAME_FORMATTING.set({"mode": "none", "exclusions": ["the"]})

    assert _formatted("learn the Python API") == "learn the Python API"


def test_sentence_case_preserves_intentional_internal_capitals():
    settings.NAME_FORMATTING.set({"mode": "sentence", "exclusions": []})

    assert _formatted("learn the Python API") == "Learn the Python API"
    assert _formatted("'learn the API") == "'Learn the API"


def test_title_case_exceptions_do_not_change_duplicate_detection():
    settings.NAME_FORMATTING.set({
        "mode": "title",
        "exclusions": ["quantum"],
    })

    assert normalize_name_for_comparison("Quantum Mechanics") == "quantum mechanics"
    assert normalize_name_for_comparison("The Skill Tree") == "skill tree"


def test_the_legacy_enabled_switch_still_saves_as_title_case():
    settings.NAME_FORMATTING.set({"enabled": True, "exclusions": ["of"]})

    assert settings.NAME_FORMATTING.get()["mode"] == "title"
    assert _formatted("history of science") == "History of Science"
