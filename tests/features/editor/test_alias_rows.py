"""The editor's alias rows."""
import dash
from skilltree.features.editor.layout import alias_rows_label, update_alias_rows


# ============================================================================
# update_alias_rows
# ============================================================================

class TestUpdateAliasRows:
    def test_label_is_singular_for_zero_or_one_stored_row(self):
        assert alias_rows_label([]) == "Alias"
        assert alias_rows_label([""]) == "Alias"

    def test_label_is_plural_for_two_or_more_rows(self):
        assert alias_rows_label(["One", "Two"]) == "Aliases"
        assert alias_rows_label(["One", "Two", "Three"]) == "Aliases"

    def test_first_add_reveals_existing_row_without_adding_another(self):
        aliases, is_open = update_alias_rows(
            "add", ["Existing"], ["Stored"], False, "add", "remove",
        )
        assert aliases == ["Existing"]
        assert is_open is True

    def test_add_while_open_appends_a_row(self):
        aliases, is_open = update_alias_rows(
            "add", ["Existing"], ["Stored"], True, "add", "remove",
        )
        assert aliases == ["Existing", ""]
        assert is_open is True

    def test_add_after_all_rows_were_removed_restores_blank_row(self):
        aliases, is_open = update_alias_rows(
            "add", [], [], False, "add", "remove",
        )
        assert aliases == [""]
        assert is_open is True

    def test_removing_final_row_closes_aliases(self):
        aliases, is_open = update_alias_rows(
            {"type": "remove", "index": 0}, ["Only"], ["Only"], True,
            "add", "remove",
        )
        assert aliases == []
        assert is_open is False

    def test_removing_one_of_multiple_rows_keeps_collapse_unchanged(self):
        aliases, is_open = update_alias_rows(
            {"type": "remove", "index": 0}, ["First", "Second"],
            ["First", "Second"], True, "add", "remove",
        )
        assert aliases == ["Second"]
        assert is_open is dash.no_update
