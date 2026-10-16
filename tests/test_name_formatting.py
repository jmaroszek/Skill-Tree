"""Name formatting modes and duplicate-name normalization."""

import json

from skilltree.domain.names import normalize_name_for_comparison
from skilltree.store.settings import ConfigManager


def test_default_name_formatting_keeps_names_as_entered():
    formatting = ConfigManager.get_name_formatting()

    assert formatting["mode"] == "none"
    assert formatting["enabled"] is False
    assert ConfigManager.apply_name_formatting("learn iOS basics") == "learn iOS basics"


def test_legacy_enabled_switch_migrates_when_read():
    ConfigManager._set_db_value("TITLECASE_LINTER", json.dumps({
        "enabled": False,
        "exclusions": ["the"],
    }))

    formatting = ConfigManager.get_name_formatting()

    assert formatting == {
        "mode": "none",
        "enabled": False,
        "exclusions": ["the"],
    }


def test_keep_as_entered_does_not_change_capitalization():
    ConfigManager.set_name_formatting({"mode": "none", "exclusions": ["the"]})

    assert ConfigManager.apply_name_formatting("learn the Python API") == "learn the Python API"


def test_sentence_case_preserves_intentional_internal_capitals():
    ConfigManager.set_name_formatting({"mode": "sentence", "exclusions": []})

    assert ConfigManager.apply_name_formatting("learn the Python API") == "Learn the Python API"
    assert ConfigManager.apply_name_formatting("'learn the API") == "'Learn the API"


def test_title_case_exceptions_do_not_change_duplicate_detection():
    ConfigManager.set_name_formatting({
        "mode": "title",
        "exclusions": ["quantum"],
    })

    assert normalize_name_for_comparison("Quantum Mechanics") == "quantum mechanics"
    assert normalize_name_for_comparison("The Skill Tree") == "skill tree"


def test_legacy_api_remains_compatible():
    ConfigManager.set_titlecase_linter({"enabled": True, "exclusions": ["of"]})

    assert ConfigManager.get_titlecase_linter()["mode"] == "title"
    assert ConfigManager.apply_titlecase_linter("history of science") == "History of Science"
