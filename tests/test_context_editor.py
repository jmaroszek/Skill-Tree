"""The Contexts editor: rows with identity instead of a block of text.

The free-text field could only say what the taxonomy should look like, never
what the user did to it, so the save path diffed names and guessed. A rename
and a delete-plus-add were the same edit, and the guess only held when exactly
one context changed. These tests pin the replacement: each row remembers the
name it was loaded under, renames and moves go straight onto the nodes, and
only a genuine removal reaches the migration dialog.
"""

import json

import dash
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

import context_rules as cr
import settings_callbacks
from callback_helpers import build_context_editor_rows
from config import ConfigManager
from graph_manager import GraphManager
from models import Node


CONTEXTS = ["Health", "People", "Wisdom"]
SUBCONTEXTS = {"Health": ["Stress", "Rhythms"], "People": ["Dating"],
               "Wisdom": ["Ethics", "Logic"]}


def _rows():
    return cr.taxonomy_to_rows(CONTEXTS, SUBCONTEXTS, {"People": 1.4})


def _row(rows, name):
    return next(r for r in rows if r["name"] == name)


def _plan(rows):
    return cr.plan_taxonomy_change(rows, CONTEXTS, SUBCONTEXTS)


def _node(name, context, subcontext=None, dormant=0):
    return Node(name=name, type="Learn", description="", value=5,
                time_o=1, time_m=2, time_p=3, interest=5, difficulty=5,
                status="Open", context=context, subcontext=subcontext,
                dormant=dormant)


# --- Row model ---------------------------------------------------------------

class TestRowsFromTaxonomy:
    def test_every_row_and_chip_remembers_where_it_came_from(self):
        rows = _rows()
        assert [r["orig"] for r in rows] == CONTEXTS
        wisdom = _row(rows, "Wisdom")
        assert [(s["orig_ctx"], s["orig"]) for s in wisdom["subs"]] == [
            ("Wisdom", "Ethics"), ("Wisdom", "Logic")]
        assert _row(rows, "People")["weight"] == 1.4
        assert _row(rows, "Health")["weight"] == cr.DEFAULT_CONTEXT_WEIGHT

    def test_subcontexts_stored_under_an_unlisted_context_still_get_a_row(self):
        """An inconsistent config is shown, not silently dropped on save."""
        rows = cr.taxonomy_to_rows(["A"], {"A": ["x"], "Ghost": ["y"]})
        assert [r["name"] for r in rows] == ["A", "Ghost"]

    def test_ids_are_unique(self):
        rows = _rows()
        rows.append({"rid": cr.next_row_id(rows), "orig": None, "name": "New",
                     "weight": 1.0, "subs": []})
        assert len({r["rid"] for r in rows}) == len(rows)
        sid = cr.next_sub_id(rows)
        assert sid not in {s["sid"] for r in rows for s in r["subs"]}


# --- Planning a save -----------------------------------------------------------

