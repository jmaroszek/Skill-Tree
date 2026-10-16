"""Names and ranks the clusters the Community filter lists.

A label says what a cluster is about. It is an optional context prefix, then
up to three hubs: the nodes the cluster is built around. Hubs are member
names, and a node belongs to one cluster, so labels come out unique.

Pure functions over plain data, so they test without a database.
`graph_queries.list_communities` gathers the inputs.
"""
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

from skilltree.domain.models import EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT
from skilltree.domain.models import EDGE_HELPS
from skilltree.domain.models import STATUS_DONE
import math

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
# The Community list shows this many clusters at most, and none under
# MIN_LISTED_SIZE. Unlisted clusters still show under "All"; grouping them in
# one row would put unrelated clusters on the canvas together. On a real
# graph, 1-2 node clusters are most of what a narrow filter produces, and the
# unfiltered graph has 17 clusters of three or more.
MAX_LISTED = 20
MIN_LISTED_SIZE = 3


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


def build_listing(communities, labels, priority,
                  skip_small=True) -> List[Tuple[str, Set[str]]]:
    """The Community filter's rows as (label, members), most important first.

    Importance is the summed priority score of a cluster's members: how much
    of the user's recommended work lives there. Clusters under
    MIN_LISTED_SIZE are left out when ``skip_small`` is set; Orphans mode
    clears it, since every orphan is a cluster of one.
    """
    def importance(i):
        return sum(max(0.0, priority.get(x, 0.0)) for x in communities[i])

    candidates = [i for i in range(len(communities))
                  if not (skip_small and len(communities[i]) < MIN_LISTED_SIZE)]
    candidates.sort(key=lambda i: (-importance(i), -len(communities[i]),
                                   labels[i].casefold()))
    return [(labels[i], set(communities[i])) for i in candidates[:MAX_LISTED]]


def hub_scores(nodes, edges):
    """Every unfinished work node's hub score, keyed by name —
    ``sqrt(in_count * out_count) + 0.5 * helps_count`` over Hard + Soft
    prereq edges, with Helps edges counted as symmetric synergy partners.

    Only Learn and Action prerequisites count as inputs, and Goals and
    Milestones are not ranked. A Goal's incoming edges are its members, so
    every umbrella Goal used to top the list; a Resource's edge into a topic
    measures the length of its reading list, not how central the topic is.

    The geometric mean punishes asymmetry (a pure root or pure leaf scores
    0 on the first term), so hubs are exactly the nodes with traffic in
    both directions — concepts that absorb prereqs AND feed dependents.
    The Helps term gives synergy partners half-weight credit on top.

    The community labels use it to name a cluster after its most central
    nodes. Each value is a row with the score components. Nodes scoring 0
    are left out."""
    node_map = {n.name: n for n in nodes}
    candidates = {n.name for n in nodes
                  if n.status != STATUS_DONE and n.type not in CONTAINER_TYPES}

    in_ct: dict = defaultdict(int)
    out_ct: dict = defaultdict(int)
    helps_ct: dict = defaultdict(int)

    for e in edges:
        s, t, etype = e['source'], e['target'], e['type']
        if etype in (EDGE_NEEDS_HARD, EDGE_NEEDS_SOFT):
            out_ct[s] += 1
            if s in node_map and node_map[s].type in CONCEPT_TYPES:
                in_ct[t] += 1
        elif etype == EDGE_HELPS:
            helps_ct[s] += 1
            helps_ct[t] += 1

    results = {}
    for name in candidates:
        i, o = in_ct[name], out_ct[name]
        h = helps_ct[name]
        score = math.sqrt(i * o) + 0.5 * h
        if score <= 0:
            continue
        n = node_map[name]
        results[name] = {
            'name': name,
            'score': score,
            'in_count': i,
            'out_count': o,
            'helps_count': h,
            'type': n.type,
            'status': n.status,
        }
    return results


# Goals are containers and Milestones are checkpoints. Neither is work, so the
# structure charts walk through them without ranking or counting them.
CONTAINER_TYPES = ('Goal', 'Milestone')


# Node types whose incoming edges count as a hub's inputs. A Resource linked to
# a topic is reading material for it, not a concept feeding into it.
CONCEPT_TYPES = ('Learn', 'Action')
