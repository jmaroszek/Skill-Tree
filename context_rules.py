"""Pure rules for the context/subcontext editor and its migrations.

The Contexts settings tab edits a list of *rows*, not a block of text. Each row
carries the name it was loaded under (``orig``), so an edit says what the user
meant instead of leaving the save path to guess:

    orig set, name differs   -> rename       (applied straight to the nodes)
    orig unset               -> new context
    orig with no row         -> deletion     (the only case that needs the
                                              migration dialog)

Subcontexts are identified by the ``(context, subcontext)`` pair, so each one
also remembers the context it was loaded under (``orig_ctx``). That is what
lets a chip move between contexts as a move rather than a delete plus an add.

Row shape::

    {"rid": str, "orig": str|None, "name": str, "weight": float,
     "subs": [{"sid": str, "orig": str|None, "orig_ctx": str|None,
               "name": str}]}
"""

DEFAULT_CONTEXT_WEIGHT = 1.0

# Both characters are structural in the "Name: sub, sub" grammar the text view
# round-trips through, and neither has ever survived a save. Rejecting them
# states a restriction that was previously silent.
_FORBIDDEN_IN_CONTEXT = (":", ",")
_FORBIDDEN_IN_SUBCONTEXT = (",",)


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


# --- Row model ---------------------------------------------------------------

def taxonomy_to_rows(contexts, subcontexts, weights=None):
    """Build editor rows from the persisted taxonomy.

    Every row and chip starts out claiming its stored name as its origin, which
    is what makes a later edit legible as a rename rather than a replacement.
    Subcontexts stored under a context that is not in ``contexts`` still get a
    row, so an inconsistent config is visible and fixable instead of silently
    dropped on the next save.
    """
    weights = weights or {}
    subcontexts = subcontexts or {}
    ordered = list(contexts or [])
    ordered += [c for c in subcontexts if c not in set(ordered)]

    rows = []
    for i, ctx in enumerate(ordered):
        rows.append({
            "rid": f"c{i}",
            "orig": ctx,
            "name": ctx,
            "weight": float(weights.get(ctx, DEFAULT_CONTEXT_WEIGHT)),
            "subs": [
                {"sid": f"c{i}s{j}", "orig": sub, "orig_ctx": ctx, "name": sub}
                for j, sub in enumerate(subcontexts.get(ctx, []))
            ],
        })
    return rows


def next_row_id(rows):
    """A row id no current row uses. Ids only need to be unique per session."""
    used = {str(row.get("rid", "")) for row in rows or []}
    return _unused("n", used)


def next_sub_id(rows):
    """A chip id no current chip uses, unique across every row."""
    used = {str(s.get("sid", ""))
            for row in rows or [] for s in row.get("subs", [])}
    return _unused("m", used)


def _unused(prefix, used):
    n = len(used)
    while f"{prefix}{n}" in used:
        n += 1
    return f"{prefix}{n}"


def normalize_rows(rows):
    """Trim names, and drop rows marked removed and anything added but never named.

    A row the user removed is kept in the store (struck through, undoable)
    until Save, so every reader of the live taxonomy has to skip it here.
    A blank row or chip that was never saved is an unfinished add, not an
    error — the editor leaves an empty input behind after every add. A saved
    one whose name was cleared survives, so validation can ask what was meant.
    """
    clean = []
    for row in rows or []:
        if row.get("deleted"):
            continue
        if not (row.get("name") or "").strip() and not row.get("orig"):
            continue
        subs = []
        for sub in row.get("subs", []):
            name = (sub.get("name") or "").strip()
            if not name and not sub.get("orig"):
                continue
            subs.append({**sub, "name": name})
        clean.append({**row, "name": (row.get("name") or "").strip(), "subs": subs})
    return clean


def rows_to_taxonomy(rows):
    """Collapse rows into the ``(contexts, subcontexts, weights)`` triple.

    Row order is the defined order, which is what the "Defined order" sort mode
    reads. Contexts with no subcontexts are left out of the subcontext map
    rather than carrying an empty list, matching what the old parser produced.
    """
    contexts = []
    subcontexts = {}
    weights = {}
    for row in rows or []:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if name not in contexts:
            contexts.append(name)
        subs = [(s.get("name") or "").strip() for s in row.get("subs", [])]
        subs = [s for s in subs if s]
        if subs:
            subcontexts.setdefault(name, []).extend(
                s for s in subs if s not in subcontexts.get(name, [])
            )
        try:
            weights[name] = float(row.get("weight", DEFAULT_CONTEXT_WEIGHT))
        except (TypeError, ValueError):
            weights[name] = DEFAULT_CONTEXT_WEIGHT
    return contexts, subcontexts, weights


