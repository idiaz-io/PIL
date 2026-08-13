"""ScienceLogic SL1 webhook translator.

Ported from `msp-platform/integrations/sciencelogic/normaliser.py`, which is the
best-tested logic in AXO (`tests/test_normaliser.py`). The mapping tables and the
field-precedence chains are reproduced exactly, including their quirks.

One deliberate difference: ``client_id`` and ``client_name`` came out of the payload in
AXO (`normaliser.py:143-154`). Here they become ``tenant_hint`` — evidence about what the
payload claimed — while the envelope's ``tenant_id`` comes from adapter configuration.
See ADR-0004.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pil_adapters._axo_compat import epoch_to_datetime, iso_to_datetime
from pil_adapters.base import Translation, Translator
from pil_contracts import AlertBody, TenantHint

__all__ = ["SL_CATEGORY_MAP", "SL_SEVERITY_MAP", "ScienceLogicTranslator"]

# Verbatim from normaliser.py:12-25. SL1 uses numeric severity levels.
SL_SEVERITY_MAP = {
    "0": "P4",  # Healthy / informational
    "1": "P4",  # Notice
    "2": "P3",  # Minor
    "3": "P3",  # Major
    "4": "P2",  # Critical
    "5": "P1",  # Emergency
    "healthy": "P4",
    "notice": "P4",
    "minor": "P3",
    "major": "P3",
    "critical": "P2",
    "emergency": "P1",
}

# Verbatim from normaliser.py:28-48. Insertion order is load-bearing: the substring
# scan below returns the first key that matches, so reordering this dict changes
# behaviour for messages that mention more than one keyword.
SL_CATEGORY_MAP = {
    "service": "service",
    "process": "service",
    "disk": "disk",
    "storage": "disk",
    "filesystem": "disk",
    "certificate": "certificate",
    "ssl": "certificate",
    "cpu": "cpu",
    "processor": "cpu",
    "memory": "memory",
    "ram": "memory",
    "network": "network",
    "interface": "network",
    "connectivity": "network",
    "update": "windows_update",
    "patch": "windows_update",
    "account": "account",
    "lockout": "account",
    "authentication": "account",
}


def normalise_severity(raw_severity: str) -> str:
    """Map an SL1 severity to P1–P4. Port of `normaliser.py:51-59`."""
    if not raw_severity:
        return "P3"
    severity_str = str(raw_severity).lower().strip()
    if severity_str in ("p1", "p2", "p3", "p4"):
        return severity_str.upper()
    return SL_SEVERITY_MAP.get(severity_str, "P3")


def normalise_category(raw_category: str, description: str = "") -> str:
    """Map an SL1 alert type to a category. Port of `normaliser.py:62-83`.

    Three passes, in order: exact match, substring of the category, then substring of
    the description. The description fallback means an unrecognised category can still
    be classified from the message text.
    """
    if not raw_category:
        raw_category = ""
    cat_lower = raw_category.lower().strip()

    if cat_lower in SL_CATEGORY_MAP:
        return SL_CATEGORY_MAP[cat_lower]

    for key, value in SL_CATEGORY_MAP.items():
        if key in cat_lower:
            return value

    desc_lower = description.lower()
    for key, value in SL_CATEGORY_MAP.items():
        if key in desc_lower:
            return value

    return "unknown"


class ScienceLogicTranslator(Translator):
    """SL1 webhook payload → envelope."""

    source = "sciencelogic"
    adapter_version = "1.0.0"

    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        # Every chain below uses `or`, not `.get(key, default)` — so an empty string or
        # an explicit null falls through to the next candidate. That is AXO's behaviour
        # and differs from the ConnectWise and legacy translators, which use `.get`
        # defaults and therefore keep a falsy value. Do not "tidy" one into the other.
        alert_id = str(
            raw.get("alert_id")
            or raw.get("event_id")
            or raw.get("xid")
            or raw.get("id")
            or "unknown"
        )

        device_id = str(raw.get("device_id") or raw.get("did") or raw.get("entity_id") or "unknown")
        device_name = (
            raw.get("device_name")
            or raw.get("hostname")
            or raw.get("entity_name")
            or (raw.get("device", {}).get("name") if isinstance(raw.get("device"), dict) else None)
            or "unknown"
        )

        # In AXO these two populated StandardAlert.client_id / .client_name. I-5 says
        # the tenant may not come from input, so they become a hint (ADR-0004).
        hint_tenant_id = str(
            raw.get("client_id") or raw.get("org_id") or raw.get("organization_id") or "unknown"
        )
        hint_tenant_name = (
            raw.get("client_name") or raw.get("organization") or raw.get("org_name") or "unknown"
        )

        raw_severity = str(
            raw.get("severity") or raw.get("priority") or raw.get("event_severity") or "P3"
        )
        severity = normalise_severity(raw_severity)

        raw_category = str(
            raw.get("category")
            or raw.get("alert_type")
            or raw.get("event_type")
            or raw.get("policy_name")
            or ""
        )
        description = str(
            raw.get("description")
            or raw.get("message")
            or raw.get("event_message")
            or raw.get("details")
            or ""
        )
        category = normalise_category(raw_category, description)

        device_history = raw.get("device_history", [])
        if not isinstance(device_history, list):
            device_history = []

        return Translation(
            event_id=alert_id,
            occurred_at=self._normalise_timestamp(raw),
            tenant_hint=TenantHint(
                tenant_id=hint_tenant_id,
                tenant_name=str(hint_tenant_name),
            ),
            body=AlertBody(
                alert_id=alert_id,
                device_id=device_id,
                device_name=str(device_name),
                severity=severity,
                category=category,
                # AXO's Pydantic StandardAlert calls this `description`; the dataclass
                # one calls it `message`. The envelope has a single name.
                message=description,
                device_history=tuple(
                    entry for entry in device_history if isinstance(entry, Mapping)
                ),
            ),
        )

    def _normalise_timestamp(self, raw: Mapping[str, Any]) -> datetime:
        """Port of `normaliser.py:86-104`.

        The final fallback is where AXO calls ``datetime.utcnow()``, which is why this
        translator needs a clock. Preserved defect 4 in ``docs/known-differences.md``.
        """
        for field in ("timestamp", "event_time", "created_at", "time"):
            if raw.get(field):
                parsed = iso_to_datetime(raw[field])
                if parsed is not None:
                    return parsed

        for field in ("epoch", "event_epoch", "unix_time"):
            if raw.get(field):
                parsed = epoch_to_datetime(raw[field])
                if parsed is not None:
                    return parsed

        return self._clock.now()