class TestPlanTaxonomyChange:
    def test_no_edit_changes_nothing(self):
        plan = _plan(_rows())
        assert plan["contexts"] == CONTEXTS
        assert plan["ctx_renames"] == {}
        assert plan["pair_moves"] == []
        assert plan["deleted_contexts"] == []
        assert plan["deleted_pairs"] == []

    def test_renaming_a_row_is_a_rename_not_a_removal(self):
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "Philosophy"
        plan = _plan(rows)
        assert plan["ctx_renames"] == {"Wisdom": "Philosophy"}
        assert plan["deleted_contexts"] == []
        assert plan["deleted_pairs"] == []
        assert plan["contexts"] == ["Health", "People", "Philosophy"]

    def test_several_renames_alongside_an_addition_all_register(self):
        """The case the old name-diff heuristic gave up on.

        It only recognised a rename when exactly one context was removed and
        exactly one added, so this edit sent every node in both renamed
        contexts to the migration dialog.
        """
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "Philosophy"
        _row(rows, "People")["name"] = "Relationships"
        rows.append({"rid": cr.next_row_id(rows), "orig": None,
                     "name": "Money", "weight": 1.0, "subs": []})
        plan = _plan(rows)
        assert plan["ctx_renames"] == {"Wisdom": "Philosophy",
                                       "People": "Relationships"}
        assert plan["deleted_contexts"] == []
        assert "Money" in plan["contexts"]

    def test_renamed_contexts_carry_their_subcontexts_as_pair_moves(self):
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "Philosophy"
        plan = _plan(rows)
        assert sorted(plan["pair_moves"]) == [
            ["Wisdom", "Ethics", "Philosophy", "Ethics"],
            ["Wisdom", "Logic", "Philosophy", "Logic"],
        ]

    def test_weight_follows_its_row_through_a_rename(self):
        rows = _rows()
        _row(rows, "People")["name"] = "Relationships"
        plan = _plan(rows)
        assert plan["weights"]["Relationships"] == 1.4
        assert "People" not in plan["weights"]

    def test_moving_a_chip_to_another_context_is_a_move(self):
        rows = _rows()
        ethics = _row(rows, "Wisdom")["subs"].pop(0)
        _row(rows, "People")["subs"].append(ethics)
        plan = _plan(rows)
        assert plan["pair_moves"] == [["Wisdom", "Ethics", "People", "Ethics"]]
        assert plan["deleted_pairs"] == []
        assert plan["subcontexts"]["People"] == ["Dating", "Ethics"]

    def test_renaming_a_chip_is_a_move_within_its_context(self):
        rows = _rows()
        _row(rows, "Health")["subs"][1]["name"] = "Sleep"
        plan = _plan(rows)
        assert plan["pair_moves"] == [["Health", "Rhythms", "Health", "Sleep"]]
        assert plan["deleted_pairs"] == []

    def test_removing_a_chip_drops_its_pair(self):
        rows = _rows()
        _row(rows, "People")["subs"] = []
        plan = _plan(rows)
        assert plan["deleted_pairs"] == [["People", "Dating"]]
        assert plan["deleted_contexts"] == []

    def test_removing_a_row_drops_the_context_but_not_its_pairs(self):
        """The removed context's nodes are rehomed whole, so listing its
        pairs as well would put them in the dialog twice."""
        rows = [r for r in _rows() if r["name"] != "Wisdom"]
        plan = _plan(rows)
        assert plan["deleted_contexts"] == ["Wisdom"]
        assert plan["deleted_pairs"] == []

    def test_a_row_marked_removed_counts_as_removed(self):
        rows = _rows()
        _row(rows, "Wisdom")["deleted"] = True
        plan = _plan(rows)
        assert plan["deleted_contexts"] == ["Wisdom"]
        assert "Wisdom" not in plan["contexts"]

    def test_row_order_is_the_defined_order(self):
        rows = _rows()
        rows.reverse()
        assert _plan(rows)["contexts"] == ["Wisdom", "People", "Health"]

    def test_blank_chips_are_an_unfinished_add_not_a_change(self):
        rows = _rows()
        _row(rows, "Health")["subs"].append(
            {"sid": "m9", "orig": None, "orig_ctx": None, "name": "  "})
        plan = _plan(rows)
        assert plan["subcontexts"]["Health"] == ["Stress", "Rhythms"]
        assert cr.validate_rows(cr.normalize_rows(rows)) == {}


class TestDescribePlan:
    def test_says_nothing_when_nothing_changed(self):
        assert cr.describe_plan(_plan(_rows())) == ""

    def test_names_the_nodes_a_removal_would_strand(self):
        rows = [r for r in _rows() if r["name"] != "Wisdom"]
        text = cr.describe_plan(_plan(rows), {"Wisdom": 3})
        assert "1 removal affecting 3 nodes" in text
        assert "migration dialog" in text

    def test_a_rename_alone_needs_no_dialog(self):
        rows = _rows()
        _row(rows, "Health")["name"] = "Body"
        text = cr.describe_plan(_plan(rows), {"Health": 12})
        assert text == "1 rename"

    def test_subcontexts_that_follow_a_renamed_context_are_not_moves(self):
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "Philosophy"
        ethics = _row(rows, "Philosophy")["subs"].pop(0)
        _row(rows, "People")["subs"].append(ethics)
        assert cr.describe_plan(_plan(rows)) == "1 rename · 1 move"


