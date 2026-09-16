"""The gate's input. Tier and decision are absent on purpose.

§6.5: an action's tier comes from policy, never from the caller.
:class:`GateRequest` has no ``tier`` field the same way ``Translation`` has
no tenant field — there is nowhere to put a caller-supplied authorization.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pil_capabilities import Capability
from pil_gate.vocabulary import ActorKind

__all__ = ["Actor", "BlastRadius", "Breaker", "GateRequest"]


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} is required and may not be blank")


@dataclass(frozen=True, slots=True)
class Actor:
    """Who is asking to act. ``identity_ref`` is opaque — never a secret (I-8)."""

    identity_ref: str
    kind: ActorKind
    permissions: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class BlastRadius:
    """§6.5 blast-radius fields, computed by the caller (an ITKG query).

    ``None`` on :class:`GateRequest` means "not computed", never "safe"
    (ADR-0013 §6). A present value can only narrow a write — it cannot
    widen one to ``allow``.
    """

    tenants_crossed: int
    mission_critical_downstream: int
    max_depth_hit: bool
    data_classifications: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class Breaker:
    """§6.5 circuit breaker. Default threshold in the handover is 3;
    this type carries the already-evaluated rate and trip flag — computing
    them is the caller's job."""

    class_rate_1h: int
    tripped: bool


@dataclass(frozen=True, slots=True)
class GateRequest:
    """One question for the gate. No tier, no decision, no pre-approved flag."""

    tenant_id: str
    product: str
    capability: Capability
    actor: Actor
    target_ref: str | None = None
    blast_radius: BlastRadius | None = None
    breaker: Breaker | None = None

    def __post_init__(self) -> None:
        _require(self.tenant_id, "tenant_id")
        _require(self.product, "product")
