"""pil_ledger — seal this evidence, then prove nobody tampered with it.

Library only (I-1). Zero dependencies (ADR-0014). Ships an abstract
:class:`Ledger`, one real :class:`HmacSealer`, an in-memory chain
:class:`MemoryLedger` for tests, and one test double :class:`StaticLedger`.
Does not persist rows, does not open KMS, does not import the gate.
"""

from pil_ledger.entry import SealedEntry, SealInput, VerifyReport
from pil_ledger.fakes import MemoryLedger, StaticLedger
from pil_ledger.seal import HmacSealer, Ledger
from pil_ledger.signer import HmacSigner
from pil_ledger.vocabulary import ALGORITHM, FORBIDDEN_PAYLOAD_KEYS, KIND_COUNT, EntryKind

__all__ = [
    "ALGORITHM",
    "FORBIDDEN_PAYLOAD_KEYS",
    "KIND_COUNT",
    "EntryKind",
    "HmacSealer",
    "HmacSigner",
    "Ledger",
    "MemoryLedger",
    "SealInput",
    "SealedEntry",
    "StaticLedger",
    "VerifyReport",
]