def validate_rows(rows):
    """Return ``{"row:<rid>": message}`` / ``{"sub:<sid>": message}`` for each problem.

    An empty dict means the taxonomy is saveable. Names are compared
    case-insensitively: ``STEM`` and ``Stem`` would become two contexts that
    look like one, which is how a stray shift key used to split a context in
    the text field.
    """
    errors = {}
    seen = {}
    for row in rows or []:
        name = (row.get("name") or "").strip()
        rid = row.get("rid")
        if not name:
            errors[f"row:{rid}"] = "Give this context a name, or remove the row."
            continue
        bad = [c for c in _FORBIDDEN_IN_CONTEXT if c in name]
        if bad:
            errors[f"row:{rid}"] = (
                f"A context name cannot contain {' or '.join(repr(c) for c in bad)}.")
            continue
        key = name.casefold()
        if key in seen:
            errors[f"row:{rid}"] = f"'{seen[key]}' is already a context."
            continue
        seen[key] = name

        sub_seen = {}
        for sub in row.get("subs", []):
            sub_name = (sub.get("name") or "").strip()
            sid = sub.get("sid")
            if not sub_name:
                errors[f"sub:{sid}"] = "Name this subcontext, or remove it."
                continue
            if any(c in sub_name for c in _FORBIDDEN_IN_SUBCONTEXT):
                errors[f"sub:{sid}"] = "A subcontext name cannot contain ','."
                continue
            sub_key = sub_name.casefold()
            if sub_key in sub_seen:
                errors[f"sub:{sid}"] = f"'{sub_seen[sub_key]}' is already in {name}."
                continue
            sub_seen[sub_key] = sub_name
    return errors


# --- Diffing -----------------------------------------------------------------

def plan_taxonomy_change(rows, old_contexts, old_subcontexts):
    """Work out what the edited rows mean for the stored taxonomy and the nodes.

    Returns a dict with the taxonomy to persist plus four change sets:

      ``ctx_renames``   {old: new} — apply straight to the nodes, no dialog.
      ``pair_moves``    [[old_ctx, old_sub, new_ctx, new_sub]] — same, for the
                        (context, subcontext) pairs that moved or were renamed.
      ``deleted_contexts``  old names no row claims any more.
      ``deleted_pairs``     [[ctx, sub]] dropped while their context survives.

    Only the two deletion lists can strand nodes, so they are the only reason
    to open the migration dialog. Pair moves are ordered before context renames
    by ``GraphManager.apply_taxonomy_migration``, which is what lets a renamed
    context and a moved chip inside it both land correctly.
    """
    rows = normalize_rows(rows)
    contexts, subcontexts, weights = rows_to_taxonomy(rows)

    old_contexts = list(old_contexts or [])
    old_subcontexts = old_subcontexts or {}

    ctx_renames = {}
    claimed = set()
    for row in rows:
        orig = row.get("orig")
        name = (row.get("name") or "").strip()
        if not orig or not name or orig in claimed:
            continue
        claimed.add(orig)
        if orig != name:
            ctx_renames[orig] = name

    pair_moves = []
    claimed_pairs = set()
    for row in rows:
        new_ctx = (row.get("name") or "").strip()
        if not new_ctx:
            continue
        for sub in row.get("subs", []):
            orig, orig_ctx = sub.get("orig"), sub.get("orig_ctx")
            new_sub = (sub.get("name") or "").strip()
            if not orig or not orig_ctx or not new_sub:
                continue
            pair = (orig_ctx, orig)
            if pair in claimed_pairs:
                continue
            claimed_pairs.add(pair)
            if pair != (new_ctx, new_sub):
                pair_moves.append([orig_ctx, orig, new_ctx, new_sub])

    surviving = {row.get("orig") for row in rows if row.get("orig")}
    deleted_contexts = [c for c in old_contexts if c not in surviving]

    gone = set(deleted_contexts)
    deleted_pairs = [
        [ctx, sub]
        for ctx, subs in old_subcontexts.items()
        if ctx not in gone
        for sub in subs
        if (ctx, sub) not in claimed_pairs
    ]

    return {
        "contexts": contexts,
        "subcontexts": subcontexts,
        "weights": weights,
        "ctx_renames": ctx_renames,
        "pair_moves": pair_moves,
        "deleted_contexts": deleted_contexts,
        "deleted_pairs": deleted_pairs,
    }


