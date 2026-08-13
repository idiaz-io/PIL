"""Redaction — IDI-195 D1.

The test that matters most is
:func:`test_credential_patterns_are_byte_identical_to_axos`. This module exists to replace
two existing redactors, and a replacement that redacts *differently* is worse than the
duplication: the corpus captured before the change stops matching the corpus captured
after, and nobody can tell which half is right.
"""

from __future__ import annotations

import re

import pytest

from pil_contracts import (
    REDACTED,
    Classification,
    classify_key,
    redact,
    redact_text,
)

SALT = b"a-test-salt-not-a-real-one"


# ----------------------------------------------------------------------------------
# Compatibility with what it replaces
# ----------------------------------------------------------------------------------


def test_credential_patterns_are_byte_identical_to_axos():
    """The two patterns must stay exactly the pair both AXO redactors already use.

    Sources: ``apps/exoagent/internal/evidence/evidence.go:13-16`` and
    ``backend/services/pil_capture.py:67``. If this module strips more or less than they
    did, adopting it silently changes what is already on disk in the corpus.
    """
    from pil_contracts.redaction import _CREDENTIAL_PATTERNS

    assert [p.pattern for p in _CREDENTIAL_PATTERNS] == [
        r"(?i)(password|secret|token|key|credential|api[_-]?key)\s*[=:]\s*\S+",
        r"\b[A-Za-z0-9+/]{40,}={0,2}\b",
    ]


def test_the_replacement_marker_matches_axos():
    """`evidence.go` and `pil_capture.py` both write this exact string."""
    assert REDACTED == "[REDACTED]"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("password=hunter2", REDACTED),
        ("password: hunter2", REDACTED),
        ("API_KEY = abc123", REDACTED),
        ("api-key:xyz", REDACTED),
        ("token=eyJhbGciOi", REDACTED),
        # The long-base64 rule, for credentials that carry no label.
        ("A" * 40, REDACTED),
        ("QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9w", REDACTED),
    ],
)
def test_credentials_are_stripped_from_free_text(text, expected):
    assert redact_text(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "SQL Server stopped on PROD-DB-01",
        "disk full",
        # 36 characters — a UUID must survive the 40-char base64 rule, or every device
        # id in every payload becomes [REDACTED] and the corpus is worthless.
        "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        "P1",
        "",
    ],
)
def test_ordinary_text_is_left_alone(text):
    assert redact_text(text) == text


# ----------------------------------------------------------------------------------
# Classification
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("password", Classification.SECRET),
        ("API_KEY", Classification.SECRET),
        ("Authorization", Classification.SECRET),
        ("private_key", Classification.SECRET),
        ("hostname", Classification.CONFIDENTIAL),
        ("device_name", Classification.CONFIDENTIAL),
        ("client_name", Classification.CONFIDENTIAL),
        ("yname", Classification.CONFIDENTIAL),
        ("email", Classification.CONFIDENTIAL),
        ("ip_address", Classification.CONFIDENTIAL),
        ("severity", Classification.PUBLIC),
        ("policy_name", Classification.PUBLIC),
    ],
)
def test_keys_classify_by_name(key, expected):
    assert classify_key(key) is expected


def test_classification_is_case_insensitive():
    assert classify_key("PASSWORD") is classify_key("password")


def test_a_secret_key_is_stripped_whatever_its_value_looks_like():
    """The patterns only fire on text that advertises itself.

    A bare password looks like any other word, so the key name has to carry it.
    """
    result = redact({"password": "correcthorse", "api_key": 12345})
    assert result.payload == {"password": REDACTED, "api_key": REDACTED}
    assert result.held_secrets


def test_a_credential_under_an_unexpected_key_is_still_caught():
    """Second line of defence: every string is stripped whatever its key classified as."""
    result = redact({"notes": "the password=hunter2 is in the vault"})
    assert REDACTED in result.payload["notes"]
    assert "hunter2" not in result.payload["notes"]
    assert result.held_secrets


def test_marks_report_where_things_were_found():
    result = redact({"outer": {"password": "x", "severity": "4"}})
    assert result.marks == {"$.outer.password": Classification.SECRET}
    assert result.classifications == frozenset({Classification.SECRET})


def test_a_clean_payload_reports_no_marks():
    result = redact({"severity": "4", "message": "disk full", "count": 3})
    assert result.marks == {}
    assert not result.held_secrets


# ----------------------------------------------------------------------------------
# Structure preservation — why the translators still work on a scrubbed corpus
# ----------------------------------------------------------------------------------


def test_structure_is_preserved_exactly():
    """Same keys, same nesting, same types, same empty/null distinctions.

    The translators branch on which keys are present and on whether a value is empty
    (`sciencelogic/normaliser.py` and the Fleet unwrap in particular), so a scrubber that
    dropped an empty string or collapsed a null would change what the corpus tests
    without changing any test.
    """
    payload = {
        "a": None,
        "b": "",
        "c": [],
        "d": {},
        "e": [1, 2, {"f": None}],
        "g": False,
        "h": 0,
        "i": 1.5,
    }
    assert redact(payload).payload == payload


def test_nested_lists_and_dicts_are_walked():
    result = redact({"failing_policies": [{"password": "x"}, {"severity": "4"}]})
    assert result.payload == {"failing_policies": [{"password": REDACTED}, {"severity": "4"}]}
    assert result.marks == {"$.failing_policies[0].password": Classification.SECRET}


# ----------------------------------------------------------------------------------
# Pseudonymisation
# ----------------------------------------------------------------------------------