# --- Validation ----------------------------------------------------------------

class TestValidateRows:
    def test_a_clean_taxonomy_has_no_errors(self):
        assert cr.validate_rows(_rows()) == {}

    def test_names_that_differ_only_in_case_collide(self):
        """`STEM` and `Stem` would be two contexts that read as one."""
        rows = [{"rid": "a", "name": "STEM", "subs": []},
                {"rid": "b", "name": "Stem", "subs": []}]
        assert set(cr.validate_rows(rows)) == {"row:b"}

    def test_clearing_a_saved_context_name_is_flagged(self):
        rows = cr.normalize_rows([{"rid": "a", "orig": "Health", "name": "  ", "subs": []}])
        assert set(cr.validate_rows(rows)) == {"row:a"}

    def test_a_row_added_but_never_named_is_an_unfinished_add(self):
        """No error the moment "Add context" is clicked; dropped at save."""
        rows = _rows() + [{"rid": "n9", "orig": None, "name": "", "weight": 1.0,
                           "subs": []}]
        assert cr.validate_rows(cr.normalize_rows(rows)) == {}
        assert _plan(rows)["contexts"] == CONTEXTS

    @pytest.mark.parametrize("name", ["Health: Body", "Health, Body"])
    def test_context_names_cannot_hold_the_text_grammar(self, name):
        rows = [{"rid": "a", "name": name, "subs": []}]
        assert set(cr.validate_rows(rows)) == {"row:a"}

    def test_a_colon_is_fine_in_a_subcontext(self):
        rows = [{"rid": "a", "name": "A",
                 "subs": [{"sid": "s", "name": "Note: one"}]}]
        assert cr.validate_rows(rows) == {}

    def test_duplicate_subcontexts_within_a_context_collide(self):
        rows = [{"rid": "a", "name": "A", "subs": [
            {"sid": "s1", "name": "Sleep"}, {"sid": "s2", "name": "sleep"}]}]
        assert set(cr.validate_rows(rows)) == {"sub:s2"}

    def test_the_same_subcontext_under_two_contexts_is_allowed(self):
        rows = [{"rid": "a", "name": "A", "subs": [{"sid": "s1", "name": "Sleep"}]},
                {"rid": "b", "name": "B", "subs": [{"sid": "s2", "name": "Sleep"}]}]
        assert cr.validate_rows(rows) == {}


# --- The text view ---------------------------------------------------------------

