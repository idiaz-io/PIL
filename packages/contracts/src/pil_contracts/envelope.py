"""The message envelope.

Every message PIL produces is an :class:`Envelope`. The envelope carries the facts that
are true of *any* message — who it belongs to, where it came from, when it happened —
and a ``body`` whose shape depends on ``kind``.

That split is deliberate. Adapters are the only producer today, so it would be easy to
design an alert-shaped envelope with ``severity`` and ``category`` at the top level.
Findings and attestations are coming, they are not alerts, and reworking the envelope
once messages are signed is exactly the retrofit I-9 warns about. The envelope is
therefore kind-agnostic from the first commit.

Two fields deserve explanation:

``tenant_id``
    Authoritative, and always taken from the adapter instance's own configuration
    (I-5). It is never read from a vendor payload. An adapter instance may only ever
    emit messages for its configured tenant, and that is enforced by a test.

``tenant_hint``
    What the *vendor payload* claimed the tenant was. AXO derives tenancy from payloads
    in eleven places today — splitting URIs, fuzzy-matching team names, treating an MDM
    policy id as a customer id — and this field is how we measure that without
    depending on it. Nothing may route, authorise or query on ``tenant_hint``. It is
    evidence, not identity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pil_contracts.canonical import canonical_hash, canonical_json
from pil_contracts.versioning import CURRENT_SCHEMA_VERSION, SchemaVersion

__all__ = ["AlertBody", "Envelope", "MessageKind", "TenantHint", "format_timestamp"]


class MessageKind(StrEnum):
    """What a message *is*.

    A closed vocabulary (I-6). Extend by adding properties to a body, never by adding a
    member here — a new kind is an ADR, not a commit.
    """

    ALERT = "alert"


def format_timestamp(value: datetime) -> str:
    """RFC 3339 in UTC, with fixed six-digit precision and a ``Z`` suffix.

    Fixed precision matters: a timestamp that lands on a whole second must not serialise
    differently from one that does not, or the same logical message produces two
    different signatures.

    Naive datetimes are rejected rather than assumed to be UTC. AXO produces naive
    values throughout and they happen to be UTC, but "happens to be" is not something to
    encode into a signed message — the translator has to say so explicitly.

    Formatted from components rather than via ``strftime`` so that the output does not
    depend on the platform's C library.
    """
    if value.tzinfo is None:
        raise ValueError(
            f"{value!r} is naive. Attach a timezone before putting a timestamp in an "
            "envelope — an ambiguous instant cannot be serialised deterministically."
        )
    utc = value.astimezone(UTC)
    return (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"
        f"T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}"
        f".{utc.microsecond:06d}Z"
    )


@dataclass(frozen=True, slots=True)
class TenantHint:
    """The tenant as the vendor payload claimed it. Evidence only — never identity."""

    tenant_id: str | None = None
    tenant_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"tenant_id": self.tenant_id, "tenant_name": self.tenant_name}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> TenantHint:
        if not data:
            return cls()
        return cls(
            tenant_id=_optional_str(data.get("tenant_id")),
            tenant_name=_optional_str(data.get("tenant_name")),
        )


@dataclass(frozen=True, slots=True)
class AlertBody:
    """The ``alert`` kind.

    Field *values* are deliberately unvalidated strings. AXO emits ``"P1"``–``"P4"`` from
    some paths, raw vendor severities from others, and the literal ``"unknown"`` from
    several. I-10 requires PIL to reproduce that exactly, so this shape constrains
    structure and never content. Tightening any of these is a behaviour change and
    belongs in its own commit, after the migration.
    """

    alert_id: str
    device_id: str
    device_name: str
    severity: str
    category: str
    message: str
    device_history: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "device_id": self.device_id,
            "device_name": self.device_name,
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "device_history": [dict(entry) for entry in self.device_history],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AlertBody:
        history = data.get("device_history") or ()
        if not isinstance(history, Sequence) or isinstance(history, (str, bytes)):
            history = ()
        return cls(
            alert_id=_required_str(data, "alert_id"),
            device_id=_required_str(data, "device_id"),
            device_name=_required_str(data, "device_name"),
            severity=_required_str(data, "severity"),
            category=_required_str(data, "category"),
            message=_required_str(data, "message"),
            device_history=tuple(dict(entry) for entry in history if isinstance(entry, Mapping)),
        )


@dataclass(frozen=True, slots=True)
class Envelope:
    """A message produced by PIL."""

    event_id: str
    tenant_id: str
    source: str
    adapter_version: str
    occurred_at: datetime
    observed_at: datetime
    body: AlertBody
    kind: MessageKind = MessageKind.ALERT
    schema_version: SchemaVersion = CURRENT_SCHEMA_VERSION
    tenant_hint: TenantHint = field(default_factory=TenantHint)
    raw_payload: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError(
                "tenant_id is empty. I-5: the tenant comes from the adapter instance's "
                "configuration and is never optional."
            )

    # -- serialisation -------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON types, ready for :func:`canonical_json`.

        Every conversion is explicit. Nothing is left for an encoder to guess at.
        """
        return {
            "schema_version": str(self.schema_version),
            "kind": self.kind.value,
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "tenant_hint": self.tenant_hint.to_dict(),
            "source": self.source,
            "adapter_version": self.adapter_version,
            "occurred_at": format_timestamp(self.occurred_at),
            "observed_at": format_timestamp(self.observed_at),
            "body": self.body.to_dict(),
            "raw_payload": dict(self.raw_payload),
        }

    def to_canonical_json(self) -> bytes:
        return canonical_json(self.to_dict())

    def content_hash(self) -> str:
        return canonical_hash(self.to_dict())

    # -- parsing -------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Envelope:
        """Parse an envelope.

        Unknown fields are ignored, never rejected (I-7, ADR-0002) — including fields
        added by a future major version. A *missing required* field is a malformed
        message rather than a version mismatch, and does raise.
        """
        kind_raw = data.get("kind", MessageKind.ALERT.value)
        try:
            kind = MessageKind(kind_raw)
        except ValueError as exc:
            # A kind we do not know is a closed-vocabulary violation from a newer
            # producer. Surface it plainly rather than guessing at the body's shape.
            raise ValueError(
                f"unknown message kind {kind_raw!r}. Adding a kind is an ADR (I-6)."
            ) from exc

        body_raw = data.get("body")
        if not isinstance(body_raw, Mapping):
            raise ValueError("envelope is missing its 'body'")

        raw_payload = data.get("raw_payload")

        return cls(
            schema_version=SchemaVersion.parse(data.get("schema_version")),
            kind=kind,
            event_id=_required_str(data, "event_id"),
            tenant_id=_required_str(data, "tenant_id"),
            tenant_hint=TenantHint.from_dict(data.get("tenant_hint")),
            source=_required_str(data, "source"),
            adapter_version=_required_str(data, "adapter_version"),
            occurred_at=_required_timestamp(data, "occurred_at"),
            observed_at=_required_timestamp(data, "observed_at"),
            body=AlertBody.from_dict(body_raw),
            raw_payload=dict(raw_payload) if isinstance(raw_payload, Mapping) else {},
        )


# ----------------------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------------------


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _required_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"envelope field {key!r} must be a string, got {type(value).__name__}")
    return value


def _required_timestamp(data: Mapping[str, Any], key: str) -> datetime:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"envelope field {key!r} must be an RFC 3339 string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"envelope field {key!r} is not a valid RFC 3339 timestamp: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise ValueError(f"envelope field {key!r} must carry a timezone offset")
    return parsed.astimezone(UTC)
