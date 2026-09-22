"""Cross-tenant isolation — the exit criterion for this package.

Mirrors the two-part proof ``tests/test_invariants.py`` already builds for
adapters: a **structural** check (there is nowhere to put a second tenant,
so the mistake can't be constructed) plus a **behavioural** check (running
real operations for two tenants through the same driver never crosses them).
Kept in its own file rather than folded into ``test_operations.py`` — this is
what makes "PIL owns the ITKG interface" a checkable claim, not an
architectural intention.

AXO's own version of the behavioural half runs in CI (`itkg-leak`) against a
real Neo4j. This package ships no live driver, so the behavioural proof here
runs against :class:`~pil_graph.fakes.InMemoryGraphDriver` instead — cheap,
no external dependency, runs in every CI job. It is not, by itself, proof a
real driver behaves the same way; ``tests/test_graph_neo4j_integration.py``
is that proof, against a real Neo4j, gated on a local instance being up
(``make neo4j-up``) since CI has none. Both exist on purpose: this file for
routine coverage, that one for the claim the fake alone cannot make.
"""

from __future__ import annotations

import pytest

from pil_graph.fakes import InMemoryGraphDriver
from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode
from pil_graph.vocabulary import EdgeType, NodeLabel

# ---------------------------------------------------------------------------
# Structural: no operation can name two tenants.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [UpsertNode, UpsertEdge, CountNodes])
def test_no_operation_has_a_second_tenant_field(cls: type) -> None:
    """Mirrors tests/test_invariants.py's test_translation_has_no_tenant_field:
    UpsertEdge references two nodes but must have exactly one tenant_id field
    between them — there is nowhere to express "from tenant A to tenant B"."""
    fields = set(cls.__dataclass_fields__)
    tenant_fields = {f for f in fields if "tenant" in f}
    assert tenant_fields == {"tenant_id"}, (
        f"{cls.__name__} must carry exactly one tenant field — an edge that could "
        "name a second tenant would be constructable, which defeats the point"
    )


@pytest.mark.parametrize(
    "blank_kwargs",
    [
        {"tenant_id": "", "label": NodeLabel.ASSET, "id": "x"},
        {"tenant_id": "   ", "label": NodeLabel.ASSET, "id": "x"},
    ],
)
def test_upsert_node_cannot_be_built_unscoped(blank_kwargs: dict) -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        UpsertNode(**blank_kwargs)


def test_count_nodes_cannot_be_built_unscoped() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        CountNodes(tenant_id="", label=NodeLabel.ASSET)


def test_upsert_edge_cannot_be_built_unscoped() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        UpsertEdge(
            tenant_id="",
            edge_type=EdgeType.RUNS_ON,
            from_label=NodeLabel.ASSET,
            from_id="a",
            to_label=NodeLabel.MISSION,
            to_id="b",
        )


# ---------------------------------------------------------------------------
# Behavioural: running real operations for two tenants never crosses them.
# ---------------------------------------------------------------------------


def test_count_nodes_never_sees_another_tenants_upserts() -> None:
    driver = InMemoryGraphDriver()
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-2"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-b", label=NodeLabel.ASSET, id="host-1"))

    count_a = driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET))
    count_b = driver.count_nodes(CountNodes(tenant_id="tenant-b", label=NodeLabel.ASSET))

    assert count_a == 2, "tenant-a's own two nodes"
    assert count_b == 1, "tenant-b's own one node — not tenant-a's two"


def test_same_id_under_two_tenants_does_not_collide() -> None:
    """tenant-a's 'host-1' and tenant-b's 'host-1' are different nodes — the
    uid() key is tenant-scoped, so an id colliding across tenants must not
    collapse into one row."""
    driver = InMemoryGraphDriver()
    driver.upsert_node(
        UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1", props={"owner": "a"})
    )
    driver.upsert_node(
        UpsertNode(tenant_id="tenant-b", label=NodeLabel.ASSET, id="host-1", props={"owner": "b"})
    )

    assert driver.count_nodes(CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET)) == 1
    assert driver.count_nodes(CountNodes(tenant_id="tenant-b", label=NodeLabel.ASSET)) == 1
    assert driver._nodes["tenant-a/host-1"]["owner"] == "a"
    assert driver._nodes["tenant-b/host-1"]["owner"] == "b"


def test_edge_upsert_is_confined_to_its_own_tenants_nodes() -> None:
    """An edge naming an id that exists only under a different tenant must
    fail, not silently attach to the wrong tenant's node — the fake's
    MATCH-before-MERGE semantics, mirroring a real driver's."""
    driver = InMemoryGraphDriver()
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-b", label=NodeLabel.MISSION, id="mission-1"))

    # host-1 belongs to tenant-a; mission-1 belongs to tenant-b. An edge
    # claimed under tenant-a naming mission-1 must not find tenant-b's node.
    with pytest.raises(LookupError):
        driver.upsert_edge(
            UpsertEdge(
                tenant_id="tenant-a",
                edge_type=EdgeType.RUNS_ON,
                from_label=NodeLabel.ASSET,
                from_id="host-1",
                to_label=NodeLabel.MISSION,
                to_id="mission-1",
            )
        )


def test_edges_are_scoped_per_tenant() -> None:
    driver = InMemoryGraphDriver()
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-a", label=NodeLabel.MISSION, id="mission-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-b", label=NodeLabel.ASSET, id="host-1"))
    driver.upsert_node(UpsertNode(tenant_id="tenant-b", label=NodeLabel.MISSION, id="mission-1"))

    driver.upsert_edge(
        UpsertEdge(
            tenant_id="tenant-a",
            edge_type=EdgeType.RUNS_ON,
            from_label=NodeLabel.ASSET,
            from_id="host-1",
            to_label=NodeLabel.MISSION,
            to_id="mission-1",
        )
    )

    assert len(driver.edges_for_tenant("tenant-a")) == 1
    assert len(driver.edges_for_tenant("tenant-b")) == 0