class TestTextView:
    def test_rows_render_to_the_familiar_grammar(self):
        assert cr.rows_to_text(_rows()) == (
            "Health: Stress, Rhythms\nPeople: Dating\nWisdom: Ethics, Logic")

    def test_parse_and_format_round_trip(self):
        text = cr.format_context_text(CONTEXTS, SUBCONTEXTS)
        assert cr.parse_context_text(text) == (CONTEXTS, SUBCONTEXTS)

    def test_an_in_place_rename_keeps_the_rows_identity(self):
        """Position recovers what name-matching cannot."""
        text = "Health: Stress, Rhythms\nPeople: Dating\nPhilosophy: Ethics, Logic"
        rows = cr.reconcile_rows_with_text(text, _rows())
        assert _row(rows, "Philosophy")["orig"] == "Wisdom"
        assert _plan(rows)["ctx_renames"] == {"Wisdom": "Philosophy"}
        assert _plan(rows)["deleted_contexts"] == []

    def test_reordering_lines_keeps_every_identity(self):
        text = "Wisdom: Ethics, Logic\nHealth: Stress, Rhythms\nPeople: Dating"
        rows = cr.reconcile_rows_with_text(text, _rows())
        assert [(r["orig"], r["name"]) for r in rows] == [
            ("Wisdom", "Wisdom"), ("Health", "Health"), ("People", "People")]
        assert _plan(rows)["ctx_renames"] == {}

    def test_a_new_line_is_a_new_context_and_a_missing_one_is_removed(self):
        text = "Health: Stress, Rhythms\nPeople: Dating\nWisdom: Ethics, Logic\nMoney"
        rows = cr.reconcile_rows_with_text(text, _rows())
        assert _row(rows, "Money")["orig"] is None

        rows = cr.reconcile_rows_with_text("Health: Stress, Rhythms\nPeople: Dating",
                                           _rows())
        assert _plan(rows)["deleted_contexts"] == ["Wisdom"]

    def test_a_renamed_subcontext_keeps_its_identity_by_position(self):
        text = "Health: Stress, Sleep\nPeople: Dating\nWisdom: Ethics, Logic"
        rows = cr.reconcile_rows_with_text(text, _rows())
        assert _plan(rows)["pair_moves"] == [["Health", "Rhythms", "Health", "Sleep"]]

    def test_weights_survive_a_text_edit(self):
        text = "Health: Stress, Rhythms\nRelationships: Dating\nWisdom: Ethics, Logic"
        rows = cr.reconcile_rows_with_text(text, _rows())
        assert _row(rows, "Relationships")["weight"] == 1.4


# --- Dragging ----------------------------------------------------------------------

class TestApplyDragOrder:
    def test_rows_take_the_reported_order(self):
        rows = cr.apply_drag_order(_rows(), {"rows": ["c2", "c0", "c1"]})
        assert [r["name"] for r in rows] == ["Wisdom", "Health", "People"]

    def test_a_chip_dragged_to_another_row_moves_there(self):
        order = {"rows": ["c0", "c1", "c2"],
                 "subs": {"c0": ["c0s0", "c0s1"], "c1": ["c1s0", "c2s0"],
                          "c2": ["c2s1"]}}
        rows = cr.apply_drag_order(_rows(), order)
        assert [s["name"] for s in _row(rows, "People")["subs"]] == ["Dating", "Ethics"]
        assert [s["name"] for s in _row(rows, "Wisdom")["subs"]] == ["Logic"]
        assert _plan(rows)["pair_moves"] == [["Wisdom", "Ethics", "People", "Ethics"]]

    def test_a_stale_payload_cannot_drop_anything(self):
        rows = cr.apply_drag_order(_rows(), {"rows": ["gone"], "subs": {"c0": ["nope"]}})
        assert [r["name"] for r in rows] == CONTEXTS
        assert sum(len(r["subs"]) for r in rows) == 5


# --- Carrying changes onto nodes ------------------------------------------------

