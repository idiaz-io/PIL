"""ReferenceGate — one test per ADR-0013 decision-table row, plus extras."""

from __future__ import annotations

from datetime import timedelta
from itertools import product

import pytest

from pil_capabilities import CAPABILITIES, Capability, Risk
from pil_gate.gate import GRANT_SIGN, ReferenceGate
from pil_gate.request import Actor, BlastRadius, Breaker, GateRequest
from pil_gate.vocabulary import ActorKind, Decision, Tier

WRITE = Capability.SCRIPT_EXECUTE
READ = Capability.HOST_READ


def _actor(
    kind: ActorKind = ActorKind.HUMAN,
    permissions: frozenset[str] = frozenset(),
) -> Actor:
    return Actor(identity_ref="user:test-1", kind=kind, permissions=permissions)


def _request(
    *,
    capability: Capability = WRITE,
    actor: Actor | None = None,
    blast_radius: BlastRadius | None = None,
    breaker: Breaker | None = None,
) -> GateRequest:
    return GateRequest(
        tenant_id="tenant-acme",
        product="axo",
        capability=capability,
        actor=actor or _actor(),
        blast_radius=blast_radius,
        breaker=breaker,
    )


def _gate() -> ReferenceGate:
    return ReferenceGate(policy_version="console-v1", id_factory=lambda: "fixed")


def test_row_1_read_allows_observe_only() -> None:
    result = _gate().decide(_request(capability=READ))
    assert result.decision is Decision.ALLOW
    assert result.tier is Tier.OBSERVE_ONLY
    assert result.required_approvers == 0
    assert result.approval_ttl is None
    assert "read" in result.reason
    assert result.policy_version == "console-v1"
    assert result.decision_id == "fixed"


def test_row_1_tenants_crossed_denies() -> None:
    result = _gate().decide(
        _request(
            blast_radius=BlastRadius(
                tenants_crossed=2,
                mission_critical_downstream=0,
                max_depth_hit=False,
            )
        )
    )
    assert result.decision is Decision.DENY
    assert result.tier is Tier.BLOCKED_BY_DEFAULT
    assert result.required_approvers == 1
    assert result.approval_ttl is None
    assert "2" in result.reason


def test_row_3_tripped_breaker_holds() -> None:
    result = _gate().decide(_request(breaker=Breaker(class_rate_1h=4, tripped=True)))
    assert result.decision is Decision.HOLD
    assert result.tier is Tier.APPROVAL_REQUIRED
    assert result.required_approvers == 1
    assert result.approval_ttl == timedelta(hours=24)
    assert "breaker" in result.reason
    assert "4" in result.reason


def test_row_4_human_with_grant_sign_allows_approval_required() -> None:
    result = _gate().decide(_request(actor=_actor(permissions=frozenset({GRANT_SIGN}))))
    assert result.decision is Decision.ALLOW
    assert result.tier is Tier.APPROVAL_REQUIRED
    assert result.required_approvers == 1
    assert result.approval_ttl is None
    assert GRANT_SIGN in result.reason


def test_row_5_human_without_grant_sign_holds() -> None:
    result = _gate().decide(_request())
    assert result.decision is Decision.HOLD
    assert result.tier is Tier.APPROVAL_REQUIRED
    assert result.approval_ttl == timedelta(hours=24)
    assert GRANT_SIGN in result.reason
    assert "lacks" in result.reason


def test_row_5_service_actor_holds() -> None:
    result = _gate().decide(_request(actor=_actor(kind=ActorKind.SERVICE)))
    assert result.decision is Decision.HOLD
    assert result.tier is Tier.APPROVAL_REQUIRED
    assert "service actor" in result.reason


def test_service_actor_holding_grant_sign_still_holds() -> None:
    result = _gate().decide(
        _request(actor=_actor(kind=ActorKind.SERVICE, permissions=frozenset({GRANT_SIGN})))
    )
    assert result.decision is Decision.HOLD
    assert result.tier is Tier.APPROVAL_REQUIRED
    assert "service actor" in result.reason


def test_benign_blast_radius_does_not_change_outcome() -> None:
    benign = BlastRadius(tenants_crossed=0, mission_critical_downstream=0, max_depth_hit=False)
    without = _gate().decide(_request())
    with_benign = _gate().decide(_request(blast_radius=benign))
    assert without.decision is with_benign.decision is Decision.HOLD
    assert without.tier is with_benign.tier


