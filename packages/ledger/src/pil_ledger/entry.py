"""Ledger input and sealed output. Hash fields are absent on the input on purpose.

§6.4: hashes and the signature come from the sealer, never from the caller.
:class:`SealInput` has no ``entry_hash`` / ``signature`` the same way
:class:`~pil_gate.request.GateRequest` has no ``tier``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pil_ledger.vocabulary import FORBIDDEN_PAYLOAD_KEYS, EntryKind

__all__ = ["SealInput", "SealedEntry", "VerifyReport"]


def _require(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} is required and may not be blank")


def _reject_forbidden(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            if key in FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"payload key {key!r} is forbidden (redact before sealing)")
            _reject_forbidden(inner, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            _reject_forbidden(inner, path=f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class SealInput:
    """One unsigned fact. No hashes, no signature, no seq."""

    tenant_id: str
    kind: EntryKind
    event_type: str
    subject: str
    payload: Mapping[str, Any]
    occurred_at: datetime
    actor_principal_id: str | None = None
    assumed_role_key: str | None = None
    payload_ref: str = "inline:no-payload-store"

    def __post_init__(self) -> None:
        _require(self.tenant_id, "tenant_id")
        _require(self.event_type, "event_type")
        _require(self.subject, "subject")
        _require(self.payload_ref, "payload_ref")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        if not isinstance(self.payload, Mapping):
            raise ValueError("payload must be a mapping")
        _reject_forbidden(self.payload, path="payload")
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True, slots=True)
class SealedEntry:
    """One chained, signed row. No payload body — hash + ref only."""

    seq: int
    tenant_id: str
    kind: EntryKind
    event_type: str
    subject: str
    actor_principal_id: str | None
    assumed_role_key: str | None
    payload_hash: str
    payload_ref: str
    prev_entry_hash: str | None
    entry_hash: str
    signature: str
    signing_key_id: str
    occurred_at: datetime
    algorithm: str

    def __post_init__(self) -> None:
        if self.seq < 1:
            raise ValueError("seq must be >= 1")
        _require(self.tenant_id, "tenant_id")
        _require(self.entry_hash, "entry_hash")
        _require(self.signature, "signature")
        _require(self.payload_hash, "payload_hash")


@dataclass(frozen=True, slots=True)
class VerifyReport:
    """Result of recomputing a slice. ``broken_at_seq`` is the first failure."""

    ok: bool
    broken_at_seq: int | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.ok and self.broken_at_seq is not None:
            raise ValueError("ok report cannot name a broken seq")
        if not self.ok and self.broken_at_seq is None:
            raise ValueError("failed report must name a broken seq")
