"""Test doubles: an in-memory chain, and a static emitter with no crypto.

Mirrors :class:`pil_gate.fakes.StaticGate` and
:class:`pil_graph.fakes.InMemoryGraphDriver`: ship the fakes here so
consumers do not each write their own and drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pil_ledger.entry import SealedEntry, SealInput
from pil_ledger.seal import HmacSealer, Ledger
from pil_ledger.vocabulary import ALGORITHM

__all__ = ["MemoryLedger", "StaticLedger"]


@dataclass(slots=True)
class MemoryLedger(Ledger):
    """Per-tenant in-memory chain over a real :class:`HmacSealer`.

    Assigns ``seq`` and previous hash. Not a production store — the product
    persists; this exists so tests (and only tests) need not fake the head.
    """

    sealer: HmacSealer
    _chains: dict[str, list[SealedEntry]] = field(default_factory=dict)

    def append(self, entry: SealInput) -> SealedEntry:
        chain = self._chains.setdefault(entry.tenant_id, [])
        seq = len(chain) + 1
        prev = chain[-1].entry_hash if chain else None
        sealed = self.sealer.seal(entry, seq=seq, prev_entry_hash=prev)
        chain.append(sealed)
        return sealed

    def entries(self, tenant_id: str) -> tuple[SealedEntry, ...]:
        return tuple(self._chains.get(tenant_id, ()))


@dataclass(slots=True)
class StaticLedger(Ledger):
    """Returns deterministic placeholder hashes. Records every input."""

    inputs: list[SealInput] = field(default_factory=list)

    def append(self, entry: SealInput) -> SealedEntry:
        self.inputs.append(entry)
        seq = len(self.inputs)
        prev = f"static-{seq - 1}" if seq > 1 else None
        fake = f"static-{seq}"
        return SealedEntry(
            seq=seq,
            tenant_id=entry.tenant_id,
            kind=entry.kind,
            event_type=entry.event_type,
            subject=entry.subject,
            actor_principal_id=entry.actor_principal_id,
            assumed_role_key=entry.assumed_role_key,
            payload_hash=fake,
            payload_ref=entry.payload_ref,
            prev_entry_hash=prev,
            entry_hash=fake,
            signature="static",
            signing_key_id="static",
            occurred_at=entry.occurred_at,
            algorithm=ALGORITHM,
        )
