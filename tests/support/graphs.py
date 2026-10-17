"""Small graphs for tests: a node, a graph of plain nodes, an editor save."""
from skilltree.domain.models import Node
from skilltree.store.commands import handle_save
from skilltree.store.graph.manager import GraphManager


def node(name, **kwargs):
    """A Learn node in Mind, rated 5 across, with fields overridden by ``kwargs``."""
    return Node(**dict(dict(name=name, type="Learn", description="original",
                           value=5, interest=5, difficulty=5, time_o=1,
                           time_m=2, time_p=4, context="Mind", status="Open"), **kwargs))


def graph(*names):
    """A GraphManager on the test's database, holding a plain node per name."""
    manager = GraphManager()
    for name in names:
        manager.add_node(node(name))
    return manager


def save(manager, name, **kwargs):
    """handle_save as the editor calls it, with fields overridden by ``kwargs``."""
    args = dict(name=name, n_type="Learn", desc="edited", val=5, time_o=1,
                time_m=2, time_p=4, interest=5, diff=5, status_done=[],
                context="Mind", subctx=None, resource_links=None,
                e_needs_h=[], e_needs_s=[], e_supp_h=[],
                e_supp_s=[], e_helps=[])
    args.update(kwargs)
    return handle_save(manager, **args)
