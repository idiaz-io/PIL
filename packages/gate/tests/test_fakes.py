"""StaticGate — returns what it was given and records requests."""

from __future__ import annotations

from pil_capabilities import Capability
from pil_gate.fakes import StaticGate
from pil_gate.request import Actor, GateRequest
from pil_gate.vocabulary import ActorKind, Decision, Tier


def test_static_gate_returns_configured_decision_and_records() -> None:
    gate = StaticGate(decision=Decision.HOLD, tier=Tier.APPROVAL_REQUIRED)
    request = GateRequest(
        tenant_id="tenant-acme",
        product="axo",
        capability=Capability.SCRIPT_EXECUTE,
        actor=Actor(identity_ref="user:test-1", kind=ActorKind.HUMAN),
    )
    result = gate.decide(request)
    assert result.decision is Decision.HOLD
    assert result.tier is Tier.APPROVAL_REQUIRED
    assert result.policy_version == "static-test"
    assert result.reason == "static test double"
    assert result.decision_id == "static"
    assert gate.requests == [request]


def test_static_gate_can_return_deny() -> None:
    gate = StaticGate(
        decision=Decision.DENY,
        tier=Tier.BLOCKED_BY_DEFAULT,
        reason="configured deny",
    )
    result = gate.decide(
        GateRequest(
            tenant_id="tenant-acme",
            product="axo",
            capability=Capability.SCRIPT_EXECUTE,
            actor=Actor(identity_ref="user:test-1", kind=ActorKind.HUMAN),
        )
    )
    assert result.decision is Decision.DENY
    assert result.reason == "configured deny"