class TestApplyTaxonomyMigration:
    def test_rename_and_move_land_together(self):
        """Pairs move before contexts rename, so both reach the right nodes."""
        mgr = GraphManager()
        mgr.add_node(_node("Kant", "Wisdom", "Ethics"))
        mgr.add_node(_node("Aristotle", "Wisdom", "Logic"))
        mgr.add_node(_node("Stoa", "Wisdom"))
        mgr.add_node(_node("Resting", "Wisdom", "Ethics", dormant=1))

        rows = _rows()
        wisdom = _row(rows, "Wisdom")
        wisdom["name"] = "Philosophy"
        _row(rows, "People")["subs"].append(wisdom["subs"].pop(0))
        plan = _plan(rows)
        mgr.apply_taxonomy_migration(plan["ctx_renames"], plan["pair_moves"])

        nodes = {n.name: n for n in mgr.get_all_nodes(include_dormant=True)}
        assert (nodes["Kant"].context, nodes["Kant"].subcontext) == ("People", "Ethics")
        assert (nodes["Aristotle"].context, nodes["Aristotle"].subcontext) == (
            "Philosophy", "Logic")
        assert (nodes["Stoa"].context, nodes["Stoa"].subcontext) == ("Philosophy", None)
        assert (nodes["Resting"].context, nodes["Resting"].subcontext) == (
            "People", "Ethics")

    def test_counts_include_dormant_nodes(self):
        mgr = GraphManager()
        mgr.add_node(_node("A", "Wisdom", "Ethics"))
        mgr.add_node(_node("B", "Wisdom", dormant=1))
        ctx_counts, pair_counts = mgr.count_nodes_by_context()
        assert ctx_counts["Wisdom"] == 2
        assert pair_counts[("Wisdom", "Ethics")] == 1

    def test_find_nodes_by_pairs_groups_by_label(self):
        mgr = GraphManager()
        mgr.add_node(_node("A", "People", "Dating"))
        found = mgr.find_nodes_by_pairs([["People", "Dating"], ["People", "None"]])
        assert list(found) == ["People > Dating"]
        assert [n.name for n in found["People > Dating"]] == ["A"]


# --- The callbacks -------------------------------------------------------------------

def _callbacks():
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    settings_callbacks.register_settings_callbacks(app)
    found = {}
    for spec in app.callback_map.values():
        fn = spec.get("callback")
        while fn is not None and hasattr(fn, "__wrapped__"):
            fn = fn.__wrapped__
        if fn is not None:
            found[fn.__name__] = fn
    return found


def _with_trigger(fn, prop_id, value, *args):
    token = context_value.set(AttributeDict(
        triggered_inputs=[{"prop_id": prop_id, "value": value}]))
    try:
        return fn(*args)
    finally:
        context_value.reset(token)


def _pm(kind, index, prop="n_clicks"):
    """The prop_id Dash reports for a pattern-matched component."""
    return json.dumps({"index": index, "type": kind},
                      separators=(",", ":"), sort_keys=True) + f".{prop}"


def _live(rows):
    """What the rendered inputs would report back for these rows."""
    live = [r for r in rows if not r.get("deleted")]
    subs = [s for r in live for s in r["subs"]]
    return (
        [r["name"] for r in live], [{"index": r["rid"]} for r in live],
        [r["weight"] for r in live], [{"index": r["rid"]} for r in live],
        [s["name"] for s in subs], [{"index": s["sid"]} for s in subs],
    )


@pytest.fixture
def seeded():
    ConfigManager.set_contexts(CONTEXTS)
    ConfigManager.set_subcontexts(SUBCONTEXTS)
    ConfigManager.set_context_weights({"People": 1.4})
    mgr = GraphManager()
    mgr.add_node(_node("Kant", "Wisdom", "Ethics"))
    mgr.add_node(_node("Stoa", "Wisdom"))
    mgr.add_node(_node("Date night", "People", "Dating"))
    return mgr


def _save(fns, rows, state=None):
    state = state or {"rows": rows}
    return fns["save_settings"](
        1, "", "", [], [], [], [],
        40, 160, "hours", 1, 2, 4, "Sage", "title", "",
        [], "definition", "definition", [], 5,
        state, *_live(rows),
    )