def test_untripped_breaker_does_not_change_outcome() -> None:
    without = _gate().decide(_request())
    with_breaker = _gate().decide(_request(breaker=Breaker(class_rate_1h=1, tripped=False)))
    assert without.decision is with_breaker.decision is Decision.HOLD


def test_determinism_with_fixed_id_factory() -> None:
    gate = _gate()
    request = _request()
    first = gate.decide(request)
    second = gate.decide(request)
    assert first == second


def test_determinism_except_decision_id_with_default_factory() -> None:
    gate = ReferenceGate(policy_version="console-v1")
    request = _request()
    first = gate.decide(request)
    second = gate.decide(request)
    assert first.decision_id != second.decision_id
    assert first.decision is second.decision
    assert first.tier is second.tier
    assert first.reason == second.reason
    assert first.policy_version == second.policy_version


@pytest.mark.parametrize("capability", list(Capability))
def test_every_capability_gets_a_decision_without_raising(capability: Capability) -> None:
    result = _gate().decide(_request(capability=capability))
    assert result.capability is capability
    assert result.decision in Decision


@pytest.mark.parametrize(
    ("capability", "kind", "holds_sign"),
    list(product(list(Capability), list(ActorKind), [False, True])),
)
def test_reference_gate_never_produces_safe_auto_heal(
    capability: Capability, kind: ActorKind, holds_sign: bool
) -> None:
    permissions = frozenset({GRANT_SIGN}) if holds_sign else frozenset()
    result = _gate().decide(
        _request(capability=capability, actor=_actor(kind=kind, permissions=permissions))
    )
    assert result.tier is not Tier.SAFE_AUTO_HEAL
    if CAPABILITIES[capability].risk is Risk.READ:
        assert result.tier is Tier.OBSERVE_ONLY


def test_cross_tenant_read_is_denied() -> None:
    result = _gate().decide(
        _request(
            capability=READ,
            blast_radius=BlastRadius(
                tenants_crossed=1,
                mission_critical_downstream=0,
                max_depth_hit=False,
            ),
        )
    )
    assert result.decision is Decision.DENY
    assert result.tier is Tier.BLOCKED_BY_DEFAULT
    assert "tenants_crossed=1" in result.reason


@pytest.mark.parametrize(
    "capability",
    [c for c in Capability if CAPABILITIES[c].risk is Risk.READ],
)
def test_cross_tenant_deny_precedes_read_for_every_read_capability(
    capability: Capability,
) -> None:
    result = _gate().decide(
        _request(
            capability=capability,
            blast_radius=BlastRadius(
                tenants_crossed=1,
                mission_critical_downstream=0,
                max_depth_hit=False,
            ),
        )
    )
    assert result.decision is Decision.DENY
    assert result.tier is Tier.BLOCKED_BY_DEFAULT


def test_in_tenant_read_is_still_observe_only() -> None:
    result = _gate().decide(
        _request(
            capability=READ,
            blast_radius=BlastRadius(
                tenants_crossed=0,
                mission_critical_downstream=0,
                max_depth_hit=False,
            ),
        )
    )
    assert result.decision is Decision.ALLOW
    assert result.tier is Tier.OBSERVE_ONLY
    assert result.required_approvers == 0


def test_tripped_breaker_does_not_affect_a_read() -> None:
    result = _gate().decide(
        _request(
            capability=READ,
            blast_radius=BlastRadius(
                tenants_crossed=0,
                mission_critical_downstream=0,
                max_depth_hit=False,
            ),
            breaker=Breaker(class_rate_1h=9, tripped=True),
        )
    )
    assert result.decision is Decision.ALLOW
    assert result.tier is Tier.OBSERVE_ONLY


def test_cross_tenant_write_beats_a_human_signer() -> None:
    result = _gate().decide(
        _request(
            actor=_actor(permissions=frozenset({GRANT_SIGN})),
            blast_radius=BlastRadius(
                tenants_crossed=1,
                mission_critical_downstream=0,
                max_depth_hit=False,
            ),
        )
    )
    assert result.decision is Decision.DENY
    assert result.tier is Tier.BLOCKED_BY_DEFAULT
