"""StaticLedger records inputs and emits placeholder hashes."""

from __future__ import annotations

from datetime import UTC, datetime

from pil_ledger.entry import SealInput
from pil_ledger.fakes import StaticLedger
from pil_ledger.vocabulary import EntryKind

WHEN = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def _input() -> SealInput:
    return SealInput(
        tenant_id="tenant-acme",
        kind=EntryKind.FINDING,
        event_type="finding.raised",
        subject="host-1",
        payload={"severity": 4},
        occurred_at=WHEN,
    )


def test_static_ledger_records_and_chains_placeholders() -> None:
    ledger = StaticLedger()
    first = ledger.append(_input())
    second = ledger.append(_input())
    assert first.entry_hash == "static-1"
    assert second.prev_entry_hash == "static-1"
    assert second.entry_hash == "static-2"
    assert ledger.inputs == [_input(), _input()]
    assert first.signature == "static"
