"""Canonical JSON and the console's HMAC chain preimages.

Stdlib ``json`` only (ADR-0014 §1). Separators and ``sort_keys`` are pinned so
a hash cannot drift because someone pretty-printed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Final

from pil_ledger.entry import SealInput

__all__ = [
    "canonical_json",
    "entry_hash_hex",
    "payload_document",
    "payload_hash_hex",
]

_SEPARATORS: Final = (",", ":")


def canonical_json(value: object) -> bytes:
    """UTF-8 JSON, keys sorted, no extra whitespace."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=_SEPARATORS,
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _rfc3339(when: datetime) -> str:
    return when.isoformat()


def payload_document(entry: SealInput) -> dict[str, Any]:
    """Everything ``payload_hash`` covers — metadata plus the caller's mapping."""
    return {
        "actor_principal_id": entry.actor_principal_id,
        "assumed_role_key": entry.assumed_role_key,
        "event_type": entry.event_type,
        "kind": entry.kind.value,
        "occurred_at": _rfc3339(entry.occurred_at),
        "payload": dict(entry.payload),
        "payload_ref": entry.payload_ref,
        "subject": entry.subject,
        "tenant_id": entry.tenant_id,
    }


def payload_hash_hex(entry: SealInput) -> str:
    return hashlib.sha256(canonical_json(payload_document(entry))).hexdigest()


def entry_hash_hex(prev_entry_hash: str | None, seq: int, payload_hash: str) -> str:
    """Console 0019: sha256(coalesce(prev, '') || '|' || seq || '|' || payload_hash)."""
    prev = prev_entry_hash or ""
    preimage = f"{prev}|{seq}|{payload_hash}".encode()
    return hashlib.sha256(preimage).hexdigest()
