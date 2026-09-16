"""An in-memory :class:`~pil_graph.driver.GraphDriver`, for tests.

Not a port — ``itkg.go`` has no fake driver of its own, because AXO always
runs against a real Neo4j (its CI's ``itkg-leak`` job exercises the graph
cross-tenant leak test against ``neo4j:5``). PIL ships no live driver at all
(ADR-0011), so it needs a default test double the way every other interface
in this repo already gets one — mirrors
:class:`pil_adapters.connection.StaticConnectionProvider` and
:class:`pil_adapters.sink.CollectingSink`: ship it here once, so a future
consumer of :class:`~pil_graph.driver.GraphDriver` does not each write their
own and drift, which is exactly the failure mode the report-only section of
IDI-195 warned about.

Operates on the structured operation directly — ``tenant_id``, ``label``,
``props`` — not on the Cypher text :meth:`~pil_graph.operations.UpsertNode.to_cypher`
produces. There is no Cypher interpreter here; a real driver is what turns
that text into an actual query.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pil_graph.driver import GraphDriver
from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode, uid
from pil_graph.vocabulary import NodeLabel

__all__ = ["InMemoryGraphDriver"]


@dataclass(slots=True)
class InMemoryGraphDriver(GraphDriver):
    """Holds nodes and edges in plain dicts/lists, keyed the same way
    ``itkg.go`` keys a real graph — by :func:`~pil_graph.operations.uid`."""

    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _edges: list[UpsertEdge] = field(default_factory=list)

    def upsert_node(self, operation: UpsertNode) -> None:
        key = uid(operation.tenant_id, operation.id)
        merged: dict[str, Any] = dict(operation.props)
        merged["tenant_id"] = operation.tenant_id
        merged["id"] = operation.id
        merged["label"] = operation.label
        self._nodes[key] = merged

    def upsert_edge(self, operation: UpsertEdge) -> None:
        # Mirrors itkg.go's own MATCH-before-MERGE semantics: an edge to a
        # node this driver has never seen is not silently created.
        from_key = uid(operation.tenant_id, operation.from_id)
        to_key = uid(operation.tenant_id, operation.to_id)
        if from_key not in self._nodes or to_key not in self._nodes:
            raise LookupError(
                f"upsert_edge: endpoint not found for tenant {operation.tenant_id!r} "
                f"(from={operation.from_id!r}, to={operation.to_id!r}) — MERGE has "
                "nothing to match, the same as a real driver's MATCH clause finding "
                "no rows"
            )
        self._edges.append(operation)

    def count_nodes(self, operation: CountNodes) -> int:
        return sum(
            1
            for props in self._nodes.values()
            if props["tenant_id"] == operation.tenant_id and props["label"] == operation.label
        )

    def edges_for_tenant(self, tenant_id: str) -> list[UpsertEdge]:
        """Not part of :class:`~pil_graph.driver.GraphDriver` — a test-only
        accessor, the same role ``itkg.go``'s own ``wipeAll`` plays: useful
        for assertions, not part of the tenant-scoped surface."""
        return [e for e in self._edges if e.tenant_id == tenant_id]

    def node_labels_seen(self, tenant_id: str) -> set[NodeLabel]:
        """Test-only accessor, same reasoning as :meth:`edges_for_tenant`."""
        return {props["label"] for props in self._nodes.values() if props["tenant_id"] == tenant_id}
