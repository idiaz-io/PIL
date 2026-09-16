"""GateDecision construction and to_record()."""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from pil_capabilities import Capability
from pil_gate.decision import GateDecision
from pil_gate.vocabulary import Decision, Tier


def _decision(**overrides: object) -> GateDecision:
    values: dict[str, object] = {
        "decision_id": "dec-1",
        "tenant_id": "tenant-acme",
        "product": "axo",
        "capability": Capability.SCRIPT_EXECUTE,
        "decision": Decision.ALLOW,
        "tier": Tier.APPROVAL_REQUIRED,
        "policy_version": "console-v1",
        "required_approvers": 1,
        "approval_ttl": None,
        "reason": "signed",
    }
    values.update(overrides)
    return GateDecision(**values)  # type: ignore[arg-type]


def test_deny_without_reason_is_unconstructible() -> None:
    with pytest.raises(ValueError, match="deny requires a reason"):
        _decision(decision=Decision.DENY, tier=Tier.BLOCKED_BY_DEFAULT, reason="")


def test_deny_with_whitespace_reason_is_unconstructible() -> None:
    with pytest.raises(ValueError, match="deny requires a reason"):
        _decision(decision=Decision.DENY, tier=Tier.BLOCKED_BY_DEFAULT, reason="   ")


def test_deny_with_reason_constructs() -> None:
    decision = _decision(
        decision=Decision.DENY,
        tier=Tier.BLOCKED_BY_DEFAULT,
        reason="tenants_crossed=2",
    )
    assert decision.decision is Decision.DENY


def test_required_approvers_may_be_zero() -> None:
    decision = _decision(required_approvers=0, tier=Tier.OBSERVE_ONLY)
    assert decision.required_approvers == 0


def test_required_approvers_may_not_be_negative() -> None:
    with pytest.raises(ValueError, match="required_approvers"):
        _decision(required_approvers=-1)


def test_to_record_keys_are_sorted_and_primitive() -> None:
    decision = _decision(approval_ttl=timedelta(hours=24))
    record = decision.to_record()
    assert list(record) == sorted(record)
    allowed = (str, int, bool, type(None))
    assert all(isinstance(v, allowed) for v in record.values())
    json.dumps(record, sort_keys=True)
    assert set(record) == set(GateDecision.__dataclass_fields__)
    assert record["decision"] == "allow"
    assert record["tier"] == "approval-required"
    assert record["capability"] == "script.execute"
    assert record["approval_ttl"] == 86400


def test_to_record_keeps_none_ttl() -> None:
    record = _decision(approval_ttl=None).to_record()
    assert record["approval_ttl"] is None
