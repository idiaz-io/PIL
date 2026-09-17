"""The sealer itself: an interface, one HMAC implementation, no side effects.

``seal()`` is a pure function of the input, ``seq``, ``prev_entry_hash``, and
the injected signer. Nothing is written — not a database, not a file
(ADR-0014 §3).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from pil_ledger.canon import entry_hash_hex, payload_hash_hex
from pil_ledger.entry import SealedEntry, SealInput, VerifyReport
from pil_ledger.signer import HmacSigner
from pil_ledger.vocabulary import ALGORITHM

__all__ = ["HmacSealer", "Ledger"]


class Ledger(ABC):
    """Appends a sealed entry onto some chain. Not async — nothing here does I/O."""

    @abstractmethod
    def append(self, entry: SealInput) -> SealedEntry:
        """Seal ``entry`` as the next row for its tenant and return it."""


@dataclass(frozen=True, slots=True)
class HmacSealer:
    """v1 sealer/verifier. Evaluates the ADR-0014 chain formula.

    Does not implement :class:`Ledger` — it has no head-of-chain. Products
    call :meth:`seal` with the previous row's hash from *their* store.
    :class:`~pil_ledger.fakes.MemoryLedger` wraps this for in-process tests.
    """

    signer: HmacSigner

    def seal(
        self,
        entry: SealInput,
        *,
        seq: int,
        prev_entry_hash: str | None,
    ) -> SealedEntry:
        if seq < 1:
            raise ValueError("seq must be >= 1")
        if seq == 1 and prev_entry_hash is not None:
            raise ValueError("genesis seq=1 requires prev_entry_hash=None")
        if seq > 1 and not prev_entry_hash:
            raise ValueError("seq>1 requires prev_entry_hash")

        payload_hash = payload_hash_hex(entry)
        entry_hash = entry_hash_hex(prev_entry_hash, seq, payload_hash)
        signature = self.signer.sign(entry_hash)
        return SealedEntry(
            seq=seq,
            tenant_id=entry.tenant_id,
            kind=entry.kind,
            event_type=entry.event_type,
            subject=entry.subject,
            actor_principal_id=entry.actor_principal_id,
            assumed_role_key=entry.assumed_role_key,
            payload_hash=payload_hash,
            payload_ref=entry.payload_ref,
            prev_entry_hash=prev_entry_hash,
            entry_hash=entry_hash,
            signature=signature,
            signing_key_id=self.signer.key_id,
            occurred_at=entry.occurred_at,
            algorithm=ALGORITHM,
        )

    def verify(self, entries: Sequence[SealedEntry]) -> VerifyReport:
        """Recompute the chain and signatures. Empty slice is vacuously ok."""
        if not entries:
            return VerifyReport(ok=True)

        tenant_id = entries[0].tenant_id
        expected_prev: str | None = None
        expected_seq = 1
        for item in entries:
            if item.tenant_id != tenant_id:
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason=f"tenant_id changed to {item.tenant_id!r}",
                )
            if item.seq != expected_seq:
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason=f"expected seq={expected_seq}",
                )
            if item.prev_entry_hash != expected_prev:
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason="prev_entry_hash does not match previous entry_hash",
                )
            if item.algorithm != ALGORITHM:
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason=f"unsupported algorithm {item.algorithm!r}",
                )
            recomputed = entry_hash_hex(item.prev_entry_hash, item.seq, item.payload_hash)
            if recomputed != item.entry_hash:
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason="entry_hash does not match prev|seq|payload_hash",
                )
            if item.signing_key_id != self.signer.key_id:
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason="signing_key_id does not match verifier",
                )
            if not self.signer.verify_signature(item.entry_hash, item.signature):
                return VerifyReport(
                    ok=False,
                    broken_at_seq=item.seq,
                    reason="signature mismatch",
                )
            expected_prev = item.entry_hash
            expected_seq += 1
        return VerifyReport(ok=True)

    def verify_payload(self, entry: SealInput, sealed: SealedEntry) -> VerifyReport:
        """Does ``sealed.payload_hash`` match this body? Needs the payload."""
        if (
            entry.tenant_id != sealed.tenant_id
            or entry.kind != sealed.kind
            or entry.event_type != sealed.event_type
            or entry.subject != sealed.subject
        ):
            return VerifyReport(
                ok=False,
                broken_at_seq=sealed.seq,
                reason="seal input does not match sealed entry metadata",
            )
        expected = payload_hash_hex(entry)
        if expected != sealed.payload_hash:
            return VerifyReport(
                ok=False,
                broken_at_seq=sealed.seq,
                reason="payload_hash does not match body",
            )
        return VerifyReport(ok=True)
