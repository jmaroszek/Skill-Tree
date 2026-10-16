"""Moving nodes when Settings renames, moves or removes contexts and subcontexts:
finding the nodes a change orphans, counting nodes per context, and the bulk
remaps. GraphManager's methods of the same names delegate here."""
from typing import Dict, List, Optional

from skilltree.domain.contexts import compute_orphaned_subcontext_pairs
from skilltree.domain.models import Node
from skilltree.store import database
from skilltree.store.graph.state import SCORING_RELEVANT_FIELDS


def find_orphaned_nodes(graph, field: str, old_values: list, new_values: list) -> Dict[str, List[Node]]:
    """Find nodes that reference removed values for a given field.

    Returns a dict mapping each removed value to the list of nodes that still reference it.
    Only includes entries where at least one node is affected.

    Includes dormant nodes — they reference config values too, and silently
    leaving them out means a context/type/subcontext can be deleted while
    dormant nodes still hold the stale value, only surfacing as broken
    config when the event later triggers them back into play.
    """
    removed = set(old_values) - set(new_values)
    if not removed:
        return {}

    all_nodes = graph.get_all_nodes(include_dormant=True)
    orphans = {}
    for val in removed:
        affected = [n for n in all_nodes if getattr(n, field, None) == val]
        if affected:
            orphans[val] = affected
    return orphans


def find_nodes_by_pairs(graph, pairs) -> Dict[str, List[Node]]:
    """Group nodes by the (context, subcontext) pairs they still reference.

    Keyed by 'ctx > sub' display labels, and only for pairs that actually
    hold nodes. Includes dormant nodes — see find_orphaned_nodes.
    """
    pairs = [tuple(p) for p in pairs or []]
    if not pairs:
        return {}

    all_nodes = graph.get_all_nodes(include_dormant=True)
    found = {}
    for ctx, sub in pairs:
        affected = [n for n in all_nodes if n.context == ctx and n.subcontext == sub]
        if affected:
            found[f"{ctx} > {sub}"] = affected
    return found


def find_orphaned_subcontext_pairs(graph, old_subcontexts: Dict, new_subcontexts: Dict,
                                   new_contexts: list) -> Dict[str, List[Node]]:
    """Find nodes whose (context, subcontext) pair no longer exists in the new structure.

    Subcontext identity is the (context, subcontext) tuple, not the bare name —
    moving a subcontext between parents leaves the bare name in the flat list but
    invalidates the pair. Returns a dict keyed by 'ctx > sub' display labels.

    This compares taxonomies by name. The Contexts editor tracks each row's
    origin instead, so it names the dropped pairs itself and calls
    find_nodes_by_pairs directly.
    """
    pairs = compute_orphaned_subcontext_pairs(old_subcontexts, new_subcontexts, new_contexts)
    return graph.find_nodes_by_pairs(pairs)


def count_nodes_by_context(graph):
    """Return ({context: n}, {(context, subcontext): n}) across every node.

    Feeds the blast-radius counts in the Contexts editor, so it counts
    dormant nodes too: they hold config values just the same, and a
    deletion strands them just the same.
    """
    ctx_counts: Dict[str, int] = {}
    pair_counts: Dict[tuple, int] = {}
    for node in graph.get_all_nodes(include_dormant=True):
        if not node.context:
            continue
        ctx_counts[node.context] = ctx_counts.get(node.context, 0) + 1
        if node.subcontext:
            key = (node.context, node.subcontext)
            pair_counts[key] = pair_counts.get(key, 0) + 1
    return ctx_counts, pair_counts