class TestSave:
    def test_a_rename_saves_without_the_dialog_and_moves_the_nodes(self, seeded):
        fns = _callbacks()
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "Philosophy"
        _row(rows, "People")["name"] = "Relationships"

        status, pending, *_rest, editor = _save(fns, rows)

        assert pending is dash.no_update, "a rename must not open the migration dialog"
        # Two renames, not two plus the subcontexts that followed them.
        assert status == "Settings saved — 2 renames"
        assert ConfigManager.get_contexts() == ["Health", "Relationships", "Philosophy"]
        assert ConfigManager.get_context_weights()["Relationships"] == 1.4
        nodes = {n.name: n for n in seeded.get_all_nodes(include_dormant=True)}
        assert (nodes["Kant"].context, nodes["Kant"].subcontext) == ("Philosophy", "Ethics")
        assert nodes["Stoa"].context == "Philosophy"
        assert nodes["Date night"].context == "Relationships"
        # The editor re-seeds from what was saved, so its origins move on too.
        assert [r["orig"] for r in editor["rows"]] == [
            "Health", "Relationships", "Philosophy"]

    def test_a_removal_that_strands_nodes_waits_for_the_dialog(self, seeded):
        fns = _callbacks()
        rows = _rows()
        _row(rows, "Wisdom")["deleted"] = True
        _row(rows, "Health")["name"] = "Body"

        status, pending, *_ = _save(fns, rows)

        assert "Migration required" in status
        assert list(pending["orphans"]["context"]) == ["Wisdom"]
        assert pending["ctx_renames"] == {"Health": "Body"}
        # Nothing is written until the dialog is answered.
        assert ConfigManager.get_contexts() == CONTEXTS
        assert seeded.get_node("Kant").context == "Wisdom"

    def test_saving_before_the_editor_loads_leaves_the_taxonomy_alone(self, seeded):
        """No store means no edit, not an empty taxonomy.

        Read literally, an absent editor is a taxonomy with no rows, and
        saving it would wipe every subcontext and priority.
        """
        fns = _callbacks()
        status, pending, *_ = fns["save_settings"](
            1, "", "", [], [], [], [],
            40, 160, "hours", 1, 2, 4, "Sage", "title", "",
            [], "definition", "definition", [], 5,
            None, None, None, None, None, None, None,
        )
        assert status == "Settings saved"
        assert pending is dash.no_update
        assert ConfigManager.get_contexts() == CONTEXTS
        assert ConfigManager.get_subcontexts() == SUBCONTEXTS
        assert ConfigManager.get_context_weights()["People"] == 1.4

    def test_an_invalid_taxonomy_is_not_saved(self, seeded):
        fns = _callbacks()
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "health"

        status, pending, *_rest, editor = _save(fns, rows)

        assert "fix" in status.lower()
        assert pending is dash.no_update and editor is dash.no_update
        assert ConfigManager.get_contexts() == CONTEXTS


class TestMigrationDialog:
    def _pending(self, fns, seeded):
        rows = _rows()
        _row(rows, "Wisdom")["deleted"] = True
        _row(rows, "Health")["name"] = "Body"
        return _save(fns, rows)[1]

    def _answer(self, fns, button, pending):
        return _with_trigger(
            fns["handle_migration"], f"{button}.n_clicks", 1,
            None, 1, 1, 1, [], [], [], [], {"ctx_nodes": [], "sub_nodes": []},
            pending)

    def test_skip_still_makes_the_rename(self, seeded):
        """Skipping declines to rehome stranded nodes, not to rename."""
        fns = _callbacks()
        seeded.add_node(_node("Run", "Health", "Stress"))
        pending = self._pending(fns, seeded)

        is_open, _body, _map, editor = self._answer(fns, "btn-migration-skip", pending)

        assert is_open is False
        assert ConfigManager.get_contexts() == ["Body", "People"]
        assert seeded.get_node("Run").context == "Body"
        assert seeded.get_node("Kant").context == "Wisdom"  # left for the user
        assert [r["name"] for r in editor["rows"]] == ["Body", "People"]

    def test_cancel_writes_nothing_and_restores_the_rows(self, seeded):
        fns = _callbacks()
        pending = self._pending(fns, seeded)

        is_open, _body, _map, editor = self._answer(fns, "btn-migration-cancel", pending)

        assert is_open is False
        assert ConfigManager.get_contexts() == CONTEXTS
        assert seeded.get_node("Kant").context == "Wisdom"
        assert [r["name"] for r in editor["rows"]] == CONTEXTS


