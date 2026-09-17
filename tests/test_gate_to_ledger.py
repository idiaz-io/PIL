"""Workspace seam: a GateDecision.to_record() can be sealed without pil_ledger
importing pil_gate (ADR-0014 §5). This test is the only permitted coupling.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pil_capabilities import Capability
from pil_gate.decision import GateDecision
from pil_gate.vocabulary import Decision, Tier
from pil_ledger.entry import SealInput
from pil_ledger.seal import HmacSealer
from pil_ledger.signer import HmacSigner
from pil_ledger.vocabulary import EntryKind


def test_a_gate_decision_record_seals_as_policy_decision() -> None:
    decision = GateDecision(
        decision_id="dec-1",
        tenant_id="tenant-acme",
        product="axo",
        capability=Capability.SCRIPT_EXECUTE,
        decision=Decision.ALLOW,
        tier=Tier.APPROVAL_REQUIRED,
        policy_version="console-v1",
        required_approvers=1,
        approval_ttl=None,
        reason="signed by human holding org.grant.sign",
    )
    record = decision.to_record()
    sealer = HmacSealer(signer=HmacSigner("tenant-acme-hmac-1", b"a" * 32))
    sealed = sealer.seal(
        SealInput(
            tenant_id=str(record["tenant_id"]),
            kind=EntryKind.POLICY_DECISION,
            event_type="gate.signed",
            subject=str(record["capability"]),
            payload=record,
            occurred_at=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
            actor_principal_id="user:1",
        ),
        seq=1,
        prev_entry_hash=None,
    )
    assert sealed.kind is EntryKind.POLICY_DECISION
    assert sealer.verify([sealed]).ok
    assert "entry_hash" not in record
