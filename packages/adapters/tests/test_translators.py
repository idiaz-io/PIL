"""Translator behaviour, including the AXO quirks that are reproduced on purpose."""

from datetime import UTC, datetime

import pytest

from pil_adapters import (
    AdapterConfig,
    AddigyTranslator,
    ConnectWiseTranslator,
    FleetTranslator,
    FrozenClock,
    LegacyTranslator,
    ScienceLogicTranslator,
    SL1HealingTranslator,
)
from pil_adapters.translators.connectwise import map_priority_to_severity, map_type_to_category
from pil_adapters.translators.fleet import classify_policy
from pil_adapters.translators.sciencelogic import normalise_category, normalise_severity
from pil_adapters.translators.sl1_healing import classify_message

CONFIG = AdapterConfig(tenant_id="tenant-acme")
CLOCK = FrozenClock(datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC))


# ----------------------------------------------------------------------------------
# ScienceLogic webhook
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0", "P4"), ("2", "P3"), ("4", "P2"), ("5", "P1"), ("emergency", "P1"), ("MAJOR", "P3")],
)
def test_sl_severity_map(raw, expected):
    assert normalise_severity(raw) == expected


def test_sl_severity_passes_through_existing_p_codes():
    assert normalise_severity("p1") == "P1"


def test_sl_severity_defaults_to_p3():
    assert normalise_severity("") == "P3"
    assert normalise_severity("something-new") == "P3"


def test_sl_category_falls_back_to_the_description():
    """An unrecognised category is still classified from the message text."""
    assert normalise_category("nonsense", "the disk is full") == "disk"


def test_sl_category_prefers_the_category_over_the_description():
    assert normalise_category("cpu", "the disk is full") == "cpu"


def test_sl_category_unknown_when_nothing_matches():
    assert normalise_category("", "") == "unknown"


def test_sciencelogic_uses_or_chains_so_empty_values_fall_through():
    """`or` chains, unlike `.get` defaults, skip a present-but-empty value."""
    envelope = ScienceLogicTranslator(CONFIG, CLOCK).translate({"alert_id": "", "event_id": "e-9"})
    assert envelope.body.alert_id == "e-9"


def test_sciencelogic_reads_a_nested_device_name():
    envelope = ScienceLogicTranslator(CONFIG, CLOCK).translate({"device": {"name": "db01"}})
    assert envelope.body.device_name == "db01"


def test_sciencelogic_falls_back_to_the_clock_when_no_timestamp_field_exists():
    """AXO calls datetime.utcnow() here, which is why the clock is injected."""
    envelope = ScienceLogicTranslator(CONFIG, CLOCK).translate({"id": "1"})
    assert envelope.occurred_at == CLOCK.instant


def test_sciencelogic_prefers_an_iso_timestamp_from_the_payload():
    envelope = ScienceLogicTranslator(CONFIG, CLOCK).translate(
        {"id": "1", "timestamp": "2020-01-02T03:04:05Z"}
    )
    assert envelope.occurred_at == datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_sciencelogic_falls_back_to_the_clock_on_an_unparseable_timestamp():
    envelope = ScienceLogicTranslator(CONFIG, CLOCK).translate({"id": "1", "timestamp": "banana"})
    assert envelope.occurred_at == CLOCK.instant


# ----------------------------------------------------------------------------------
# ConnectWise
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pid", "expected"), [(0, "P1"), (1, "P1"), (2, "P2"), (3, "P3"), (9, "P4"), ("x", "P3")]
)
def test_cw_priority_map(pid, expected):
    assert map_priority_to_severity(pid) == expected


def test_cw_type_map_matches_on_substring():
    assert map_type_to_category("Managed Services") == "service"
    assert map_type_to_category("nothing relevant") == "unknown"


def test_connectwise_uses_get_defaults_so_empty_values_are_kept():
    """The mirror image of the ScienceLogic test above. Do not unify these."""
    envelope = ConnectWiseTranslator(CONFIG, CLOCK).translate({"id": "", "company": {}})
    assert envelope.body.alert_id == "", "`.get` keeps a present-but-empty value"


def test_connectwise_maps_company_to_the_tenant_hint():
    envelope = ConnectWiseTranslator(CONFIG, CLOCK).translate(
        {"id": 5, "company": {"id": 100, "identifier": "AcmeCorp"}}
    )
    assert envelope.tenant_hint.tenant_id == "100"
    assert envelope.tenant_hint.tenant_name == "AcmeCorp"
    assert envelope.tenant_id == "tenant-acme"


def test_connectwise_raises_when_company_is_null_exactly_as_axo_does():
    """A payload that breaks AXO must break PIL identically."""
    with pytest.raises(AttributeError):
        ConnectWiseTranslator(CONFIG, CLOCK).translate({"id": "1", "company": None})


# ----------------------------------------------------------------------------------
# Fleet
# ----------------------------------------------------------------------------------


def test_fleet_classify_order_puts_encryption_before_disk():
    """'disk encryption' is security, not disk, because that branch runs first."""
    assert classify_policy("Disk encryption enabled") == "security"
    assert classify_policy("Disk space above 10%") == "disk"