def test_identifiers_are_pseudonymised_only_when_a_salt_is_given():
    payload = {"hostname": "prod-db-01"}

    unsalted = redact(payload)
    assert unsalted.payload["hostname"] == "prod-db-01", "no salt means leave it, but mark it"
    assert unsalted.marks == {"$.hostname": Classification.CONFIDENTIAL}

    salted = redact(payload, salt=SALT)
    assert salted.payload["hostname"] != "prod-db-01"
    assert salted.payload["hostname"].startswith("host-")


def test_pseudonyms_are_stable_so_joins_survive():
    """Two payloads naming the same host must still name the same host afterwards.

    Without this, a corpus loses every relationship between payloads and device_history
    stops lining up with the alert it belongs to.
    """
    first = redact({"hostname": "prod-db-01"}, salt=SALT).payload["hostname"]
    second = redact({"device_name": "prod-db-01"}, salt=SALT).payload["device_name"]
    assert first == second


def test_pseudonyms_differ_under_a_different_salt():
    a = redact({"hostname": "prod-db-01"}, salt=b"salt-one").payload["hostname"]
    b = redact({"hostname": "prod-db-01"}, salt=b"salt-two").payload["hostname"]
    assert a != b


def test_uri_shaped_tenant_references_keep_their_shape():
    """SL1 names an organisation as a URI and AXO splits it on "/" (`sl_poller.py:307`).

    Replacing the whole string would delete the edge case the corpus exists to capture —
    preserved defect 1 in docs/known-differences.md is exactly this path.
    """
    result = redact({"organization": "/api/organization/42"}, salt=SALT)
    value = result.payload["organization"]
    assert value.startswith("/api/organization/")
    assert value != "/api/organization/42"
    assert value.rsplit("/", 1)[-1].startswith("org-")


def test_a_secret_is_never_pseudonymised():
    """There is no use for a stable fake password, and holding one invites trusting it."""
    result = redact({"password": "hunter2"}, salt=SALT)
    assert result.payload["password"] == REDACTED


def test_pseudonyms_do_not_leak_the_original():
    original = "prod-db-01"
    value = redact({"hostname": original}, salt=SALT).payload["hostname"]
    assert original not in value
    assert re.fullmatch(r"host-[0-9a-f]{12}", value)


# ----------------------------------------------------------------------------------
# Envelope.redacted — opt-in, and opt-in for a reason
# ----------------------------------------------------------------------------------


def _envelope(raw):
    from datetime import UTC, datetime

    from pil_contracts import AlertBody, Envelope

    return Envelope(
        event_id="e-1",
        tenant_id="tenant-acme",
        source="sciencelogic",
        adapter_version="1.0.0",
        occurred_at=datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC),
        observed_at=datetime(2026, 3, 14, 15, 9, 26, tzinfo=UTC),
        body=AlertBody(
            alert_id="a-1",
            device_id="d-1",
            device_name="db01",
            severity="P1",
            category="service",
            message="stopped",
        ),
        raw_payload=raw,
    )


def test_redacted_strips_credentials_from_raw_payload():
    envelope = _envelope({"password": "hunter2", "severity": "4"})
    clean, result = envelope.redacted()

    assert clean.raw_payload == {"password": REDACTED, "severity": "4"}
    assert result.held_secrets


def test_redacted_leaves_the_original_untouched():
    """Envelopes are frozen and redaction returns a copy.

    A caller holding the original for a parity comparison must not find it mutated
    underneath them.
    """
    envelope = _envelope({"password": "hunter2"})
    envelope.redacted()
    assert envelope.raw_payload == {"password": "hunter2"}


def test_redacted_does_not_touch_the_body():
    """Body fields are the translated result. Rewriting them changes the message.

    Redaction protects what the vendor sent, not what we concluded from it.
    """
    envelope = _envelope({})
    clean, _ = envelope.redacted()
    assert clean.body == envelope.body


def test_construction_does_not_redact():
    """The guarantee that keeps the migration honest.

    AXO stores raw_payload untouched. If building an Envelope redacted it, PIL's output
    would differ from AXO's on every payload holding a credential, parity would fail, and
    the fix would look like a porting bug rather than the deliberate improvement it is.
    I-10: a migration that also improves behaviour is unreviewable.
    """
    envelope = _envelope({"password": "hunter2"})
    assert envelope.raw_payload == {"password": "hunter2"}


def test_confidential_key_list_matches_axos_verbatim():
    """Moving ownership must not change output.

    AXO's `pil_capture.py:75-113` is the incumbent and is tuned to these vendors — `yname`
    and `aligned_resource_name` are ScienceLogic field names that a generic list would stop
    protecting. This is that mapping, copied rather than imported: PIL may not import a
    product (I-3), so the drift guard has to be a literal.

    Changing the list is allowed. Changing it in the same commit that moves it is not.
    """
    from pil_contracts.redaction import _CONFIDENTIAL_KEYS

    assert _CONFIDENTIAL_KEYS == {
        "hostname": "host",
        "host_name": "host",
        "device_name": "host",
        "element_name": "host",
        "aligned_resource_name": "host",
        "yname": "host",
        "fqdn": "host",
        "computer_name": "host",
        "display_name": "host",
        "name": "name",
        "ip": "ip",
        "ip_address": "ip",
        "primary_ip": "ip",
        "public_ip": "ip",
        "private_ip": "ip",
        "mac": "mac",
        "mac_address": "mac",
        "serial": "serial",
        "serial_number": "serial",
        "uuid": "uuid",
        "host_uuid": "uuid",
        "organization": "org",
        "organization_name": "org",
        "org_name": "org",
        "client_name": "org",
        "company_name": "org",
        "identifier": "org",
        "email": "email",
        "user": "user",
        "username": "user",
        "owner": "user",
        "contact": "user",
    }
