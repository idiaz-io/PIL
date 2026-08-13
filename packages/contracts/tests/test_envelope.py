"""The message envelope: structure, determinism, and the tenant invariant."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from pil_contracts import (
    CURRENT_SCHEMA_VERSION,
    AlertBody,
    Envelope,
    MessageKind,
    SchemaVersion,
    TenantHint,
    format_timestamp,
)

WHEN = datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC)


def make_envelope(**overrides) -> Envelope:
    defaults: dict = {
        "event_id": "evt-1",
        "tenant_id": "tenant-acme",
        "source": "sciencelogic",
        "adapter_version": "1.0.0",
        "occurred_at": WHEN,
        "observed_at": WHEN,
        "body": AlertBody(
            alert_id="a-1",
            device_id="sl1:1001",
            device_name="host-abc",
            severity="P2",
            category="service",
            message="IIS application pool stopped",
        ),
    }
    defaults.update(overrides)
    return Envelope(**defaults)


# ----------------------------------------------------------------------------------
# Timestamps
# ----------------------------------------------------------------------------------


def test_timestamp_has_fixed_precision():
    """A whole second must not serialise differently from a fractional one."""
    whole = datetime(2026, 1, 1, 0, 0, 0, 0, tzinfo=UTC)
    assert format_timestamp(whole) == "2026-01-01T00:00:00.000000Z"
    assert len(format_timestamp(whole)) == len(format_timestamp(WHEN))


def test_timestamp_is_normalised_to_utc():
    elsewhere = WHEN.astimezone(timezone(timedelta(hours=5, minutes=30)))
    assert format_timestamp(elsewhere) == format_timestamp(WHEN)


def test_naive_timestamps_are_rejected():
    """AXO's values are naive-but-actually-UTC. 'Actually' is not good enough here."""
    with pytest.raises(ValueError, match="naive"):
        format_timestamp(datetime(2026, 1, 1))


def test_envelope_rejects_naive_timestamps_on_serialisation():
    envelope = make_envelope(occurred_at=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="naive"):
        envelope.to_canonical_json()


# ----------------------------------------------------------------------------------
# Tenancy — I-5
# ----------------------------------------------------------------------------------


def test_tenant_id_may_not_be_empty():
    with pytest.raises(ValueError, match="I-5"):
        make_envelope(tenant_id="")


def test_tenant_hint_defaults_to_empty_and_is_separate_from_identity():
    envelope = make_envelope()
    assert envelope.tenant_hint == TenantHint()
    assert envelope.tenant_id == "tenant-acme"


def test_tenant_hint_carries_what_the_payload_claimed():
    envelope = make_envelope(
        tenant_id="tenant-acme",
        tenant_hint=TenantHint(tenant_id="42", tenant_name="Acme Corporation"),
    )
    rendered = envelope.to_dict()
    assert rendered["tenant_id"] == "tenant-acme"
    assert rendered["tenant_hint"] == {"tenant_id": "42", "tenant_name": "Acme Corporation"}


# ----------------------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------------------


def test_canonical_form_is_byte_stable():
    envelope = make_envelope()
    first = envelope.to_canonical_json()
    for _ in range(20):
        assert envelope.to_canonical_json() == first


def test_content_hash_ignores_raw_payload_key_order():
    a = make_envelope(raw_payload={"b": 1, "a": 2})
    b = make_envelope(raw_payload={"a": 2, "b": 1})
    assert a.content_hash() == b.content_hash()


def test_content_hash_changes_when_content_changes():
    assert make_envelope().content_hash() != make_envelope(event_id="evt-2").content_hash()


def test_golden_canonical_form():
    """Pinned on purpose. If this changes, every prior signature is invalid (I-9)."""
    envelope = make_envelope(raw_payload={"severity": "4"})
    assert envelope.to_canonical_json() == (
        b'{"adapter_version":"1.0.0",'
        b'"body":{"alert_id":"a-1","category":"service","device_history":[],'
        b'"device_id":"sl1:1001","device_name":"host-abc",'
        b'"message":"IIS application pool stopped","severity":"P2"},'
        b'"event_id":"evt-1","kind":"alert",'
        b'"observed_at":"2026-03-14T15:09:26.535897Z",'
        b'"occurred_at":"2026-03-14T15:09:26.535897Z",'
        b'"raw_payload":{"severity":"4"},'
        b'"schema_version":"1.0","source":"sciencelogic",'
        b'"tenant_hint":{"tenant_id":null,"tenant_name":null},'
        b'"tenant_id":"tenant-acme"}'
    )


# ----------------------------------------------------------------------------------
# Round trip and the version rule
# ----------------------------------------------------------------------------------


def test_round_trip_preserves_everything():
    original = make_envelope(
        tenant_hint=TenantHint(tenant_id="42", tenant_name="Acme"),
        raw_payload={"nested": {"a": [1, 2, 3]}},
    )
    restored = Envelope.from_dict(original.to_dict())
    assert restored.to_canonical_json() == original.to_canonical_json()


def test_unknown_fields_are_ignored_never_rejected():
    """I-7: a v1 consumer must not crash on a v2 message."""
    data = make_envelope().to_dict()
    data["a_field_from_the_future"] = {"anything": [1, 2]}
    data["body"]["another_new_field"] = "hello"

    restored = Envelope.from_dict(data)
    assert restored.body.alert_id == "a-1"


def test_newer_major_version_parses_rather_than_raising():
    data = make_envelope().to_dict()
    data["schema_version"] = "2.0"

    restored = Envelope.from_dict(data)
    assert restored.schema_version == SchemaVersion(2, 0)
    assert restored.schema_version.is_newer_major_than(CURRENT_SCHEMA_VERSION)


def test_unparseable_version_does_not_prevent_parsing():
    data = make_envelope().to_dict()
    data["schema_version"] = "banana"
    assert not Envelope.from_dict(data).schema_version.is_known


def test_missing_required_field_is_malformed_and_does_raise():
    """A missing field is not a version mismatch — it is a broken message."""
    data = make_envelope().to_dict()
    del data["tenant_id"]
    with pytest.raises(ValueError, match="tenant_id"):
        Envelope.from_dict(data)


def test_unknown_kind_is_surfaced_not_guessed_at():
    data = make_envelope().to_dict()
    data["kind"] = "finding"
    with pytest.raises(ValueError, match="I-6"):
        Envelope.from_dict(data)


def test_kind_defaults_to_alert():
    assert make_envelope().kind is MessageKind.ALERT
