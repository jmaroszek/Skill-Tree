"""Names and ranks the clusters the Community filter lists.

A label says what a cluster is about. It is an optional context prefix, then
up to three hubs: the nodes the cluster is built around. Hubs are member
names, and a node belongs to one cluster, so labels come out unique.

Pure functions over plain data, so they test without a database.
`graph_queries.list_communities` gathers the inputs.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT

# A context or subcontext appears as a prefix only when it holds this share
# of the cluster. A bare majority would name a half-mixed cluster after one
# side.
PREFIX_SHARE = 0.7
# With no prefix, a hub's context must hold this share of the cluster, so a
# small tail from another area can't name it.
MIXED_CONTEXT_SHARE = 0.2
MAX_HUBS = 3
# A second or third hub joins only while the label fits this many characters.
# With the node count after it, that wraps to at most two lines in the
# sidebar's Community select.
MAX_LABEL_CHARS = 50
# A further hub must reach at least this share of the cluster that the
# earlier hubs don't.
MIN_NEW_REACH = 0.1
# The Community list shows this many clusters at most. The rest, and every
# cluster too small to be worth a row, share one "Other" entry.
MAX_LISTED = 15
MIN_LISTED_SIZE = 3
OTHER_VALUE = "__other__"


@dataclass
class CommunityListing:
    """What the Community filter offers: ``listed`` holds (label, members)
    pairs, most important first; ``other`` holds every member folded into
    the Other entry."""
    listed: List[tuple] = field(default_factory=list)
    other: Set[str] = field(default_factory=set)
    other_clusters: int = 0


def _top(counter):
    """The most common key, ties broken by name so a label never depends on
    set iteration order."""
    return min(counter.items(), key=lambda kv: (-kv[1], str(kv[0]).casefold()))


def _adjacency(edges, members):
    neighbors = defaultdict(set)
    prereqs = defaultdict(set)
    for e in edges:
        s, t = e['source'], e['target']
        if s == t or s not in members or t not in members:
            continue
        neighbors[s].add(t)
        neighbors[t].add(s)
        if e['type'] in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            prereqs[t].add(s)
    return neighbors, prereqs


def _ancestors(name, prereqs, cluster):
    """Every cluster member whose prerequisite chain reaches ``name``."""
    found, stack = set(), [name]
    while stack:
        for p in prereqs[stack.pop()]:
            if p in cluster and p not in found:
                found.add(p)
                stack.append(p)
    return found


def _prefix(members):
    """The cluster's context prefix, its top context, and the contexts a hub
    may come from."""
    contexts = Counter(n.context for n in members)
    named = Counter({c: k for c, k in contexts.items() if c})
    if not named:
        return None, None, {None}
    top, k = _top(named)
    subs = Counter(n.subcontext for n in members
                   if n.context == top and n.subcontext)
    size = len(members)
    if subs:
        sub, sk = _top(subs)
        if sk / size >= PREFIX_SHARE:
            return f"{top} > {sub}", top, {top}
    if k / size >= PREFIX_SHARE:
        return top, top, {top}
    return None, top, {c for c, v in contexts.items()
                       if v / size >= MIXED_CONTEXT_SHARE}


def _pick_hubs(cluster, by_name, neighbors, prereqs, allowed, hub_score):
    """Up to MAX_HUBS hubs, best first.

    Goals come first, chosen greedily by reach: the members whose
    prerequisites lead into the Goal, plus its neighbors. Goals sum up a
    cluster better than any concept inside it. A cluster with no usable Goal
    falls back to the Analyze tab's hub score, then to the best-connected
    members.
    """
    size = len(cluster)

    def degree(x):
        return len(neighbors[x] & cluster)

    goals = {x: _ancestors(x, prereqs, cluster) | (neighbors[x] & cluster) | {x}
             for x in cluster if by_name[x].type == 'Goal' and allowed(x)}
    hubs, covered = [], set()
    while goals and len(hubs) < MAX_HUBS:
        best = min(goals, key=lambda x: (-len(goals[x] - covered), -degree(x),
                                         x.casefold()))
        reach = goals.pop(best)
        new = len(reach - covered)
        if new < 2 or (hubs and new / size < MIN_NEW_REACH):
            break
        hubs.append(best)
        covered |= reach
    if hubs:
        return hubs

    scored = sorted((x for x in cluster if hub_score.get(x, 0) > 0 and allowed(x)),
                    key=lambda x: (-hub_score[x], x.casefold()))
    if scored:
        return scored[:MAX_HUBS]
    connected = sorted((x for x in cluster if allowed(x)),
                       key=lambda x: (-degree(x), x.casefold()))
    return connected[:2]


def label_communities(communities, nodes_by_name: Dict, edges,
                      hub_score: Optional[Dict[str, float]] = None) -> List[str]:
    """One label per community, in the order given."""
    hub_score = hub_score or {}
    members = set().union(*communities) if communities else set()
    neighbors, prereqs = _adjacency(edges, members)
    context_names = {n.context.casefold() for n in nodes_by_name.values() if n.context}

    labels = []
    for community in communities:
        cluster = {x for x in community if x in nodes_by_name}
        if not community:
            labels.append("Empty")
            continue
        if not cluster:
            labels.append("Unknown")
            continue
        if len(cluster) <= 2:
            labels.append(" + ".join(sorted(cluster, key=str.casefold)))
            continue
        nodes = [nodes_by_name[x] for x in cluster]
        prefix, top, hub_contexts = _prefix(nodes)
        # A hub named after a context is an umbrella Goal; it repeats the
        # prefix, or names some other area's cluster.
        avoid = set(context_names)
        if prefix and " > " in prefix:
            avoid.add(prefix.split(" > ", 1)[1].casefold())

        def allowed(x):
            return (x.casefold() not in avoid
                    and nodes_by_name[x].context in hub_contexts)

        hubs = _pick_hubs(cluster, nodes_by_name, neighbors, prereqs, allowed,
                          hub_score)

        def compose(names):
            body = " + ".join(names)
            if prefix and body:
                return f"{prefix}: {body}"
            return body or prefix or top or "Uncategorized"

        shown = hubs[:1]
        for hub in hubs[1:]:
            if len(compose(shown + [hub])) > MAX_LABEL_CHARS:
                break
            shown.append(hub)
        labels.append(compose(shown))

    # Hubs make labels unique; only a cluster with no usable hub could repeat
    # another's label.
    seen = Counter()
    for i, label in enumerate(labels):
        seen[label] += 1
        if seen[label] > 1:
            labels[i] = f"{label} #{seen[label]}"
    return labels


def build_listing(communities, labels, priority, fold_small=True) -> CommunityListing:
    """Rank the communities and split them into listed rows and Other.

    Importance is the summed priority score of a cluster's members: how much
    of the user's recommended work lives there. Clusters under
    MIN_LISTED_SIZE fold into Other when ``fold_small`` is set; Orphans mode
    clears it, since every orphan is a cluster of one.
    """
    def importance(i):
        return sum(max(0.0, priority.get(x, 0.0)) for x in communities[i])

    order = sorted(range(len(communities)),
                   key=lambda i: (-importance(i), -len(communities[i]),
                                  labels[i].casefold()))
    listing = CommunityListing()
    for i in order:
        small = fold_small and len(communities[i]) < MIN_LISTED_SIZE
        if not small and len(listing.listed) < MAX_LISTED:
            listing.listed.append((labels[i], set(communities[i])))
        else:
            listing.other |= communities[i]
            listing.other_clusters += 1
    return listing
