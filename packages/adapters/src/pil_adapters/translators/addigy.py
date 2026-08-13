"""Addigy MDM translator.

Ported from `msp-platform/backend/integrations/addigy_adapter.py:43-67`.

Worth knowing about this one: AXO uses the Addigy **policy id** as the customer
identifier (`addigy_adapter.py:58`). An Addigy policy is a device-configuration grouping,
not a customer — several policies belong to one customer, and a policy can be reused
across them. That value lands in ``tenant_hint`` here rather than in ``tenant_id``, and
is preserved defect 3 in ``docs/known-differences.md``.

Everything except ``normalize_alert`` on the source adapter is demo-gated, and its
credential fields are never populated at all — ``self._client_id = ""`` with no loader.
Only the translation is real, and only the translation is ported (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pil_adapters.base import Translation, Translator
from pil_contracts import AlertBody, TenantHint

__all__ = ["AddigyTranslator", "classify_addigy_message"]

# Verbatim from addigy_adapter.py:49. Addigy uses words where SL1 uses numbers.
ADDIGY_SEVERITY_MAP = {
    "critical": "P1",
    "high": "P2",
    "medium": "P3",
    "low": "P4",
    "info": "P4",
}


def classify_addigy_message(message: str) -> str:
    """Classify an Addigy message by keyword. Port of `_classify_addigy_message`."""
    msg = message.lower()
    if any(w in msg for w in ("filevault", "encryption")):
        return "security"
    if any(w in msg for w in ("certificate", "cert", "expires")):
        return "certificate"
    if any(w in msg for w in ("disk", "storage", "space")):
        return "disk"
    if any(w in msg for w in ("cpu", "processor")):
        return "cpu"
    if any(w in msg for w in ("memory", "ram")):
        return "memory"
    if any(w in msg for w in ("patch", "update", "software")):
        return "software"
    return "general"


class AddigyTranslator(Translator):
    """Addigy alert payload → envelope."""

    source = "addigy"
    adapter_version = "1.0.0"

    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        alert_id = str(raw.get("alert_id") or raw.get("id", "unknown"))
        device_id = f"addigy:{raw.get('agentid') or raw.get('device_id', 'unknown')}"
        device_name = raw.get("device_name") or raw.get("hostname") or device_id
        message = raw.get("alert_message") or raw.get("message") or raw.get("description", "")

        severity_str = str(raw.get("severity", "medium")).lower()
        severity = ADDIGY_SEVERITY_MAP.get(severity_str, "P3")

        return Translation(
            event_id=alert_id,
            # timestamp=datetime.utcnow() at line 64, unconditionally.
            occurred_at=self._clock.now(),
            tenant_hint=TenantHint(
                # An MDM policy id standing in for a customer id. See module docstring.
                tenant_id=str(raw.get("policy_id") or raw.get("client_id", "unknown")),
                tenant_name=str(raw.get("policy_name") or raw.get("client_name", "")),
            ),
            body=AlertBody(
                alert_id=alert_id,
                device_id=device_id,
                device_name=str(device_name),
                severity=severity,
                category=classify_addigy_message(message),
                message=str(message),
            ),
        )
