"""Closed vocabularies for the sealed ledger.

Ported from merp-console's ``ledger_entries.kind`` CHECK (``0006_ledger.sql``)
and ``MERP-Agent-Handover.md`` §6.4. Console strings, because those rows
already exist. Handover also names ``oscal_emission`` and ``exercise_report``;
those are not in the CHECK and are not members here (ADR-0014 §7).

Closed (I-6): extend by adding a property to :class:`~pil_ledger.entry.SealedEntry`,
never by adding a member here. Counts pinned so an addition fails CI until an
ADR bumps them.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

__all__ = [
    "ALGORITHM",
    "FORBIDDEN_PAYLOAD_KEYS",
    "KIND_COUNT",
    "EntryKind",
]


class EntryKind(StrEnum):
    """What kind of evidence this row is. Console CHECK, byte-exact."""

    FINDING = "finding"
    CHANGE_RECORD = "change_record"
    ATTESTATION = "attestation"
    POLICY_DECISION = "policy_decision"
    BREAKER_TRIP = "breaker_trip"


KIND_COUNT: Final = 5

ALGORITHM: Final = "hmac-sha256-interim"
"""Console 0019's algorithm string. Not cosign, not KMS (ADR-0014 §2)."""

FORBIDDEN_PAYLOAD_KEYS: Final = frozenset(
    {
        "quoted_text",
        "artifact_text",
        "narrative",
        "content",
        "sensor_payload",
        "device_payload",
        "identity_payload",
        "playbook_body",
    }
)
"""Handover §6.4 redaction-at-append. Rejected on input, not stripped."""
