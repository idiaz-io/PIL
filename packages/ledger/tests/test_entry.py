"""SealInput construction — blank tenant rejected; no caller-supplied hashes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pil_ledger.entry import SealedEntry, SealInput
from pil_ledger.vocabulary import EntryKind

WHEN = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def _input(**overrides: object) -> SealInput:
    values: dict[str, object] = {
        "tenant_id": "tenant-acme",
        "kind": EntryKind.POLICY_DECISION,
        "event_type": "gate.signed",
        "subject": "script.execute",
        "payload": {"decision": "allow"},
        "occurred_at": WHEN,
    }
    values.update(overrides)
    return SealInput(**values)  # type: ignore[arg-type]


def test_blank_tenant_id_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        _input(tenant_id="")


def test_whitespace_tenant_id_rejected() -> None:
    with pytest.raises(ValueError, match="tenant_id"):
        _input(tenant_id="   ")


def test_blank_event_type_rejected() -> None:
    with pytest.raises(ValueError, match="event_type"):
        _input(event_type="")


def test_naive_occurred_at_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _input(occurred_at=datetime(2026, 9, 17, 12, 0))


def test_forbidden_payload_key_rejected() -> None:
    with pytest.raises(ValueError, match="narrative"):
        _input(payload={"narrative": "raw alert text"})


def test_nested_forbidden_payload_key_rejected() -> None:
    with pytest.raises(ValueError, match="playbook_body"):
        _input(payload={"step": {"playbook_body": "rm -rf /"}})


def test_seal_input_has_no_hash_or_signature_field() -> None:
    fields = set(SealInput.__dataclass_fields__)
    assert "entry_hash" not in fields
    assert "signature" not in fields
    assert "prev_entry_hash" not in fields
    assert "payload_hash" not in fields
    assert "seq" not in fields


def test_sealed_entry_has_no_payload_body() -> None:
    assert "payload" not in set(SealedEntry.__dataclass_fields__)