def describe_plan(plan, ctx_counts=None, pair_counts=None):
    """One plain sentence summarising what a save would do, or '' for no change."""
    ctx_counts = ctx_counts or {}
    pair_counts = pair_counts or {}
    parts = []

    # A chip whose context was renamed rides along with it; that is not a
    # move. It moved only if it ended up somewhere its parent did not go.
    followed = plan["ctx_renames"]
    renames = len(followed) + sum(
        1 for _, old_sub, _, new_sub in plan["pair_moves"] if old_sub != new_sub)
    moves = sum(1 for old_ctx, _, new_ctx, _ in plan["pair_moves"]
                if new_ctx != followed.get(old_ctx, old_ctx))
    if renames:
        parts.append(f"{renames} rename{'s' if renames != 1 else ''}")
    if moves:
        parts.append(f"{moves} move{'s' if moves != 1 else ''}")

    stranded = sum(ctx_counts.get(c, 0) for c in plan["deleted_contexts"])
    stranded += sum(pair_counts.get(tuple(p), 0) for p in plan["deleted_pairs"])
    removals = len(plan["deleted_contexts"]) + len(plan["deleted_pairs"])
    if removals:
        label = f"{removals} removal{'s' if removals != 1 else ''}"
        if stranded:
            label += f" affecting {stranded} node{'s' if stranded != 1 else ''}"
        parts.append(label)

    if not parts:
        return ""
    tail = " · needs the migration dialog" if stranded else ""
    return " · ".join(parts) + tail


# --- Text view ---------------------------------------------------------------

def parse_context_text(text):
    """Parse the "Name: sub, sub" grammar into ``(contexts, subcontexts)``.

    Kept for the text view, which stays as the fast path for bulk edits.
    Repeated context lines merge their subcontexts, as they always have.
    """
    contexts = []
    subcontexts = {}
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            ctx_name, subs_str = line.split(":", 1)
            ctx_name = ctx_name.strip()
            subs = [s.strip() for s in subs_str.split(",") if s.strip()]
        else:
            ctx_name, subs = line, []
        if not ctx_name:
            continue
        if ctx_name not in contexts:
            contexts.append(ctx_name)
        for sub in subs:
            bucket = subcontexts.setdefault(ctx_name, [])
            if sub not in bucket:
                bucket.append(sub)
    return contexts, subcontexts


def format_context_text(contexts, subcontexts):
    """Render the taxonomy back into the text grammar."""
    subcontexts = subcontexts or {}
    lines = []
    for ctx in contexts or []:
        subs = subcontexts.get(ctx, [])
        lines.append(f"{ctx}: {', '.join(subs)}" if subs else ctx)
    for ctx, subs in subcontexts.items():
        if ctx not in (contexts or []):
            lines.append(f"{ctx}: {', '.join(subs)}")
    return "\n".join(lines)


def rows_to_text(rows):
    """Render the current rows into the text grammar."""
    contexts, subcontexts, _ = rows_to_taxonomy(normalize_rows(rows))
    return format_context_text(contexts, subcontexts)


