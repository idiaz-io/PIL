"""Tenant-scoped operations over the ITKG. Construction, not execution.

Ported from AXO's ``packages/itkg/itkg.go`` (``UpsertNode``, ``CountNodes``) —
same tenancy-by-construction posture, same openCypher text, same injection
guard. What's different by design: these dataclasses *describe* an operation
(Cypher text plus parameters) rather than running one — :mod:`pil_graph.driver`
is what executes them, and PIL ships no live driver (ADR-0011). ``itkg.go``
fuses construction and execution into one method per operation; this package
splits them because the execution half is exactly the part that varies by
consumer (Neo4j today, Memgraph or AGE later, an in-memory fake for tests).

**Tenancy is enforced the same way ``pil_adapters.base.Translation`` enforces
it for adapters**: every operation below requires ``tenant_id`` with no
default anywhere, so an operation cannot be constructed unscoped even by
accident. :class:`UpsertEdge` in particular carries exactly one ``tenant_id``
for both endpoints — there is nowhere to put a second one, so an edge
crossing tenants is not an expressible operation, structurally, not merely a
validated one.

**Labels and edge types can't be parameterised in Cypher** — only values can
— which is exactly the injection surface AXO's own
``TestUpsertRejectsLabelInjection`` exists to close. Every operation below
validates its label(s)/edge type against the closed vocabulary in
``__post_init__``, before any Cypher text is built, never deferred to
whatever driver eventually runs it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pil_graph.vocabulary import EdgeType, NodeLabel

__all__ = ["CountNodes", "UpsertEdge", "UpsertNode", "uid"]


def uid(tenant_id: str, node_id: str) -> str:
    """The synthetic uniqueness key ``itkg.go`` MERGEs nodes on: ``"<tenant>/<id>"``.

    Community-safe single-property uniqueness (ADR-0007, AXO side) rather
    than a composite/existence constraint, which is Neo4j Enterprise-only.
    Exposed here, not hidden inside a driver, because any real driver needs
    the identical key to MERGE against the same constraint AXO's schema
    already installs.
    """
    return f"{tenant_id}/{node_id}"


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} is required and may not be blank")


def _validate_node_label(label: NodeLabel) -> NodeLabel:
    try:
        return NodeLabel(label)
    except ValueError:
        raise ValueError(
            f"unknown node label {label!r} (closed vocabulary) — labels cannot be "
            "parameterised in Cypher, so this is validated before any query text "
            "is built, not deferred to a driver"
        ) from None


def _validate_edge_type(edge: EdgeType) -> EdgeType:
    try:
        return EdgeType(edge)
    except ValueError:
        raise ValueError(
            f"unknown edge type {edge!r} (closed vocabulary) — relationship types "
            "cannot be parameterised in Cypher either"
        ) from None


@dataclass(frozen=True, slots=True)
class UpsertNode:
    """MERGE a node under the caller's tenant.

    ``tenant_id`` and ``id`` are set server-authoritatively — the Cypher this
    produces applies ``props`` first, then overwrites ``tenant_id``/``id``
    from the operation's own fields, so a props mapping that tries to smuggle
    a different tenant cannot win. Same posture as ``itkg.go``'s ``UpsertNode``.
    """

    tenant_id: str
    label: NodeLabel
    id: str
    props: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(self.tenant_id, "tenant_id")
        _require(self.id, "id")
        object.__setattr__(self, "label", _validate_node_label(self.label))

    def to_cypher(self) -> tuple[str, dict[str, Any]]:
        """The Cypher a driver runs, and its parameters. openCypher-portable —
        no APOC/GDS/Enterprise-only construct, same constraint ``itkg.go`` holds
        itself to (ADR-0007)."""
        cypher = (
            f"MERGE (n:{self.label.value} {{uid: $uid}}) "
            "SET n += $props, n.tenant_id = $tenant, n.id = $id"
        )
        params = {
            "uid": uid(self.tenant_id, self.id),
            "props": dict(self.props),
            "tenant": self.tenant_id,
            "id": self.id,
        }
        return cypher, params


@dataclass(frozen=True, slots=True)
class UpsertEdge:
    """MERGE a relationship of a closed edge type between two nodes the
    caller's tenant owns.

    Not present in ``itkg.go`` — that file defines all 13 edge types in its
    vocabulary but never writes one, leaving them defined and unusable. Added
    here for the same reason the vocabulary names them: a closed set of edge
    types nothing can create is not a query library, it's half of one.

    Both endpoints are referenced by ``(label, id)`` and resolved against
    **one** ``tenant_id`` shared by the whole operation — there is no second
    tenant field for the "other side" of the edge, so this cannot express an
    edge that crosses tenants. That is a structural property, provable by
    inspecting the dataclass's own fields (see ``tests/test_graph_tenancy.py``), not
    merely something validated at construction time.
    """

    tenant_id: str
    edge_type: EdgeType
    from_label: NodeLabel
    from_id: str
    to_label: NodeLabel
    to_id: str
    props: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require(self.tenant_id, "tenant_id")
        _require(self.from_id, "from_id")
        _require(self.to_id, "to_id")
        object.__setattr__(self, "edge_type", _validate_edge_type(self.edge_type))
        object.__setattr__(self, "from_label", _validate_node_label(self.from_label))
        object.__setattr__(self, "to_label", _validate_node_label(self.to_label))

    def to_cypher(self) -> tuple[str, dict[str, Any]]:
        """Matches both endpoints by their tenant-scoped ``uid`` before MERGE-ing
        the relationship — an edge cannot be created to a node the MATCH doesn't
        find, and the MATCH is scoped to this operation's one tenant."""
        cypher = (
            f"MATCH (a:{self.from_label.value} {{uid: $from_uid}}), "
            f"(b:{self.to_label.value} {{uid: $to_uid}}) "
            f"MERGE (a)-[r:{self.edge_type.value}]->(b) "
            "SET r += $props, r.tenant_id = $tenant"
        )
        params = {
            "from_uid": uid(self.tenant_id, self.from_id),
            "to_uid": uid(self.tenant_id, self.to_id),
            "props": dict(self.props),
            "tenant": self.tenant_id,
        }
        return cypher, params


@dataclass(frozen=True, slots=True)
class CountNodes:
    """How many nodes of a label the caller's tenant can see.

    Filters on ``{tenant_id: $tenant}`` — there is no operation in this
    module that can return another tenant's nodes. Mirrors ``itkg.go``'s
    ``CountNodes``, which the graph-layer cross-tenant leak test in AXO's own
    CI is built against.
    """

    tenant_id: str
    label: NodeLabel

    def __post_init__(self) -> None:
        _require(self.tenant_id, "tenant_id")
        object.__setattr__(self, "label", _validate_node_label(self.label))

    def to_cypher(self) -> tuple[str, dict[str, Any]]:
        cypher = f"MATCH (n:{self.label.value} {{tenant_id: $tenant}}) RETURN count(n) AS c"
        return cypher, {"tenant": self.tenant_id}
