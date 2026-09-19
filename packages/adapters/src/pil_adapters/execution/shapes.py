"""Shapes the execution layer returns. Tool-agnostic (ADR-0015).

Ported from `msp-platform/backend/services/reasoning/interfaces.py` -- the four shapes
ADR-0015 names as shared across future adapters' execution ports, not the whole of that
module. AXO's file also defines ``StandardAlert``, ``Tool`` and ``Plan``: those belong to
AXO's reasoning engine (a tool registry, a scoring pipeline) and have no PIL analogue, so
they are not ported here. Porting them would mean PIL growing a product's concept rather
than the tool-agnostic result shapes an execution method actually returns.

``DeviceProfile`` here is narrower than AXO's: it keeps only the fields
`fleet_healing_adapter.py`'s own ``fetch_device_details`` populates (`hostname`, `os_type`,
`ip_address`, `tags`, ...). AXO's ``DeviceProfile`` also carries fields a *reasoning* stage
fills in later -- ``dependencies``, ``sops``, ``live_metrics``, ``blast_radius_count``,
``root_cause_device_id``, ``auto_registered`` -- assembled from AXO's graph and job state,
not from any tool's connect surface. Those stay a product concern.

Frozen and slotted, matching :class:`~pil_adapters.connection.ToolConnection` and
:class:`~pil_adapters.connection.CredentialHandle`: these are returned by an execution
method and read by its caller, never mutated in place the way AXO's reasoning stages mutate
a shared context object as they enrich it.

``verdict`` and ``os_type`` stay plain ``str`` rather than becoming new closed vocabularies.
I-6 governs *PIL's own* vocabularies; these three-ish-value strings are AXO's, ported as
AXO defined them. Closing them is a real option later, but that is a new enum member
decision (an ADR, per CLAUDE.md's stop-and-ask list on new kinds), not something to fold
silently into a migration.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ConnectivityResult",
    "DeviceProfile",
    "ExecutionResult",
    "VerificationResult",
]


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """A device, as an adapter's connect surface reports it.

    Port of `fleet_healing_adapter.py:205-216`'s return shape. ``client_id`` is Fleet's
    team name or ``"unknown"`` -- preserved as-is; see the translator's own tenant_hint
    docstring for why a Fleet team is not a customer.
    """

    device_id: str
    hostname: str
    platform: str
    os_type: str
    os_name: str
    ip_address: str | None = None
    tags: Sequence[str] = field(default_factory=tuple)
    auto_heal_enabled: bool = False
    business_criticality: str = "standard"
    client_id: str = ""


@dataclass(frozen=True, slots=True)
class ConnectivityResult:
    """Result of a pre-flight reachability check. Port of `interfaces.py:65-73`."""

    reachable: bool
    method: str
    endpoint: str
    latency_ms: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Result of running a script on a device. Port of `interfaces.py:116-126`."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    adapter: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Combined two-level verification result. Port of `interfaces.py:129-137`.

    ``level1_cleared`` is integration-level (the alert's own condition, re-checked against
    the tool). ``level2_passed`` is device-level (explicit checks run on the device). A
    caller may have either, both, or neither populated depending on which verification
    method produced this result.
    """

    verdict: str
    level1_cleared: bool | None = None
    level2_passed: bool | None = None
    checks: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    error: str | None = None
