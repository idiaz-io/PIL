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
        """Apply one :class:`~pil_graph.operations.UpsertEdge`.

        **MUST raise** :class:`LookupError` **if either endpoint does not
        exist** for this operation's tenant. This does not happen for free.
        ``operation.to_cypher()`` produces ``MATCH (a) ... MERGE (a)-[r]->(b)``
        — if the ``MATCH`` finds no rows, Neo4j (and openCypher generally)
        does not raise: it returns zero rows, ``MERGE`` never runs, and the
        query completes successfully having done nothing. A driver that just
        executes the query and returns has silently dropped the edge, not
        failed loudly.

        The Cypher already gives an implementation the signal it needs:
        :meth:`~pil_graph.operations.UpsertEdge.to_cypher` ends with
        ``RETURN count(r) AS relationships_written``. Cypher's aggregation
        semantics mean this still returns exactly one row even when the
        ``MATCH`` found nothing — with the count at ``0`` — rather than
        producing zero result rows outright. Run the query, read that
        column, and raise ``LookupError`` when it is ``0``. "The query
        executed without error" is not evidence the edge was written; the
        count is.

        :class:`~pil_graph.fakes.InMemoryGraphDriver` raises this by
        checking its own node set before merging, which is why its tests
        cannot, by themselves, prove a real driver behaves the same way —
        that must be a driver-level integration test against a real engine.
        """

    @abstractmethod
    def count_nodes(self, operation: CountNodes) -> int:
        """Answer one :class:`~pil_graph.operations.CountNodes`."""