def test_fleet_unwraps_a_batch_to_its_first_policy():
    envelope = FleetTranslator(CONFIG, CLOCK).translate(
        {
            "failing_policies": [
                {"host_uuid": "aaaabbbbcccc", "policy_name": "First", "team_name": "Acme"},
                {"host_uuid": "ddddeeeeffff", "policy_name": "Second"},
            ]
        }
    )
    assert "First" in envelope.body.message
    assert "Second" not in envelope.body.message


def test_fleet_raw_payload_holds_the_unwrapped_policy_not_the_batch():
    """AXO rebinds `raw` before storing it (fleet_healing_adapter.py:116-119,151)."""
    envelope = FleetTranslator(CONFIG, CLOCK).translate(
        {"failing_policies": [{"host_uuid": "aaaabbbbcccc", "policy_name": "First"}]}
    )
    assert "failing_policies" not in envelope.raw_payload
    assert envelope.raw_payload["policy_name"] == "First"


def test_fleet_empty_batch_is_left_alone():
    envelope = FleetTranslator(CONFIG, CLOCK).translate({"failing_policies": []})
    assert "failing_policies" in envelope.raw_payload


def test_fleet_bumps_severity_for_critical_policies():
    plain = FleetTranslator(CONFIG, CLOCK).translate({"host_uuid": "u" * 12, "policy_name": "Ntp"})
    critical = FleetTranslator(CONFIG, CLOCK).translate(
        {"host_uuid": "u" * 12, "policy_name": "FileVault enabled"}
    )
    assert plain.body.severity == "P3"
    assert critical.body.severity == "P2"


def test_fleet_team_name_lands_in_the_hint_not_the_tenant():
    envelope = FleetTranslator(CONFIG, CLOCK).translate(
        {"host_uuid": "u" * 12, "policy_name": "Ntp", "team_name": "Acme"}
    )
    assert envelope.tenant_hint.tenant_id == "Acme"
    assert envelope.tenant_id == "tenant-acme"


# ----------------------------------------------------------------------------------
# SL1 healing adapter — the *other* ScienceLogic translation
# ----------------------------------------------------------------------------------


def test_sl1_healing_and_sciencelogic_disagree_and_both_are_correct():
    """Two live SL1 translations in AXO. Collapsing them would change behaviour."""
    raw = {"id": "1", "severity": "4", "message": "disk full"}
    webhook = ScienceLogicTranslator(CONFIG, CLOCK).translate(raw)
    healing = SL1HealingTranslator(CONFIG, CLOCK).translate(raw)

    assert webhook.body.severity == "P2"
    assert healing.body.severity == "P4"


def test_sl1_healing_synthesises_a_severity_for_unmapped_codes():
    """An SL1 severity of "9" becomes the literal "P9". Preserved as written."""
    envelope = SL1HealingTranslator(CONFIG, CLOCK).translate({"id": "1", "severity": "9"})
    assert envelope.body.severity == "P9"


def test_sl1_classify_order_puts_disk_before_service():
    assert classify_message("disk service failed") == "disk"
    assert classify_message("service failed") == "service"


def test_sl1_device_name_falls_back_to_the_device_id():
    envelope = SL1HealingTranslator(CONFIG, CLOCK).translate({"id": "1", "device_id": "77"})
    assert envelope.body.device_name == "sl1:77"


# ----------------------------------------------------------------------------------
# Addigy
# ----------------------------------------------------------------------------------


def test_addigy_uses_a_policy_id_as_the_tenant_hint():
    """An Addigy policy is not a customer. Preserved defect 3."""
    envelope = AddigyTranslator(CONFIG, CLOCK).translate(
        {"id": "1", "policy_id": "pol-123", "policy_name": "Standard Mac"}
    )
    assert envelope.tenant_hint.tenant_id == "pol-123"
    assert envelope.tenant_id == "tenant-acme"


@pytest.mark.parametrize(
    ("severity", "expected"), [("critical", "P1"), ("HIGH", "P2"), ("nonsense", "P3")]
)
def test_addigy_severity_map(severity, expected):
    envelope = AddigyTranslator(CONFIG, CLOCK).translate({"id": "1", "severity": severity})
    assert envelope.body.severity == expected


def test_addigy_defaults_to_medium_when_severity_is_absent():
    assert AddigyTranslator(CONFIG, CLOCK).translate({"id": "1"}).body.severity == "P3"


# ----------------------------------------------------------------------------------
# Legacy fallback
# ----------------------------------------------------------------------------------


def test_legacy_raises_on_an_unparseable_timestamp_unlike_every_other_translator():
    """webhook.py:34 has no try/except. This turns the request into a 500."""
    with pytest.raises(ValueError, match=r"Invalid isoformat|fromisoformat"):
        LegacyTranslator(CONFIG, CLOCK).translate({"id": "1", "timestamp": "banana"})


def test_legacy_uses_the_clock_when_no_timestamp_key_is_present():
    assert LegacyTranslator(CONFIG, CLOCK).translate({"id": "1"}).occurred_at == CLOCK.instant


def test_legacy_keeps_present_but_empty_values():
    envelope = LegacyTranslator(CONFIG, CLOCK).translate({"alert_id": "", "id": "fallback"})
    assert envelope.body.alert_id == ""
