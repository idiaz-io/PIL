"""Legacy fallback translator.

Ported from `msp-platform/backend/routes/webhook.py:22-37` (``_legacy_normalise``), which
handles any webhook whose ``platform`` field is not sciencelogic, connectwise or fleet.

It is the least principled of the six and the easiest to overlook, since it lives in a
route file rather than an integrations package. It is also the only one that will raise
on a malformed timestamp instead of falling back, and that difference is load-bearing:
an unparseable ``timestamp`` turns the webhook into a 500 rather than an accepted alert.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pil_adapters._axo_compat import as_utc
from pil_adapters.base import Translation, Translator
from pil_contracts import AlertBody, TenantHint

__all__ = ["LegacyTranslator"]


class LegacyTranslator(Translator):
    """Unrecognised webhook payload → envelope."""

    source = "legacy"
    adapter_version = "1.0.0"

    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        # `.get(key, default)` throughout, so a present-but-empty value is kept rather
        # than falling through — unlike the ScienceLogic normaliser's `or` chains.
        alert_id = str(raw.get("alert_id", raw.get("id", "unknown")))

        device_history = raw.get("device_history", [])
        if not isinstance(device_history, list):
            device_history = []

        return Translation(
            event_id=alert_id,
            occurred_at=self._parse_timestamp(raw),
            tenant_hint=TenantHint(
                tenant_id=str(raw.get("client_id", raw.get("org_id", "unknown"))),
                tenant_name=str(raw.get("client_name", raw.get("organization", "unknown"))),
            ),
            body=AlertBody(
                alert_id=alert_id,
                device_id=str(raw.get("device_id", raw.get("did", "unknown"))),
                device_name=str(raw.get("device_name", raw.get("hostname", "unknown"))),
                severity=str(raw.get("severity", raw.get("priority", "P3"))),
                category=str(raw.get("category", raw.get("alert_type", "unknown"))),
                message=str(raw.get("description", raw.get("message", ""))),
                device_history=tuple(
                    entry for entry in device_history if isinstance(entry, Mapping)
                ),
            ),
        )

    def _parse_timestamp(self, raw: Mapping[str, Any]) -> datetime:
        """Port of `webhook.py:34`.

        ``datetime.fromisoformat(raw["timestamp"]) if "timestamp" in raw else utcnow()``

        Note there is no try/except. A present-but-unparseable timestamp raises, and the
        request becomes a 500. Every other translator swallows it and falls back to the
        current time. That inconsistency is AXO's, and it is preserved.
        """
        if "timestamp" in raw:
            return as_utc(datetime.fromisoformat(raw["timestamp"]))
        return self._clock.now()
