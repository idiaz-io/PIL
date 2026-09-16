"""Closed vocabularies for the policy gate — three decisions, four tiers.

Ported from merp-console's ``gate_decisions`` CHECK constraints
(``0005_products_and_entitlement.sql``) and ``MERP-Agent-Handover.md`` §6.5.
PIL uses the console's decision words because those rows already exist in a
live database (ADR-0013 §2). The handover's names are the same three
outcomes under other labels — recorded on :class:`Decision`, not modelled
as a fourth vocabulary.

Closed (I-6): extend by adding a property to :class:`~pil_gate.decision.GateDecision`
or :class:`~pil_gate.request.GateRequest`, never by adding a member here.
Counts pinned so an addition fails CI until an ADR bumps them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

__all__ = [
    "DECISION_COUNT",
    "TIER_COUNT",
    "ActorKind",
    "Decision",
    "Tier",
]


class Decision(StrEnum):
    """May this act run?

    Console strings (``allow`` / ``hold`` / ``deny``). Handover §6.5 mapping,
    documented here so it is not modelled as a second enum:

    - ``allow`` ≡ ``allow_auto``
    - ``hold`` ≡ ``require_named_human``
    - ``deny`` ≡ ``deny``
    """

    ALLOW = "allow"
    HOLD = "hold"
    DENY = "deny"


DECISION_COUNT: Final = 3


class Tier(StrEnum):
    """Handover §6.5 tiers, byte-for-byte as merp-console's CHECK spells them.

    ``observe-only`` — detect and record; never act. The reference gate's
    tier for an allowed read (ADR-0013 §3).
    ``safe-auto-heal`` — reversible, bounded blast radius; executes without
    approval. Vocabulary only in v1 — :class:`~pil_gate.gate.ReferenceGate`
    never produces it (no playbook registry exists).
    ``approval-required`` — executes only after a named-human signature.
    ``blocked-by-default`` — deny; unblocking is itself a signed policy change.
    """

    OBSERVE_ONLY = "observe-only"
    SAFE_AUTO_HEAL = "safe-auto-heal"
    APPROVAL_REQUIRED = "approval-required"
    BLOCKED_BY_DEFAULT = "blocked-by-default"


TIER_COUNT: Final = 4


class ActorKind(StrEnum):
    """Who is asking. Console ``principal_type``: ``user`` maps to ``human``;
    anything else (``agent`` / ``service``) maps to ``service`` — a non-human
    cannot hold ``org.grant.sign`` (``sign_write_grant``: human_only)."""

    HUMAN = "human"
    SERVICE = "service"
