"""Pure graph invariants, without storage or UI dependencies."""
import unicodedata
from typing import Optional, Tuple
from models import EDGE_HELPS, STATUS_DONE

# Longest name a node, event or alias may take. Names are identifiers that
# lists, menus and the canvas all have to show, not a place for prose; the
# description is.
NAME_MAX_LENGTH = 200


def name_problem(name, label) -> Optional[str]:
    """Why ``name`` can't be saved, or None when it can.

    ``label`` says what the name belongs to ("Node name", "Event name"). A
    name keys the database and travels through menus, the canvas and hidden
    inputs, so it is one line of text without surrounding spaces, short
    enough for a list to show.
    """
    if not isinstance(name, str) or not name.strip():
        return f"{label} is required."
    if name != name.strip():
        return f"{label} can't start or end with a space."
    if len(name) > NAME_MAX_LENGTH:
        return (f"{label} is {len(name)} characters long. "
                f"Keep it to {NAME_MAX_LENGTH} or fewer.")
    # Cc covers tabs, newlines and other control characters; Zl and Zp are
    # the Unicode line and paragraph separators.
    if any(unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in name):
        return f"{label} must be a single line, without tabs or control characters."
    return None


def _canonicalize_edge(source: str, target: str, edge_type: str) -> Tuple[str, str]:
    """Helps is bidirectional: (A,B,Helps) and (B,A,Helps) describe the
    same fact (verified in scoring.build_adjacency, which mirrors Syn for
    either row). Canonicalize so only one row per pair can exist by
    sorting endpoints lexically. Hard/Soft direction is meaningful and
    kept as-is.
    """
    if edge_type == EDGE_HELPS and source > target:
        return target, source
    return source, target


def _is_prereq_satisfied(p_node) -> bool:
    """Check if a prerequisite node is satisfied (Done)."""
    if not p_node:
        return False
    return p_node.status == STATUS_DONE
