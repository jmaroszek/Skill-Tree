"""Pure rules for context and subcontext migrations."""

def compute_orphaned_subcontext_pairs(old_subcontexts, new_subcontexts, new_contexts):
    """(ctx, sub) pairs present in old but not in new, where ctx still exists in new_contexts.

    Subcontexts are identified by (context, subcontext) tuple — the same name under a
    different parent is a distinct pair. Pairs whose parent context is being removed
    are skipped (those nodes are handled by the context-orphan path instead).
    """
    new_contexts_set = set(new_contexts)
    pairs = []
    for ctx, subs in old_subcontexts.items():
        if ctx not in new_contexts_set:
            continue
        new_subs = set(new_subcontexts.get(ctx, []))
        for sub in subs:
            if sub not in new_subs:
                pairs.append((ctx, sub))
    return pairs


def detect_context_renames(old_contexts, new_contexts, old_subcontexts, new_subcontexts):
    """Detect 1:1 context renames where the new context preserves all old subcontexts.

    Returns {old_ctx: new_ctx} when exactly one context was removed and exactly one
    was added, AND the new context's subcontexts are a superset of the old's. This
    is conservative on purpose — false positives would silently merge unrelated
    contexts. Anything ambiguous returns {} so the user disambiguates in the modal.
    """
    removed = [c for c in old_contexts if c not in set(new_contexts)]
    added = [c for c in new_contexts if c not in set(old_contexts)]
    if len(removed) != 1 or len(added) != 1:
        return {}
    old_ctx, new_ctx = removed[0], added[0]
    old_subs = set(old_subcontexts.get(old_ctx, []))
    new_subs = set(new_subcontexts.get(new_ctx, []))
    if not old_subs.issubset(new_subs):
        return {}
    return {old_ctx: new_ctx}
