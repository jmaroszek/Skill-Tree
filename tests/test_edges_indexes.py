"""Phase F: verify the Edges(target,type) index exists and is used by reverse
graph-traversal queries.

The PRIMARY KEY (source, target, type) auto-index already covers source-side
queries like WHERE source=? AND type=?, so only the target-side index is
added manually — adding a redundant source-side index would just duplicate
storage without improving query plans.
"""

import database


def test_idx_edges_target_type_present():
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_edges_target_type",),
        )
        assert cursor.fetchone() is not None


def test_edges_source_type_query_uses_pk_autoindex():
    """Baseline: the PK auto-index already handles source-side queries."""
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "EXPLAIN QUERY PLAN SELECT target FROM Edges WHERE source=? AND type=?",
            ("A", "Needs_Hard"),
        )
        plan_text = " ".join(str(row) for row in cursor.fetchall()).lower()
        assert "index" in plan_text, f"source query should use an index: {plan_text}"


def test_edges_target_type_query_uses_new_index():
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "EXPLAIN QUERY PLAN SELECT source FROM Edges WHERE target=? AND type=?",
            ("B", "Needs_Hard"),
        )
        plan_text = " ".join(str(row) for row in cursor.fetchall()).lower()
        assert "idx_edges_target_type" in plan_text, (
            f"target query did not use idx_edges_target_type: {plan_text}"
        )


def test_init_db_is_idempotent_with_indexes():
    """CREATE INDEX IF NOT EXISTS must allow safe repeat invocations."""
    database._initialized = False
    database.init_db()
    database._initialized = False
    database.init_db()  # second call: index already exists; should silently pass
    with database.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_edges_target_type",),
        )
        assert cursor.fetchone()[0] == 1
