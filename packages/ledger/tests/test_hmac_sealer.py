"""HmacSealer — chain, tamper, payload check, genesis rules."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from pil_ledger.canon import entry_hash_hex, payload_hash_hex
from pil_ledger.entry import SealInput
from pil_ledger.fakes import MemoryLedger
from pil_ledger.seal import HmacSealer
from pil_ledger.signer import HmacSigner
from pil_ledger.vocabulary import ALGORITHM, EntryKind

WHEN = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)
SECRET = b"a" * 32
KEY_ID = "tenant-acme-hmac-1"


def _signer() -> HmacSigner:
    return HmacSigner(KEY_ID, SECRET)


def _sealer() -> HmacSealer:
    return HmacSealer(signer=_signer())


def _input(
    *,
    tenant_id: str = "tenant-acme",
    subject: str = "script.execute",
    payload: dict[str, object] | None = None,
) -> SealInput:
    return SealInput(
        tenant_id=tenant_id,
        kind=EntryKind.POLICY_DECISION,
        event_type="gate.signed",
        subject=subject,
        payload=payload if payload is not None else {"decision": "allow"},
        occurred_at=WHEN,
        actor_principal_id="user:1",
    )


def test_genesis_has_null_prev_and_seq_one() -> None:
    sealed = _sealer().seal(_input(), seq=1, prev_entry_hash=None)
    assert sealed.seq == 1
    assert sealed.prev_entry_hash is None
    assert sealed.algorithm == ALGORITHM
    assert sealed.signing_key_id == KEY_ID
    assert sealed.payload_hash == payload_hash_hex(_input())
    assert sealed.entry_hash == entry_hash_hex(None, 1, sealed.payload_hash)
    assert _signer().verify_signature(sealed.entry_hash, sealed.signature)


def test_second_entry_chains_off_the_first() -> None:
    sealer = _sealer()
    first = sealer.seal(_input(subject="one"), seq=1, prev_entry_hash=None)
    second = sealer.seal(_input(subject="two"), seq=2, prev_entry_hash=first.entry_hash)
    assert second.prev_entry_hash == first.entry_hash
    assert second.seq == 2
    report = sealer.verify([first, second])
    assert report.ok


def test_seq_one_rejects_a_prev_hash() -> None:
    with pytest.raises(ValueError, match="genesis"):
        _sealer().seal(_input(), seq=1, prev_entry_hash="abc")


def test_seq_two_requires_a_prev_hash() -> None:
    with pytest.raises(ValueError, match="prev_entry_hash"):
        _sealer().seal(_input(), seq=2, prev_entry_hash=None)


def test_empty_slice_verifies() -> None:
    assert _sealer().verify([]).ok


def test_bit_flip_entry_hash_breaks_the_chain() -> None:
    sealer = _sealer()
    first = sealer.seal(_input(), seq=1, prev_entry_hash=None)
    flipped = replace(first, entry_hash=("f" * 64))
    report = sealer.verify([flipped])
    assert not report.ok
    assert report.broken_at_seq == 1
    assert "entry_hash" in report.reason


def test_dropping_seq_two_breaks_at_three() -> None:
    ledger = MemoryLedger(sealer=_sealer())
    first = ledger.append(_input(subject="a"))
    ledger.append(_input(subject="b"))
    third = ledger.append(_input(subject="c"))
    report = _sealer().verify([first, third])
    assert not report.ok
    assert report.broken_at_seq == 3


def test_swapping_two_entries_breaks() -> None:
    ledger = MemoryLedger(sealer=_sealer())
    first = ledger.append(_input(subject="a"))
    second = ledger.append(_input(subject="b"))
    report = _sealer().verify([second, first])
    assert not report.ok
    assert report.broken_at_seq == second.seq


def test_wrong_key_breaks_signature() -> None:
    sealer = _sealer()
    first = sealer.seal(_input(), seq=1, prev_entry_hash=None)
    other = HmacSealer(signer=HmacSigner("other-key", b"b" * 32))
    report = other.verify([first])
    assert not report.ok
    assert "signing_key_id" in report.reason or "signature" in report.reason


def test_memory_ledger_is_per_tenant() -> None:
    ledger = MemoryLedger(sealer=_sealer())
    a = ledger.append(_input(tenant_id="tenant-a", subject="a"))
    b = ledger.append(_input(tenant_id="tenant-b", subject="b"))
    assert a.seq == 1
    assert b.seq == 1
    assert a.entry_hash != b.entry_hash
    assert _sealer().verify(ledger.entries("tenant-a")).ok
    assert _sealer().verify(ledger.entries("tenant-b")).ok


def test_mixed_tenants_in_one_slice_fail() -> None:
    ledger = MemoryLedger(sealer=_sealer())
    a = ledger.append(_input(tenant_id="tenant-a"))
    b = ledger.append(_input(tenant_id="tenant-b"))
    report = _sealer().verify([a, b])
    assert not report.ok
    assert "tenant_id" in report.reason


def test_verify_payload_accepts_the_original_body() -> None:
    source = _input()
    sealed = _sealer().seal(source, seq=1, prev_entry_hash=None)
    assert _sealer().verify_payload(source, sealed).ok


def test_verify_payload_rejects_a_mutated_body() -> None:
    source = _input(payload={"decision": "allow"})
    sealed = _sealer().seal(source, seq=1, prev_entry_hash=None)
    mutated = _input(payload={"decision": "deny"})
    report = _sealer().verify_payload(mutated, sealed)
    assert not report.ok
    assert "payload_hash" in report.reason


def test_golden_genesis_hashes_are_pinned() -> None:
    """A change to the formula fails here rather than silently drifting."""
    sealed = _sealer().seal(_input(), seq=1, prev_entry_hash=None)
    assert sealed.payload_hash == payload_hash_hex(_input())
    assert sealed.entry_hash == entry_hash_hex(None, 1, sealed.payload_hash)
    assert len(sealed.payload_hash) == 64
    assert len(sealed.entry_hash) == 64
    assert len(sealed.signature) == 64
    assert sealed.payload_hash == (
        "ba661455bbd23beb8ded3de74af56abdae938958e8ddc71a41076a4b33585beb"
    )
    assert sealed.entry_hash == ("f96824a09911d494533f5f97a4f6135a194cfaea6606fb1d2bf131b60754bc51")
    assert sealed.signature == ("4a7e8f780aca8413afbd33d1587b27fa4626abb1233c620f42893346c8e6f65d")
