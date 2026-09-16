"""A test double that returns a configured decision and records requests.

Mirrors :class:`pil_graph.fakes.InMemoryGraphDriver` and
``StaticConnectionProvider``: ship one fake here so consumers do not each
write their own and drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pil_gate.decision import GateDecision
from pil_gate.gate import PolicyGate
from pil_gate.request import GateRequest
from pil_gate.vocabulary import Decision, Tier

__all__ = ["StaticGate"]


@dataclass(slots=True)
class StaticGate(PolicyGate):
    """Returns the same decision every time. Records every request."""

    decision: Decision
    tier: Tier
    policy_version: str = "static-test"
    reason: str = "static test double"
    requests: list[GateRequest] = field(default_factory=list)

    def decide(self, request: GateRequest) -> GateDecision:
        self.requests.append(request)
        return GateDecision(
            decision_id="static",
            tenant_id=request.tenant_id,
            product=request.product,
            capability=request.capability,
            decision=self.decision,
            tier=self.tier,
            policy_version=self.policy_version,
            required_approvers=1,
            approval_ttl=None,
            reason=self.reason,
        )
