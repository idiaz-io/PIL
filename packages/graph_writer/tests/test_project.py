"""project() -- construction only, checked against the operations it returns, never
against a live driver.

That gap is real, not just tidy scoping: a manual run against a real Neo4j (2026-09-29)
caught a bug these tests didn't -- external_ids was a native Python dict, which is not a
legal Neo4j property value (a node/relationship property must be a primitive or an array
of primitives). Fixed by JSON-encoding it; test_external_ids_is_a_json_string below pins
the fix. Nothing here replaces an actual driver run -- see
tests/test_graph_neo4j_integration.py for that proof, and ask before assuming a
property's Python shape is also a legal stored shape.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from pil_contracts import AlertBody, Envelope, TenantHint
from pil_graph import EdgeType, NodeLabel, UpsertEdge, UpsertNode
from pil_graph.fakes import InMemoryGraphDriver
from pil_graph_writer import project

WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def envelope(
    *,
    alert_id="alert-1",
    device_id="dev-1",
    device_name="db01",
    severity="P2",
    category="disk",
    message="disk full",
    source="fleet",
    tenant_id="tenant-acme",
    tenant_hint=None,
) -> Envelope:
    return Envelope(
        event_id=alert_id,
        tenant_id=tenant_id,
        source=source,
        adapter_version="1.0.0",
        occurred_at=WHEN,
        observed_at=WHEN,
        body=AlertBody(
            alert_id=alert_id,
            device_id=device_id,
            device_name=device_name,
            severity=severity,
            category=category,
            message=message,
        ),
        tenant_hint=tenant_hint if tenant_hint is not None else TenantHint(),
    )


def nodes(ops):
    return [op for op in ops if isinstance(op, UpsertNode)]


def edges(ops):
    return [op for op in ops if isinstance(op, UpsertEdge)]


def test_happy_path_writes_tenant_asset_finding_and_all_three_edges():
    ops = project(envelope())

    labels = {n.label for n in nodes(ops)}
    assert labels == {NodeLabel.TENANT, NodeLabel.ASSET, NodeLabel.FINDING}

    edge_types = [(e.edge_type, e.from_label, e.to_label) for e in edges(ops)]
    assert (EdgeType.BELONGS_TO_TENANT, NodeLabel.ASSET, NodeLabel.TENANT) in edge_types
    assert (EdgeType.BELONGS_TO_TENANT, NodeLabel.FINDING, NodeLabel.TENANT) in edge_types
    assert (EdgeType.IMPACTS, NodeLabel.FINDING, NodeLabel.ASSET) in edge_types
    assert len(edges(ops)) == 3


def test_all_operations_carry_the_envelopes_tenant():
    ops = project(envelope(tenant_id="tenant-acme"))
    assert all(op.tenant_id == "tenant-acme" for op in ops)


def test_asset_id_is_source_scoped():
    ops = project(envelope(source="fleet", device_id="uuid-123"))
    asset = next(n for n in nodes(ops) if n.label == NodeLabel.ASSET)
    assert asset.id == "fleet:uuid-123"


def test_finding_id_is_source_scoped():
    ops = project(envelope(source="connectwise", alert_id="98765"))
    finding = next(n for n in nodes(ops) if n.label == NodeLabel.FINDING)
    assert finding.id == "connectwise:98765"


def test_finding_status_defaults_to_open_not_fabricated_further():
    ops = project(envelope())
    finding = next(n for n in nodes(ops) if n.label == NodeLabel.FINDING)
    assert finding.props["status"] == "open"
    assert finding.props["compound"] is False
    assert "owner_ref" not in finding.props
    assert "sla_due" not in finding.props


def test_asset_has_no_fabricated_properties():
    ops = project(envelope())
    asset = next(n for n in nodes(ops) if n.label == NodeLabel.ASSET)
    absent_fields = (
        "type",
        "state",
        "os_version",
        "criticality_score",
        "rto_minutes",
        "rpo_minutes",
    )
    for absent in absent_fields:
        assert absent not in asset.props
        assert absent not in asset.create_only_props


def test_asset_splits_stable_facts_from_freshness_facts():
    """hostname/source/external_ids describe which device this is and don't change
    across writes to the same node (asset_id already embeds source) -- write-once.
    last_seen_at/adapter_version_seen are about the most recent observation --
    always-set, the same way Tenant.name is write-once but for the opposite reason."""
    ops = project(envelope())
    asset = next(n for n in nodes(ops) if n.label == NodeLabel.ASSET)
    assert set(asset.create_only_props) == {"hostname", "source", "external_ids"}
    assert set(asset.props) == {"adapter_version_seen", "last_seen_at"}


@pytest.mark.parametrize("missing_alert_id", ["unknown"])
def test_missing_alert_id_skips_the_finding_entirely(missing_alert_id):
    ops = project(envelope(alert_id=missing_alert_id))

    labels = {n.label for n in nodes(ops)}
    assert labels == {NodeLabel.TENANT, NodeLabel.ASSET}
    assert not any(e.edge_type == EdgeType.IMPACTS for e in edges(ops))
    assert len(edges(ops)) == 1  # only Asset -> Tenant


def test_missing_device_id_still_writes_an_asset_imprecision_is_accepted():
    """Unlike a missing alert_id, a missing device_id does not suppress anything -- an
    unidentified device still gets an Asset node, source-scoped, per the approved design:
    collapsing unidentified devices from one source is accepted imprecision, not refused."""
    ops = project(envelope(device_id="unknown", source="sciencelogic"))

    asset = next(n for n in nodes(ops) if n.label == NodeLabel.ASSET)
    assert asset.id == "sciencelogic:unknown"
    labels = {n.label for n in nodes(ops)}
    assert NodeLabel.FINDING in labels  # alert_id here is still real


def test_tenant_hint_recorded_as_evidence_not_identity():
    ops = project(envelope(tenant_hint=TenantHint(tenant_id="cust-42", tenant_name="Acme")))
    tenant = next(n for n in nodes(ops) if n.label == NodeLabel.TENANT)
    assert tenant.create_only_props["name"] == "Acme"
    assert json.loads(tenant.create_only_props["external_ids"]) == {"hint_tenant_id": "cust-42"}
    # The graph identity is still the configured tenant, never the hint (I-5).
    assert tenant.id == "tenant-acme"


def test_external_ids_is_a_json_string_not_a_native_map():
    """Neo4j property values must be primitives or arrays of primitives -- a nested map
    is not legal and fails at write time (Neo.ClientError.Statement.TypeError), a real
    driver caught this, InMemoryGraphDriver's own tests never could."""
    ops = project(envelope())
    for node in nodes(ops):
        for props in (node.props, node.create_only_props):
            if "external_ids" in props:
                assert isinstance(props["external_ids"], str)
                json.loads(props["external_ids"])  # must round-trip


def test_no_tenant_hint_leaves_name_blank_not_invented():
    ops = project(envelope(tenant_hint=TenantHint()))
    tenant = next(n for n in nodes(ops) if n.label == NodeLabel.TENANT)
    assert tenant.create_only_props["name"] == ""
    assert "external_ids" not in tenant.create_only_props


def test_tenant_name_is_write_once_the_first_alerts_name_survives():
    """Pins the user-reported bug: Tenant.name used to flip with ingestion order,
    since every alert issued an unconditional SET. Two alerts for the same tenant
    with different hints -- the first alert's name must survive the second."""
    driver = InMemoryGraphDriver()
    first = envelope(tenant_hint=TenantHint(tenant_name="first-name"))
    second = envelope(tenant_hint=TenantHint(tenant_name="second-name-should-not-win"))

    for op in project(first):
        if isinstance(op, UpsertNode):
            driver.upsert_node(op)
        else:
            driver.upsert_edge(op)
    for op in project(second):
        if isinstance(op, UpsertNode):
            driver.upsert_node(op)
        else:
            driver.upsert_edge(op)

    assert driver._nodes["tenant-acme/tenant-acme"]["name"] == "first-name"
