"""ConnectWise Manage translator.

Ported from `msp-platform/integrations/connectwise/ticket_normaliser.py`
(``normalise_connectwise_alert``, line 69).

Watch the accessor style. This module uses ``.get(key, default)`` throughout, where the
ScienceLogic normaliser uses ``or`` chains. They are not equivalent: ``.get`` returns a
present-but-falsy value (``""``, ``0``, ``None``) instead of falling through to the
default. Both are reproduced as written.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pil_adapters._axo_compat import iso_to_datetime
from pil_adapters.base import Translation, Translator
from pil_contracts import AlertBody, TenantHint

__all__ = ["ConnectWiseTranslator"]

# Verbatim from ticket_normaliser.py:120-127.
CW_TYPE_MAP = {
    "service": "service",
    "infrastructure": "network",
    "security": "certificate",
    "maintenance": "windows_update",
    "performance": "cpu",
    "backup": "disk",
}


def map_priority_to_severity(priority_id: int | str) -> str:
    """Port of `ticket_normaliser.py:100-114`."""
    try:
        pid = int(priority_id)
    except (ValueError, TypeError):
        return "P3"

    if pid <= 1:
        return "P1"
    elif pid == 2:
        return "P2"
    elif pid == 3:
        return "P3"
    else:
        return "P4"


def map_type_to_category(type_name: str) -> str:
    """Port of `ticket_normaliser.py:117-131`. First substring match wins."""
    type_name_lower = type_name.lower()
    for key, category in CW_TYPE_MAP.items():
        if key in type_name_lower:
            return category
    return "unknown"


class ConnectWiseTranslator(Translator):
    """ConnectWise ticket payload → envelope."""

    source = "connectwise"
    adapter_version = "1.0.0"

    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        # No defensive isinstance checks here, on purpose. AXO does `raw.get("company",
        # {}).get(...)`, which raises AttributeError when `company` is present but null
        # or scalar. A payload that breaks AXO must break PIL the same way, and the
        # parity harness compares raised exceptions as well as outputs.
        company = raw.get("company", {})
        priority = raw.get("priority", {})
        ticket_type = raw.get("type", {})

        alert_id = str(raw.get("id", "unknown"))
        description = raw.get("summary", raw.get("description", ""))

        device_history = raw.get("device_history", [])
        if not isinstance(device_history, list):
            device_history = []

        return Translation(
            event_id=alert_id,
            occurred_at=self._parse_timestamp(raw.get("dateEntered")),
            tenant_hint=TenantHint(
                tenant_id=str(company.get("id", "unknown")),
                tenant_name=str(company.get("identifier", company.get("name", "unknown"))),
            ),
            body=AlertBody(
                alert_id=alert_id,
                device_id=str(raw.get("deviceId", raw.get("configurationId", "unknown"))),
                device_name=str(raw.get("siteName", raw.get("configurationName", "unknown"))),
                severity=map_priority_to_severity(priority.get("id", 3)),
                category=map_type_to_category(ticket_type.get("name", "")),
                message=str(description),
                device_history=tuple(
                    entry for entry in device_history if isinstance(entry, Mapping)
                ),
            ),
        )

    def _parse_timestamp(self, value: Any) -> datetime:
        """Port of `ticket_normaliser.py:168-175`.

        Falsy or unparseable both fall back to the current time, which is why this
        translator needs a clock.
        """
        if not value:
            return self._clock.now()
        return iso_to_datetime(value) or self._clock.now()