def reconcile_rows_with_text(text, rows):
    """Fold a text edit back into rows, keeping identity where it can be traced.

    Lines are matched to existing rows by name first, then by position among
    what is left over. Position is what recovers a rename: editing "Humanities"
    to "Arts" on line six leaves an unmatched line six and an unclaimed row
    six, so the row keeps its origin and the save reads it as a rename. A line
    with no counterpart is a new context; a row no line claims is a deletion.
    """
    rows = normalize_rows(rows)
    contexts, subcontexts = parse_context_text(text)

    by_name = {}
    for i, row in enumerate(rows):
        by_name.setdefault((row.get("name") or "").casefold(), []).append(i)

    taken = set()
    matched = {}
    for pos, ctx in enumerate(contexts):
        bucket = by_name.get(ctx.casefold(), [])
        for i in bucket:
            if i not in taken:
                taken.add(i)
                matched[pos] = i
                break

    # Positional fallback: pair the nth unmatched line with the nth unclaimed
    # row, so an in-place rename keeps that row's origin.
    spare = [i for i in range(len(rows)) if i not in taken]
    for pos in range(len(contexts)):
        if pos not in matched and spare:
            matched[pos] = spare.pop(0)

    out = []
    for pos, ctx in enumerate(contexts):
        source = rows[matched[pos]] if pos in matched else None
        subs = _reconcile_subs(subcontexts.get(ctx, []), source, ctx)
        out.append({
            "rid": source["rid"] if source else f"t{pos}",
            "orig": source.get("orig") if source else None,
            "name": ctx,
            "weight": source.get("weight", DEFAULT_CONTEXT_WEIGHT) if source
                      else DEFAULT_CONTEXT_WEIGHT,
            "subs": subs,
        })
    return _dedupe_ids(out)


def _reconcile_subs(names, source, ctx):
    """Match parsed subcontext names back to a row's chips, by name then position."""
    existing = list((source or {}).get("subs", []))
    by_name = {}
    for i, sub in enumerate(existing):
        by_name.setdefault((sub.get("name") or "").casefold(), []).append(i)

    taken = set()
    matched = {}
    for pos, name in enumerate(names):
        for i in by_name.get(name.casefold(), []):
            if i not in taken:
                taken.add(i)
                matched[pos] = i
                break

    spare = [i for i in range(len(existing)) if i not in taken]
    for pos in range(len(names)):
        if pos in matched or not spare:
            continue
        matched[pos] = spare.pop(0)

    subs = []
    for pos, name in enumerate(names):
        src = existing[matched[pos]] if pos in matched else None
        subs.append({
            "sid": src["sid"] if src else f"t{ctx}{pos}",
            "orig": src.get("orig") if src else None,
            "orig_ctx": src.get("orig_ctx") if src else None,
            "name": name,
        })
    return subs


def _dedupe_ids(rows):
    """Guarantee unique rids/sids after a reconcile stitched rows together."""
    seen_rid, seen_sid, n = set(), set(), 0
    for row in rows:
        while row["rid"] in seen_rid:
            n += 1
            row["rid"] = f"d{n}"
        seen_rid.add(row["rid"])
        for sub in row["subs"]:
            while sub["sid"] in seen_sid:
                n += 1
                sub["sid"] = f"e{n}"
            seen_sid.add(sub["sid"])
    return rows


def apply_drag_order(rows, order):
    """Reorder rows and move chips between them from the DOM order JS reports.

    ``order`` is ``{"rows": [rid, ...], "subs": {rid: [sid, ...]}}``. Anything
    the payload does not mention keeps its current place, so a stale payload
    degrades to a no-op rather than dropping a row.
    """
    if not isinstance(order, dict):
        return rows
    rows = list(rows or [])
    by_rid = {row["rid"]: row for row in rows}

    wanted = [r for r in order.get("rows", []) if r in by_rid]
    ordered = [by_rid[r] for r in wanted]
    ordered += [row for row in rows if row["rid"] not in set(wanted)]

    sub_order = order.get("subs") or {}
    if not sub_order:
        return ordered

    pool = {s["sid"]: s for row in ordered for s in row.get("subs", [])}
    home = {s["sid"]: row["rid"] for row in ordered for s in row.get("subs", [])}
    placed, assigned = set(), {}
    for row in ordered:
        wanted_subs = [s for s in sub_order.get(row["rid"], [])
                       if s in pool and s not in placed]
        assigned[row["rid"]] = [pool[s] for s in wanted_subs]
        placed.update(wanted_subs)
    # A chip the payload never named stays where it was, so a partial or stale
    # payload cannot silently delete one.
    for sid, sub in pool.items():
        if sid not in placed:
            assigned.setdefault(home[sid], []).append(sub)
    for row in ordered:
        row["subs"] = assigned.get(row["rid"], [])
    return ordered