class TestStructuralEdits:
    def _edit(self, fns, prop_id, value, rows, drag="", text=""):
        state = {"rows": rows}
        return _with_trigger(
            fns["edit_context_rows"], prop_id, value,
            None, [], [], [], [], drag, None, text, state, *_live(rows))

    def test_removing_a_saved_row_keeps_it_for_undo(self, seeded):
        fns = _callbacks()
        out = self._edit(fns, _pm("ctx-row-delete", "c2"), 1, _rows())
        assert _row(out["rows"], "Wisdom")["deleted"] is True

        back = self._edit(fns, _pm("ctx-row-undelete", "c2"), 1, out["rows"])
        assert _row(back["rows"], "Wisdom")["deleted"] is False

    def test_removing_an_unsaved_row_just_drops_it(self, seeded):
        fns = _callbacks()
        rows = _rows() + [{"rid": "n9", "orig": None, "name": "Tmp",
                           "weight": 1.0, "subs": []}]
        out = self._edit(fns, _pm("ctx-row-delete", "n9"), 1, rows)
        assert [r["name"] for r in out["rows"]] == CONTEXTS

    def test_a_fresh_render_does_not_replay_a_click(self, seeded):
        """New buttons mount with n_clicks=None and fire the callback."""
        fns = _callbacks()
        out = self._edit(fns, _pm("ctx-row-delete", "c2"), None, _rows())
        assert out is dash.no_update

    def test_a_structural_edit_keeps_what_was_typed(self, seeded):
        """Names are State, not Input, so they are folded in before rebuilding."""
        fns = _callbacks()
        rows = _rows()
        live = list(_live(rows))
        live[0] = ["Health", "People", "Philosophy"]  # typed, not yet stored
        out = _with_trigger(
            fns["edit_context_rows"], _pm("ctx-sub-add", "c0"), 1,
            None, [], [], [], [], "", None, "", {"rows": rows}, *live)
        assert _row(out["rows"], "Philosophy")["orig"] == "Wisdom"
        assert len(_row(out["rows"], "Health")["subs"]) == 3

    def test_removing_a_chip(self, seeded):
        fns = _callbacks()
        out = self._edit(fns, _pm("ctx-sub-remove", "c1s0"), 1, _rows())
        assert _row(out["rows"], "People")["subs"] == []

    def test_a_drag_folds_into_the_rows(self, seeded):
        fns = _callbacks()
        drag = json.dumps({"rows": ["c1", "c0", "c2"]})
        out = self._edit(fns, "ctx-editor-drag-input.value", drag, _rows(), drag=drag)
        assert [r["name"] for r in out["rows"]] == ["People", "Health", "Wisdom"]

    def test_applying_the_text_view(self, seeded):
        fns = _callbacks()
        text = "Health: Stress, Rhythms\nPeople: Dating\nPhilosophy: Ethics, Logic"
        out = self._edit(fns, "btn-ctx-text-apply.n_clicks", 1, _rows(), text=text)
        assert _row(out["rows"], "Philosophy")["orig"] == "Wisdom"


def test_opening_settings_fills_every_output_and_seeds_the_rows(seeded):
    """load_settings swapped the weights container for the editor store; a
    tuple one short or long is rejected by Dash at runtime, not at import."""
    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    settings_callbacks.register_settings_callbacks(app)
    key, spec = next((k, s) for k, s in app.callback_map.items()
                     if "context-editor-store.data" in k and "setting-hp-profile.value" in k)
    fn = spec["callback"]
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__

    out = fn(True)
    assert len(out) == len(key.strip(".").split("..."))
    assert len(fn(False)) == len(out)
    editor, text = out[0], out[1]
    assert [r["orig"] for r in editor["rows"]] == CONTEXTS
    assert editor["counts"]["ctx"] == {"Wisdom": 2, "People": 1}
    assert text.splitlines()[0] == "Health: Stress, Rhythms"


