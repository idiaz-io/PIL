"""Envelope -> ITKG graph operations. Construction only, same posture
:mod:`pil_graph.operations` already takes: nothing here executes anything — a
:class:`~pil_graph.driver.GraphDriver` is what runs the operations :func:`project` returns.

Every alert PIL translates is the same distinct fact wherever it came from: a device
exists (or claims to), it belongs to a tenant, and this alert concerns it. That's the
whole justification surface a single translated ``Envelope`` provides, and it's exactly
what gets written — nothing more.

**Asset and Tenant are always written.** An unidentified device (``AlertBody.device_id``
falling back to a translator's missing-value sentinel) is real imprecision, accepted on
purpose (see ``identity.py``) — collapsing a tenant's unidentified devices from one source
onto a single node is a bounded, honest simplification, not a bug worth refusing over.

**Finding is written only when the alert has a real identity.** Unlike a device, an
unidentified *alert* has no safe fallback: two different alerts colliding onto the same
Finding node is not imprecision, it's data loss — the second write silently erases the
first. See :func:`~pil_graph_writer.identity.is_missing_alert_id` for why no synthetic
identity (timestamp, content hash) closes this safely. When ``alert_id`` is the known
sentinel, only the Asset/Tenant write happens; the alert itself is not represented.

**Deliberately thin.** ``Asset``'s ``type``/``state``/``os_version``/``criticality_score``/
``rto_minutes``/``rpo_minutes`` and ``Finding``'s ``owner_ref``/``sla_due`` are all absent
here — nothing in a translated alert supplies them, and inventing values would be
fabricating data no translator actually produced. ``Finding.status`` is the one lifecycle
field set here, to the literal value ``"open"`` — the honest, accurate description of a
freshly-arrived, unactioned alert, not a guess. Everything past that (triage, remediation,
verification) is a later WRITEBACK-stage concern this module has no information about.

**``external_ids`` is a JSON-encoded string, not a native map.** §6.1 describes it
conceptually as "a map of source-system keys" — Neo4j's own property-value rules don't
allow that literally: a node or relationship property must be a primitive or an array of
primitives, never a nested map. `InMemoryGraphDriver`'s tests never caught this (it just
stores whatever Python object it's handed); a real Neo4j run did, immediately, with
``Neo.ClientError.Statement.TypeError``. Encoding as JSON keeps the key-value structure
round-trippable (``json.loads`` gets the map back) while being a valid scalar to store.
"""

from __future__ import annotations

import json

from pil_contracts import Envelope, format_timestamp
from pil_graph import EdgeType, NodeLabel, UpsertEdge, UpsertNode
from pil_graph_writer.identity import is_missing_alert_id, node_id_for

__all__ = ["project"]


def project(envelope: Envelope) -> list[UpsertNode | UpsertEdge]:
    """Every graph operation one translated alert justifies. Construction only."""
    tenant_id = envelope.tenant_id
    source = envelope.source
    body = envelope.body

    tenant_props: dict[str, object] = {"name": envelope.tenant_hint.tenant_name or ""}
    if envelope.tenant_hint.tenant_id:
        # Evidence, not identity (I-5) -- what the payload claimed, kept as a property on
        # the node itself rather than trusted for anything.
        hint = {"hint_tenant_id": envelope.tenant_hint.tenant_id}
        tenant_props["external_ids"] = json.dumps(hint)

    asset_id = node_id_for(source, body.device_id)
    asset_props = {
        "hostname": body.device_name,
        "source": source,
        "adapter_version_seen": envelope.adapter_version,
        "last_seen_at": format_timestamp(envelope.observed_at),
        "external_ids": json.dumps({f"{source}_device_id": body.device_id}),
    }

    ops: list[UpsertNode | UpsertEdge] = [
        UpsertNode(tenant_id=tenant_id, label=NodeLabel.TENANT, id=tenant_id, props=tenant_props),
        UpsertNode(tenant_id=tenant_id, label=NodeLabel.ASSET, id=asset_id, props=asset_props),
        UpsertEdge(
            tenant_id=tenant_id,
            edge_type=EdgeType.BELONGS_TO_TENANT,
            from_label=NodeLabel.ASSET,
            from_id=asset_id,
            to_label=NodeLabel.TENANT,
            to_id=tenant_id,
        ),
    ]

    if is_missing_alert_id(body.alert_id):
        return ops

    finding_id = node_id_for(source, body.alert_id)
    finding_props = {
        "severity": body.severity,
        "type": body.category,
        "message": body.message,
        "status": "open",
        "compound": False,
        "external_ids": json.dumps({f"{source}_alert_id": body.alert_id}),
    }
    ops.append(
        UpsertNode(tenant_id=tenant_id, label=NodeLabel.FINDING, id=finding_id, props=finding_props)
    )
    ops.append(
        UpsertEdge(
            tenant_id=tenant_id,
            edge_type=EdgeType.BELONGS_TO_TENANT,
            from_label=NodeLabel.FINDING,
            from_id=finding_id,
            to_label=NodeLabel.TENANT,
            to_id=tenant_id,
        )
    )
    ops.append(
        UpsertEdge(
            tenant_id=tenant_id,
            edge_type=EdgeType.IMPACTS,
            from_label=NodeLabel.FINDING,
            from_id=finding_id,
            to_label=NodeLabel.ASSET,
            to_id=asset_id,
        )
    )
    return ops