@database.atomic
def apply_taxonomy_migration(graph, ctx_renames: Dict[str, str],
                             pair_moves) -> None:
    """Carry context renames and (context, subcontext) moves onto the nodes.

    Each node's destination comes from the values it holds before any of
    the changes. A pair move claims the nodes in its pair; a context rename
    reaches the rest of that context — nodes with no subcontext, or with
    one being dropped. Writing them one UPDATE at a time instead would let
    a later rename re-match nodes an earlier one had just moved, so a swap
    (Mind <-> Body) or a chain (Mind -> Body -> Physical) would pour two
    contexts into one.
    """
    pair_moves = {(m[0], m[1]): (m[2], m[3]) for m in pair_moves or []}
    ctx_renames = ctx_renames or {}
    if not ctx_renames and not pair_moves:
        return

    with graph.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, context, subcontext FROM Nodes")
        moves = []
        for name, context, subcontext in cursor.fetchall():
            dest = pair_moves.get((context, subcontext))
            if dest is None and context in ctx_renames:
                dest = (ctx_renames[context], subcontext)
            if dest is not None and dest != (context, subcontext):
                moves.append((*dest, name))
        cursor.executemany(
            "UPDATE Nodes SET context=?, subcontext=? WHERE name=?", moves)
        conn.commit()
    graph._bump_version(scoring=True)


@database.atomic
def apply_migration(graph, field: str, remap: Dict[str, str], new_subcontexts: Optional[Dict] = None):
    """Remap node attribute values in bulk.

    Args:
        field: 'context', 'subcontext', or 'type'
        remap: maps old_value -> new_value (or None to clear)
        new_subcontexts: when field is 'context', used to check if subcontexts are still valid
    """
    if not remap:
        return

    with graph.get_connection() as conn:
        cursor = conn.cursor()
        for old_val, chosen in remap.items():
            new_val = None if chosen == '__clear__' else chosen

            # Apply the remap
            cursor.execute(f"UPDATE Nodes SET [{field}]=? WHERE [{field}]=?", (new_val, old_val))

            # When context changes, clear subcontexts that don't exist under the new context
            if field == 'context' and new_val is not None and new_subcontexts is not None:
                valid_subs = set(new_subcontexts.get(new_val, []))
                if valid_subs:
                    # Clear subcontext if it's not valid under the new context
                    cursor.execute(
                        "SELECT name, subcontext FROM Nodes WHERE context=? AND subcontext IS NOT NULL",
                        (new_val,)
                    )
                    for name, sub in cursor.fetchall():
                        if sub not in valid_subs:
                            cursor.execute("UPDATE Nodes SET subcontext=NULL WHERE name=?", (name,))
                else:
                    # New context has no subcontexts — clear them all
                    cursor.execute("UPDATE Nodes SET subcontext=NULL WHERE context=?", (new_val,))

        conn.commit()
    # Every field these migrations accept (context / subcontext / type) is
    # scoring-relevant, so a bulk remap must invalidate the scoring caches.
    # Keying off the field set keeps this honest if the accepted fields grow.
    graph._bump_version(scoring=field in SCORING_RELEVANT_FIELDS)
    if field == 'type':
        graph.recompute_all_statuses()


@database.atomic
def apply_node_migration(graph, node_name: str, field: str, new_val: str,
                         new_subcontexts: Optional[Dict] = None):
    """Remap a single node's attribute value.

    Args:
        node_name: name (primary key) of the node to update
        field: 'context', 'subcontext', or 'type'
        new_val: the new value, or '__clear__' to set NULL
        new_subcontexts: when field is 'context', used to check if subcontexts are still valid
    """
    with graph.get_connection() as conn:
        cursor = conn.cursor()
        actual_val = None if new_val == '__clear__' else new_val

        cursor.execute(f"UPDATE Nodes SET [{field}]=? WHERE name=?", (actual_val, node_name))

        # When context changes, clear subcontext if invalid under the new context
        if field == 'context' and actual_val is not None and new_subcontexts is not None:
            valid_subs = set(new_subcontexts.get(actual_val, []))
            cursor.execute("SELECT subcontext FROM Nodes WHERE name=?", (node_name,))
            row = cursor.fetchone()
            if row and row[0] and row[0] not in valid_subs:
                cursor.execute("UPDATE Nodes SET subcontext=NULL WHERE name=?", (node_name,))

        conn.commit()
    # Every field these migrations accept (context / subcontext / type) is
    # scoring-relevant, so a bulk remap must invalidate the scoring caches.
    # Keying off the field set keeps this honest if the accepted fields grow.
    graph._bump_version(scoring=field in SCORING_RELEVANT_FIELDS)
    if field == 'type':
        graph.recompute_all_statuses()
