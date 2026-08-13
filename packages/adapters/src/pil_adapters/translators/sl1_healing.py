"""ScienceLogic SL1 healing-adapter translator.

Ported from `msp-platform/backend/integrations/sl1_adapter.py:44-68`.

This is a **second, different** SL1 translation, not a duplicate of the webhook
normaliser in :mod:`pil_adapters.translators.sciencelogic`. They disagree about almost
everything — different field precedence, a different severity map, and category derived
from the message text rather than from a category field. Both are live in AXO today, on
different paths. Both are ported; neither is "the" SL1 translator.

The surrounding adapter is constructed with ``demo_mode=True`` unconditionally
(`orchestrator_v2.py:61`), but ``normalize_alert`` is the one method that never branches
on it — which is why this translation is real and portable while the rest of that class
is not (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pil_adapters.base import Translation, Translator
from pil_contracts import AlertBody, TenantHint

__all__ = ["SL1HealingTranslator", "classify_message"]

# Verbatim from sl1_adapter.py:51. Note it is much smaller than the webhook
# normaliser's map, and maps "critical" to P1 where the other maps it to P2.
SL1_SEVERITY_MAP = {"1": "P1", "2": "P2", "3": "P3", "4": "P4", "critical": "P1"}


def classify_message(message: str) -> str:
    """Classify an SL1 message by keyword. Port of `_classify_message`.

    Order matters: "disk service failed" classifies as disk, because that test runs
    before the service one.
    """
    msg = message.lower()
    if any(w in msg for w in ("cpu", "processor", "load average")):
        return "cpu"
    if any(w in msg for w in ("memory", "ram", "swap")):
        return "memory"
    if any(w in msg for w in ("disk", "filesystem", "inode", "/var", "/tmp")):
        return "disk"
    if any(w in msg for w in ("service", "daemon", "stopped", "failed", "crash")):
        return "service"
    if any(w in msg for w in ("certificate", "cert", "ssl", "tls", "expires")):
        return "certificate"
    if any(w in msg for w in ("network", "interface", "unreachable", "ping", "latency")):
        return "network"
    if any(w in msg for w in ("application pool", "apppool", "iis")):
        return "apppool"
    return "general"


class SL1HealingTranslator(Translator):
    """SL1 event payload → envelope, via the healing adapter's mapping."""

    source = "sl1"
    adapter_version = "1.0.0"

    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        alert_id = str(raw.get("event_id") or raw.get("alert_id") or raw.get("id", "unknown"))
        device_id = f"sl1:{raw.get('device_id', raw.get('entity_id', 'unknown'))}"
        device_name = raw.get("device_name") or raw.get("entity_name") or device_id
        message = raw.get("message") or raw.get("event_message") or raw.get("description", "")

        severity_code = str(raw.get("severity", raw.get("event_severity", "3")))
        # The fallback synthesises a severity string rather than defaulting to P3 — an
        # SL1 severity of "9" becomes the literal "P9". Preserved as written.
        severity = SL1_SEVERITY_MAP.get(severity_code, f"P{severity_code}")

        return Translation(
            event_id=alert_id,
            # timestamp=datetime.utcnow() at line 66, unconditionally.
            occurred_at=self._clock.now(),
            tenant_hint=TenantHint(
                tenant_id=str(raw.get("org_id", raw.get("client_id", "unknown"))),
                tenant_name=str(raw.get("org_name", raw.get("client_name", ""))),
            ),
            body=AlertBody(
                alert_id=alert_id,
                device_id=device_id,
                device_name=str(device_name),
                severity=severity,
                category=classify_message(message),
                message=str(message),
            ),
        )
