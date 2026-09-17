"""Pure graph invariants, without storage or UI dependencies."""
from typing import Tuple
from models import EDGE_HELPS, STATUS_DONE

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
