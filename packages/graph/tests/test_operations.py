"""Operation construction — mirrors AXO's ``TestUpsertRejectsLabelInjection``
and ``TestUpsertRequiresTenantAndID`` (``itkg_test.go``), extended to
:class:`~pil_graph.operations.UpsertEdge`, which ``itkg.go`` never had.

Tenant-scoping proofs live in ``test_graph_tenancy.py``, not here — this file is
about the closed-vocabulary/injection guard and the Cypher each operation
produces, not about cross-tenant isolation.
"""

from __future__ import annotations

import pytest

from pil_graph.operations import CountNodes, UpsertEdge, UpsertNode, uid
from pil_graph.vocabulary import EdgeType, NodeLabel

# ---------------------------------------------------------------------------
# uid()
# ---------------------------------------------------------------------------


def test_uid_format() -> None:
    assert uid("tenant-acme", "host-1") == "tenant-acme/host-1"


# ---------------------------------------------------------------------------
# UpsertNode
# ---------------------------------------------------------------------------


def test_upsert_node_rejects_label_injection() -> None:
    """Labels can't be parameterised in Cypher — this is the injection guard,
    same adversarial string AXO's own test uses."""
    with pytest.raises(ValueError, match="closed vocabulary"):
        UpsertNode(tenant_id="tenant-a", label="Asset) DETACH DELETE n //", id="x")  # type: ignore[arg-type]


def test_upsert_node_requires_tenant() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        UpsertNode(tenant_id="", label=NodeLabel.ASSET, id="x")


def test_upsert_node_requires_id() -> None:
    with pytest.raises(ValueError, match="id"):
        UpsertNode(tenant_id="t", label=NodeLabel.ASSET, id="")


def test_upsert_node_cypher_sets_tenant_and_id_after_props() -> None:
    """Server-authoritative ordering: SET n += $props runs, then tenant_id/id
    are set from the operation's own fields, so a props map can't smuggle a
    different tenant — same posture as itkg.go's UpsertNode."""
    op = UpsertNode(
        tenant_id="tenant-a", label=NodeLabel.ASSET, id="host-1", props={"tenant_id": "attacker"}
    )
    cypher, params = op.to_cypher()
    assert "MERGE (n:Asset {uid: $uid})" in cypher
    assert "n.tenant_id = $tenant" in cypher
    assert cypher.index("$props") < cypher.index("n.tenant_id = $tenant")
    assert params["tenant"] == "tenant-a"
    assert params["props"] == {
        "tenant_id": "attacker"
    }  # carried, but overwritten by the Cypher itself


# ---------------------------------------------------------------------------
# UpsertEdge
# ---------------------------------------------------------------------------


def test_upsert_edge_rejects_unknown_edge_type() -> None:
    with pytest.raises(ValueError, match="closed vocabulary"):
        UpsertEdge(
            tenant_id="t",
            edge_type="NOT_AN_EDGE",  # type: ignore[arg-type]
            from_label=NodeLabel.ASSET,
            from_id="a",
            to_label=NodeLabel.MISSION,
            to_id="b",
        )


def test_upsert_edge_rejects_unknown_from_label() -> None:
    with pytest.raises(ValueError, match="closed vocabulary"):
        UpsertEdge(
            tenant_id="t",
            edge_type=EdgeType.RUNS_ON,
            from_label="NotALabel",  # type: ignore[arg-type]
            from_id="a",
            to_label=NodeLabel.MISSION,
            to_id="b",
        )


def test_upsert_edge_rejects_unknown_to_label() -> None:
    with pytest.raises(ValueError, match="closed vocabulary"):
        UpsertEdge(
            tenant_id="t",
            edge_type=EdgeType.RUNS_ON,
            from_label=NodeLabel.ASSET,
            from_id="a",
            to_label="NotALabel",  # type: ignore[arg-type]
            to_id="b",
        )


@pytest.mark.parametrize("field_name", ["tenant_id", "from_id", "to_id"])
def test_upsert_edge_requires_every_id_field(field_name: str) -> None:
    kwargs = {
        "tenant_id": "t",
        "edge_type": EdgeType.RUNS_ON,
        "from_label": NodeLabel.ASSET,
        "from_id": "a",
        "to_label": NodeLabel.MISSION,
        "to_id": "b",
    }
    kwargs[field_name] = ""
    with pytest.raises(ValueError, match="required"):
        UpsertEdge(**kwargs)


def test_upsert_edge_cypher_matches_both_endpoints_before_merging() -> None:
    op = UpsertEdge(
        tenant_id="tenant-a",
        edge_type=EdgeType.RUNS_ON,
        from_label=NodeLabel.ASSET,
        from_id="host-1",
        to_label=NodeLabel.MISSION,
        to_id="mission-1",
    )
    cypher, params = op.to_cypher()
    assert "MATCH (a:Asset {uid: $from_uid}), (b:Mission {uid: $to_uid})" in cypher
    assert "MERGE (a)-[r:RUNS_ON]->(b)" in cypher
    assert params["from_uid"] == "tenant-a/host-1"
    assert params["to_uid"] == "tenant-a/mission-1"
    assert params["tenant"] == "tenant-a"


# ---------------------------------------------------------------------------
# CountNodes
# ---------------------------------------------------------------------------


def test_count_nodes_rejects_unknown_label() -> None:
    with pytest.raises(ValueError, match="closed vocabulary"):
        CountNodes(tenant_id="t", label="NotALabel")  # type: ignore[arg-type]


def test_count_nodes_requires_tenant() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        CountNodes(tenant_id="", label=NodeLabel.ASSET)


def test_count_nodes_cypher_filters_by_tenant() -> None:
    op = CountNodes(tenant_id="tenant-a", label=NodeLabel.ASSET)
    cypher, params = op.to_cypher()
    assert "MATCH (n:Asset {tenant_id: $tenant})" in cypher
    assert params == {"tenant": "tenant-a"}
