"""Closed vocabularies — pinned counts, console CHECK strings byte-exact."""

from __future__ import annotations

import pytest

from pil_ledger.vocabulary import ALGORITHM, FORBIDDEN_PAYLOAD_KEYS, KIND_COUNT, EntryKind


def test_kind_count_is_pinned() -> None:
    assert len(EntryKind) == KIND_COUNT == 5


def test_known_kind_accepted() -> None:
    assert EntryKind("policy_decision") is EntryKind.POLICY_DECISION


def test_unknown_kind_rejected() -> None:
    with pytest.raises(ValueError, match="oscal_emission"):
        EntryKind("oscal_emission")


def test_kind_strings_match_the_console_check_exactly() -> None:
    """0006_ledger.sql: finding | change_record | attestation | policy_decision | breaker_trip."""
    assert [member.value for member in EntryKind] == [
        "finding",
        "change_record",
        "attestation",
        "policy_decision",
        "breaker_trip",
    ]


def test_algorithm_is_the_console_interim_string() -> None:
    assert ALGORITHM == "hmac-sha256-interim"


def test_forbidden_keys_match_handover_section_6_4() -> None:
    assert {
        "quoted_text",
        "artifact_text",
        "narrative",
        "content",
        "sensor_payload",
        "device_payload",
        "identity_payload",
        "playbook_body",
    } == FORBIDDEN_PAYLOAD_KEYS
