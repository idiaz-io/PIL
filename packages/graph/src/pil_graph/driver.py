"""The interface a real graph driver implements. PIL ships no live driver.

ADR-0011 resolves the language question this package was blocked on (PIL
stays Python) but keeps the scoping decision it was always going to have:
**a tenant-scoped query builder and this interface, never a live connection.**
Mirrors how :class:`pil_adapters.connection.ConnectionProvider` treats
adapters — the shape is PIL's, resolving it against something real (Neo4j,
Memgraph, an openCypher-portable engine not yet chosen, or AXO's own
``packages/itkg`` bridged some other way) is a consumer's job. Baking a live
driver into PIL here would assume an answer to ``[NEEDS-DECISION: ADR-17]``
(sovereign/air-gap vs. AWS) before that's settled.

Nothing in this module imports ``neo4j`` or any other graph-client library —
checked the same way ``tests/test_invariants.py`` already checks I-1 for
``contracts``/``adapters``, extended to this package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode

__all__ = ["GraphDriver"]


class GraphDriver(ABC):
    """Executes operations built in :mod:`pil_graph.operations`.

    Three typed methods, mirroring ``itkg.go``'s own ``Graph`` shape
    (``UpsertNode``, ``CountNodes``) rather than one generic ``execute`` —
    AXO's design didn't have a generic dispatch method either, and inventing
    one here would be reinventing rather than porting.

    Deliberately not ``async`` — the same reasoning
    :class:`pil_adapters.sink.Sink` and ``ConnectionProvider`` already give:
    nothing in this package does I/O, so colouring every caller a coroutine
    to satisfy an interface with no async implementation here would be
    premature. A real driver that needs it gets an async sibling and its own
    ADR, the same as a resolved credential handle would.
    """

    @abstractmethod
    def upsert_node(self, operation: UpsertNode) -> None:
        """Apply one :class:`~pil_graph.operations.UpsertNode`."""

    @abstractmethod
    def upsert_edge(self, operation: UpsertEdge) -> None:
        """Apply one :class:`~pil_graph.operations.UpsertEdge`."""

    @abstractmethod
    def count_nodes(self, operation: CountNodes) -> int:
        """Answer one :class:`~pil_graph.operations.CountNodes`."""
