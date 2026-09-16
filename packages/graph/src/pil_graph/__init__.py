"""pil_graph — the tenant-scoped ITKG query builder and driver interface.

Ships no live graph driver (ADR-0011): a query is described here — the
closed vocabulary, tenant-scoped operations, an interface a real
implementation satisfies — never executed here. Ported from AXO's
``packages/itkg`` (``idiaz-io/Axo``, ``merp-integration``, PR #47): same
vocabulary, same tenancy-by-construction posture, same openCypher-portability
constraint, rewritten in Python rather than reinvented.
"""

from pil_graph.driver import GraphDriver
from pil_graph.fakes import InMemoryGraphDriver
from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode, uid
from pil_graph.vocabulary import EDGE_TYPE_COUNT, NODE_LABEL_COUNT, EdgeType, NodeLabel

__all__ = [
    "EDGE_TYPE_COUNT",
    "NODE_LABEL_COUNT",
    "CountNodes",
    "EdgeType",
    "GraphDriver",
    "InMemoryGraphDriver",
    "NodeLabel",
    "UpsertEdge",
    "UpsertNode",
    "uid",
]
