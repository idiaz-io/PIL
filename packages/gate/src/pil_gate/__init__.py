"""pil_gate — may this act run?

Library only (I-1). Depends only on ``pil-capabilities`` (ADR-0013). Ships
an abstract :class:`PolicyGate`, one real :class:`ReferenceGate`, and one
test double :class:`StaticGate`. Does not write the ledger, does not query
the graph, and the reference implementation never returns the Otto tier —
that needs a playbook registry no product has yet.
"""

from pil_gate.decision import GateDecision
from pil_gate.fakes import StaticGate
from pil_gate.gate import GRANT_SIGN, PolicyGate, ReferenceGate
from pil_gate.request import Actor, BlastRadius, Breaker, GateRequest
from pil_gate.vocabulary import (
    DECISION_COUNT,
    TIER_COUNT,
    ActorKind,
    Decision,
    Tier,
)

__all__ = [
    "DECISION_COUNT",
    "GRANT_SIGN",
    "TIER_COUNT",
    "Actor",
    "ActorKind",
    "BlastRadius",
    "Breaker",
    "Decision",
    "GateDecision",
    "GateRequest",
    "PolicyGate",
    "ReferenceGate",
    "StaticGate",
    "Tier",
]
