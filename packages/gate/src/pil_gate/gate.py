"""The gate itself: an interface, one reference policy, no side effects.

``decide()`` is a pure function of the request plus one injectable
``id_factory`` for ``decision_id``. Nothing is written — not a sink, not
a log, not the ledger (ADR-0013 §5).
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Final

from pil_capabilities import CAPABILITIES, Risk
from pil_gate.decision import GateDecision
from pil_gate.request import GateRequest
from pil_gate.vocabulary import ActorKind, Decision, Tier

__all__ = ["GRANT_SIGN", "PolicyGate", "ReferenceGate"]

GRANT_SIGN: Final = "org.grant.sign"
"""Ported from merp-console ``sign_write_grant``. Overridable per
:class:`ReferenceGate` instance (ADR-0013 alternative for v1)."""


def _new_decision_id() -> str:
    return uuid.uuid4().hex


class PolicyGate(ABC):
    """Answers: may this act run? Not async — nothing here does I/O."""

    @abstractmethod
    def decide(self, request: GateRequest) -> GateDecision:
        """Return a decision for ``request``. Pure; no side effects."""


@dataclass(frozen=True, slots=True)
class ReferenceGate(PolicyGate):
    """The v1 policy. Evaluates the ADR-0013 table, top to bottom.

    Never produces :attr:`~pil_gate.vocabulary.Tier.SAFE_AUTO_HEAL` — that
    needs a playbook registry entry (handover E6.5) that does not exist.
    """

    policy_version: str
    required_approvers: int = 1
    approval_ttl: timedelta = timedelta(hours=24)
    sign_permission: str = GRANT_SIGN
    id_factory: Callable[[], str] = field(default=_new_decision_id)

    def __post_init__(self) -> None:
        if not self.policy_version or not self.policy_version.strip():
            raise ValueError("policy_version is required and may not be blank")
        if self.required_approvers < 1:
            raise ValueError("required_approvers must be > 0")

    def decide(self, request: GateRequest) -> GateDecision:
        risk = CAPABILITIES[request.capability].risk
        if risk is Risk.READ:
            return self._emit(
                request,
                Decision.ALLOW,
                Tier.OBSERVE_ONLY,
                required_approvers=0,
                approval_ttl=None,
                reason="read capability — observe only, never act",
            )
        blast = request.blast_radius
        if blast is not None and blast.tenants_crossed > 0:
            return self._emit(
                request,
                Decision.DENY,
                Tier.BLOCKED_BY_DEFAULT,
                required_approvers=self.required_approvers,
                approval_ttl=None,
                reason=f"blast radius tenants_crossed={blast.tenants_crossed}",
            )
        breaker = request.breaker
        if breaker is not None and breaker.tripped:
            return self._emit(
                request,
                Decision.HOLD,
                Tier.APPROVAL_REQUIRED,
                required_approvers=self.required_approvers,
                approval_ttl=self.approval_ttl,
                reason=f"breaker tripped, class_rate_1h={breaker.class_rate_1h}",
            )
        actor = request.actor
        if actor.kind is ActorKind.HUMAN and self.sign_permission in actor.permissions:
            return self._emit(
                request,
                Decision.ALLOW,
                Tier.APPROVAL_REQUIRED,
                required_approvers=self.required_approvers,
                approval_ttl=None,
                reason=f"signed by human holding {self.sign_permission}",
            )
        if actor.kind is ActorKind.SERVICE:
            why = "service actor cannot sign"
        else:
            why = f"lacks {self.sign_permission}"
        return self._emit(
            request,
            Decision.HOLD,
            Tier.APPROVAL_REQUIRED,
            required_approvers=self.required_approvers,
            approval_ttl=self.approval_ttl,
            reason=why,
        )

    def _emit(
        self,
        request: GateRequest,
        decision: Decision,
        tier: Tier,
        *,
        required_approvers: int,
        approval_ttl: timedelta | None,
        reason: str,
    ) -> GateDecision:
        return GateDecision(
            decision_id=self.id_factory(),
            tenant_id=request.tenant_id,
            product=request.product,
            capability=request.capability,
            decision=decision,
            tier=tier,
            policy_version=self.policy_version,
            required_approvers=required_approvers,
            approval_ttl=approval_ttl,
            reason=reason,
        )
