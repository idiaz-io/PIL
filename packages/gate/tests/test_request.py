"""GateRequest construction — blank tenant rejected; no caller-supplied tier."""

from __future__ import annotations

import pytest

from pil_capabilities import Capability
from pil_gate.request import Actor, BlastRadius, Breaker, GateRequest
from pil_gate.vocabulary import ActorKind


def _actor() -> Actor:
    return Actor(identity_ref="user:test-1", kind=ActorKind.HUMAN)


def test_blank_tenant_id_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        GateRequest(
            tenant_id="",
            product="axo",
            capability=Capability.HOST_READ,
            actor=_actor(),
        )


def test_whitespace_tenant_id_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        GateRequest(
            tenant_id="   ",
            product="axo",
            capability=Capability.HOST_READ,
            actor=_actor(),
        )


def test_blank_product_rejected() -> None:
    with pytest.raises(ValueError, match="product"):
        GateRequest(
            tenant_id="tenant-acme",
            product="",
            capability=Capability.HOST_READ,
            actor=_actor(),
        )


def test_gate_request_has_no_tier_or_decision_field() -> None:
    fields = set(GateRequest.__dataclass_fields__)
    assert "tier" not in fields
    assert "decision" not in fields
    assert "pre_approved" not in fields


def test_gate_request_is_frozen() -> None:
    request = GateRequest(
        tenant_id="tenant-acme",
        product="axo",
        capability=Capability.HOST_READ,
        actor=_actor(),
    )
    with pytest.raises(AttributeError):
        request.tenant_id = "other"  # type: ignore[misc]


def test_blast_radius_and_breaker_default_to_none() -> None:
    request = GateRequest(
        tenant_id="tenant-acme",
        product="axo",
        capability=Capability.HOST_READ,
        actor=_actor(),
    )
    assert request.blast_radius is None
    assert request.breaker is None
    assert request.target_ref is None


def test_blast_radius_and_breaker_are_optional_typed_values() -> None:
    request = GateRequest(
        tenant_id="tenant-acme",
        product="axo",
        capability=Capability.SCRIPT_EXECUTE,
        actor=_actor(),
        blast_radius=BlastRadius(
            tenants_crossed=0,
            mission_critical_downstream=0,
            max_depth_hit=False,
        ),
        breaker=Breaker(class_rate_1h=1, tripped=False),
    )
    assert request.blast_radius is not None
    assert request.breaker is not None
