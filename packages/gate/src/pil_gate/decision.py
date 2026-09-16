"""The gate's output. Immutable. Deny without a reason cannot be constructed.

Mirrors merp-console's ``gate_decisions_deny_requires_reason`` CHECK —
"an auditor asking why didn't you patch this gets an answer." The gate
never writes the ledger (ADR-0013 §5); :meth:`GateDecision.to_record`
returns primitives a future ``pil_ledger`` can canonicalise.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import timedelta

from pil_capabilities import Capability
from pil_gate.vocabulary import Decision, Tier

__all__ = ["GateDecision"]


@dataclass(frozen=True, slots=True)
class GateDecision:
    """One answer. Shaped like a ``gate_decisions`` row, minus persistence."""

    decision_id: str
    tenant_id: str
    product: str
    capability: Capability
    decision: Decision
    tier: Tier
    policy_version: str
    required_approvers: int
    approval_ttl: timedelta | None
    reason: str

    def __post_init__(self) -> None:
        if self.required_approvers < 0:
            raise ValueError("required_approvers must be >= 0")
        if self.decision is Decision.DENY and not self.reason.strip():
            raise ValueError("deny requires a reason")

    def to_record(self) -> dict[str, object]:
        """Sorted-key mapping of primitives for a future ledger append.

        Enums become ``.value``, ``timedelta`` becomes total seconds as
        ``int``, ``None`` stays ``None``. Does not import ``pil_contracts``
        — canonicalisation is the ledger's job.
        """
        raw: dict[str, object] = {}
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, (Decision, Tier, Capability)):
                raw[item.name] = value.value
            elif isinstance(value, timedelta):
                raw[item.name] = int(value.total_seconds())
            else:
                raw[item.name] = value
        return dict(sorted(raw.items()))