class TestLiveValidation:
    def test_flags_line_up_with_their_inputs(self, seeded):
        fns = _callbacks()
        rows = _rows()
        names, name_ids, _w, _wi, subs, sub_ids = _live(rows)
        names[2] = "health"
        state = {"rows": rows, "old": {"contexts": CONTEXTS, "subcontexts": SUBCONTEXTS}}
        name_flags, sub_flags, text, cls = fns["validate_context_editor"](
            names, subs, state, name_ids, sub_ids)
        assert name_flags == [False, False, True]
        assert not any(sub_flags)
        assert "already a context" in text
        assert "error" in cls


# --- Rendering ------------------------------------------------------------------------

def _walk(component):
    if isinstance(component, (list, tuple)):
        for child in component:
            yield from _walk(child)
        return
    if not hasattr(component, "to_plotly_json"):
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def test_the_editors_plain_ids_are_in_the_static_layout():
    """A callback Input with a plain string id must exist in the initial layout.

    The app does not suppress callback exceptions, so Dash reports "ID not
    found in layout" for any that only appear once a callback renders them.
    "Add context" first lived inside the rendered rows and did exactly that;
    only pattern-matched ids may live there.
    """
    from settings_layout import build_settings_modal

    static = {c.id for c in _walk(build_settings_modal())
              if isinstance(getattr(c, "id", None), str)}
    rendered = {c.id for c in _walk(build_context_editor_rows(_rows()))
                if isinstance(getattr(c, "id", None), str)}

    app = dash.Dash(__name__)
    app.config.suppress_callback_exceptions = True
    settings_callbacks.register_settings_callbacks(app)
    editor_ids = set()
    for spec in app.callback_map.values():
        for dep in spec.get("inputs", []) + spec.get("state", []):
            dep_id = dep["id"]
            if not dep_id.startswith("{") and ("ctx" in dep_id or "context-editor" in dep_id):
                editor_ids.add(dep_id)

    assert "btn-ctx-row-add" in editor_ids
    assert editor_ids <= static, sorted(editor_ids - static)
    assert rendered <= {"ctx-editor-rows"}, sorted(rendered)


class TestBuildContextEditorRows:
    def test_one_name_input_per_live_row_and_one_chip_per_subcontext(self):
        tree = build_context_editor_rows(_rows(), {"Wisdom": 3})
        ids = [c.id for c in _walk(tree) if isinstance(getattr(c, "id", None), dict)]
        assert [i["index"] for i in ids if i["type"] == "ctx-row-name"] == ["c0", "c1", "c2"]
        assert len([i for i in ids if i["type"] == "ctx-sub-name"]) == 5

    def test_counts_follow_the_name_the_nodes_still_carry(self):
        rows = _rows()
        _row(rows, "Wisdom")["name"] = "Philosophy"
        tree = build_context_editor_rows(rows, {"Wisdom": 3})
        counts = [c.children for c in _walk(tree)
                  if getattr(c, "className", None) == "ctx-row-count"]
        assert counts == ["", "", "3"]

    def test_a_removed_row_offers_undo_instead_of_inputs(self):
        rows = _rows()
        _row(rows, "Wisdom")["deleted"] = True
        tree = build_context_editor_rows(rows, {"Wisdom": 3})
        ids = [c.id for c in _walk(tree) if isinstance(getattr(c, "id", None), dict)]
        assert {"type": "ctx-row-undelete", "index": "c2"} in ids
        assert {"type": "ctx-row-name", "index": "c2"} not in ids
        text = " ".join(c.children for c in _walk(tree)
                        if isinstance(getattr(c, "children", None), str))
        assert "3 nodes need a new home" in text

    def test_errors_mark_their_inputs_invalid(self):
        tree = build_context_editor_rows(_rows(), errors={"row:c1": "x", "sub:c0s1": "y"})
        flagged = {c.id["index"] for c in _walk(tree)
                   if isinstance(getattr(c, "id", None), dict) and getattr(c, "invalid", False)}
        assert flagged == {"c1", "c0s1"}
