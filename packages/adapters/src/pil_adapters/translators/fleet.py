"""FleetDM policy-violation translator.

Ported from `msp-platform/backend/integrations/fleet_healing_adapter.py:108-152`.

Fleet is the one source where AXO's whole adapter is real rather than demo-gated, and
the 764-line file it comes from has **no tests at all**. This port and its fixtures are
the first coverage that logic has had.

Two behaviours here are faithful reproductions of things worth knowing about:

* Batch payloads are unwrapped to their **first** policy and the rest are silently
  dropped (`fleet_healing_adapter.py:116-119`).
* ``raw_payload`` then holds the unwrapped policy rather than the payload as received,
  because AXO rebinds the local name before storing it (line 151).

The ``await self._ensure_config()`` call at line 113 is deliberately not ported: it
loads Fleet credentials from the database and has no effect on the translation.
Phase A is translate-only (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pil_adapters.base import Translation, Translator
from pil_contracts import AlertBody, TenantHint

__all__ = ["FleetTranslator", "classify_policy"]

#: Policy-name keywords that bump severity from P3 to P2.
#: Verbatim from `fleet_healing_adapter.py:138`.
CRITICAL_POLICY_WORDS = ("critical", "encrypt", "filevault", "disk", "antivirus", "edr")


def classify_policy(policy_name: str) -> str:
    """Map a Fleet policy name to a category. Port of `_classify_policy`.

    Order matters and is preserved: "disk encryption" hits the ``encrypt`` branch and
    classifies as security, not disk, because that test runs first.
    """
    p = policy_name.lower()
    if any(w in p for w in ("filevault", "encrypt", "bitlocker")):
        return "security"
    if any(w in p for w in ("disk", "storage", "space")):
        return "disk"
    if any(w in p for w in ("patch", "update", "software", "os version")):
        return "software"
    if any(w in p for w in ("antivirus", "edr", "crowdstrike", "defender", "malware")):
        return "security"
    if any(w in p for w in ("cpu", "processor", "load")):
        return "cpu"
    if any(w in p for w in ("memory", "ram")):
        return "memory"
    if any(w in p for w in ("firewall", "network", "ssh")):
        return "network"
    if any(w in p for w in ("certificate", "cert", "ssl", "tls")):
        return "certificate"
    return "compliance"


class FleetTranslator(Translator):
    """Fleet policy-violation payload → envelope."""

    source = "fleet"
    adapter_version = "1.0.0"

    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        # Batch unwrap. Everything after the first failing policy is discarded, and the
        # unwrapped entry becomes what raw_payload carries.
        payload: Mapping[str, Any] = raw
        if "failing_policies" in raw:
            policies = raw["failing_policies"]
            if policies:
                payload = policies[0]

        host_uuid = payload.get("host_uuid") or payload.get("uuid", "unknown")
        host_name = payload.get("host_name") or payload.get("hostname") or host_uuid
        policy_name = payload.get("policy_name") or payload.get("policy", "Unknown policy")
        policy_id = payload.get("policy_id", "")
        team_name = payload.get("team_name") or payload.get("team", "")

        category = classify_policy(policy_name)

        # Verbatim from line 135. The wording is deliberate in the original — it states
        # what is wrong rather than naming the policy, because the message is fed to a
        # model downstream. Reword it and the reasoning engine's behaviour changes.
        message = (
            f"{host_name} does NOT meet Fleet policy: '{policy_name}' — this condition "
            f"is currently FALSE on the device and must be remediated"
        )

        severity = "P2" if any(w in policy_name.lower() for w in CRITICAL_POLICY_WORDS) else "P3"

        alert_id = f"fleet-policy-{policy_id or policy_name}-{host_uuid[:8]}"

        return Translation(
            event_id=alert_id,
            # AXO sets timestamp=datetime.utcnow() unconditionally here — Fleet's
            # payload carries no event time it trusts. Hence the clock.
            occurred_at=self._clock.now(),
            tenant_hint=TenantHint(
                # `team_name or "unknown"` / `team_name or ""` at lines 144-145. A Fleet
                # team is not a customer; treating it as one is preserved defect
                # territory, which is exactly what tenant_hint is for.
                tenant_id=team_name or "unknown",
                tenant_name=team_name or "",
            ),
            body=AlertBody(
                alert_id=alert_id,
                device_id=f"fleet:{host_uuid}",
                device_name=str(host_name),
                severity=severity,
                category=category,
                message=message,
            ),
            raw_payload_override=payload,
        )
