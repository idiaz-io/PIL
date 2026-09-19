"""FleetDM execution port. Ported from `fleet_healing_adapter.py` (ADR-0015).

`FleetExecutor` takes an already-resolved ``endpoint`` and ``token`` -- never a
:class:`~pil_adapters.connection.CredentialHandle`. ADR-0015 decided this is a permanent
architectural boundary, not a Phase A gap: PIL does not know a deployment's answer to
sovereign/air-gap hosting (ADR-17, still open) or hold a secret store's own address and
master token, so resolving a handle to a value is the caller's job, done immediately
before constructing this class -- the same posture :mod:`pil_graph` takes toward shipping
no live Neo4j driver (ADR-0011).

Also not ported: AXO's ``_ensure_config`` (loads credentials from AXO's own database --
a product dependency, I-3) and the "not configured" branches every AXO method opens with.
``endpoint`` and ``token`` are required constructor arguments, validated non-blank, so
there is no unconfigured state to branch on here.

Every method below takes an httpx transport hook only through the constructor
(``transport``), never per call, so a caller cannot swap network behaviour mid-request --
tests inject an :class:`httpx.MockTransport` there; production leaves it unset and gets
real sockets, opened by ``httpx``, not by PIL (I-1's bind/listen/accept test governs PIL
itself, not a client library it depends on).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from pil_adapters.execution.shapes import ConnectivityResult, DeviceProfile

__all__ = ["FleetExecutor"]

logger = logging.getLogger(__name__)

#: A host not seen within this window is treated as offline. Port of
#: `fleet_healing_adapter.py:308`'s inline ``24 * 3600``.
_OFFLINE_AFTER_SECONDS = 24 * 3600

#: Fleet's `platform` field to PIL's `os_type`. Port of `fleet_healing_adapter.py:195`.
_PLATFORM_TO_OS_TYPE = {"darwin": "macos", "linux": "linux", "windows": "windows"}


class FleetExecutor:
    """Connect, fetch, execute and verify against one Fleet deployment.

    One instance per (tenant, product)'s resolved Fleet connection -- the same scoping
    :class:`~pil_adapters.connection.ToolConnection` already enforces one layer up. This
    class has no opinion about tenancy at all; it only ever sees one endpoint and one
    token.
    """

    def __init__(
        self,
        endpoint: str,
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not endpoint or not endpoint.strip():
            raise ValueError("FleetExecutor.endpoint is required")
        if not token or not token.strip():
            raise ValueError("FleetExecutor.token is required")
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._transport = transport

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def __repr__(self) -> str:
        return f"FleetExecutor(endpoint={self._endpoint!r})"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @property
    def _verify_tls(self) -> bool:
        """Whether httpx should validate the TLS cert. Port of `_verify()`/`_verify_for()`.

        Local Fleet uses a self-signed cert, so validation is skipped for an endpoint
        naming localhost or 127.0.0.1. Everything else validates normally.
        """
        lowered = self._endpoint.lower()
        return not ("localhost" in lowered or "127.0.0.1" in lowered)

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=self._transport, timeout=timeout, verify=self._verify_tls
        )

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    async def check_connectivity(self, device_id: str) -> ConnectivityResult:
        """Verify the host exists in Fleet. Port of `fleet_healing_adapter.py:225-325`.

        Reachability is left to Fleet's script-execution API rather than enforced here:
        `/scripts/run/sync` already waits up to 60s for a host to come online, and
        `/scripts/run` (async) queues for the next osquery check-in. Flagging a brief
        offline gap here would cause spurious escalations for a laptop that is merely
        asleep.

        Lookup strategy, in order:
          1. Fleet's exact-match ``/hosts/identifier/{uuid}`` (deterministic).
          2. Fall back to ``/hosts?query={uuid}&per_page=1`` (fuzzy -- AXO's own comment
             notes this has been observed to return empty for valid hosts under load).
          3. If both lookups fail with anything other than a clean 404, treat it as a
             transient API blip and report reachable -- Fleet's script-run API has its own
             retries and will surface a real failure there, with a useful message.

        A host last seen within 24h counts as reachable; older than that counts as
        offline.
        """
        uuid = device_id.removeprefix("fleet:")

        host: dict[str, Any] | None = None
        lookup_error: str | None = None
        try:
            async with self._client(timeout=10) as client:
                identifier_resp = await client.get(
                    f"{self._endpoint}/api/latest/fleet/hosts/identifier/{uuid}",
                    headers=self._headers(),
                )
                if identifier_resp.status_code == 200:
                    host = (identifier_resp.json() or {}).get("host")
                elif identifier_resp.status_code != 404:
                    lookup_error = f"identifier lookup HTTP {identifier_resp.status_code}"

                if host is None and lookup_error is None:
                    query_resp = await client.get(
                        f"{self._endpoint}/api/latest/fleet/hosts",
                        params={"query": uuid, "per_page": 1},
                        headers=self._headers(),
                    )
                    if query_resp.status_code == 200:
                        hosts = (query_resp.json() or {}).get("hosts") or []
                        if hosts:
                            host = hosts[0]
                    else:
                        lookup_error = f"query lookup HTTP {query_resp.status_code}"
        except Exception as exc:  # ported leniency -- AXO treats any lookup failure as transient
            lookup_error = str(exc)

        if lookup_error and host is None:
            # Transient API failure -- don't escalate the whole job over this. Trust
            # Fleet's script-run API to surface a real error if one exists.
            return ConnectivityResult(
                reachable=True,
                method="fleet",
                endpoint=device_id,
                error=(
                    f"Fleet lookup failed transiently ({lookup_error}) -- deferring to "
                    "script execution"
                ),
            )

        if host is None:
            # Both lookups succeeded but returned no host -- a real escalation.
            return ConnectivityResult(
                reachable=False,
                method="fleet",
                endpoint=device_id,
                error="Host not found in Fleet (both identifier and query lookups returned empty)",
            )

        status = str(host.get("status") or "").lower()
        seen_time = host.get("seen_time")
        reachable = True
        age_seconds: float | None = None
        if seen_time:
            try:
                seen = datetime.fromisoformat(str(seen_time).replace("Z", "+00:00"))
                if seen.tzinfo is None:
                    seen = seen.replace(tzinfo=UTC)
                age_seconds = (datetime.now(UTC) - seen).total_seconds()
                if age_seconds > _OFFLINE_AFTER_SECONDS:
                    reachable = False
            except ValueError:
                pass

        error = None
        if not reachable and age_seconds is not None:
            error = (
                f"Host last seen {int(age_seconds / 3600)}h ago (>24h) -- treating as "
                f"offline. Fleet status={status or 'unknown'}"
            )

        return ConnectivityResult(
            reachable=reachable,
            method="fleet",
            endpoint=f"{self._endpoint}/hosts/{host.get('id', '')}",
            error=error,
        )

    # ------------------------------------------------------------------
    # Device details
    # ------------------------------------------------------------------

    async def fetch_device_details(self, device_id: str) -> DeviceProfile:
        """Fetch a device profile from Fleet by UUID.

        Port of `fleet_healing_adapter.py:158-219`. Any failure -- host not found,
        network error, malformed response -- falls back to :func:`_stub_profile` rather
        than raising, matching AXO's own behaviour: a device that cannot be enriched still
        needs a profile object downstream, just an uninformative one.
        """
        uuid = device_id.removeprefix("fleet:")
        try:
            async with self._client(timeout=15) as client:
                search_resp = await client.get(
                    f"{self._endpoint}/api/latest/fleet/hosts",
                    params={"query": uuid, "per_page": 1},
                    headers=self._headers(),
                )
                search_resp.raise_for_status()
                hosts = search_resp.json().get("hosts", [])

                if not hosts:
                    return _stub_profile(device_id, uuid)

                host: dict[str, Any] = hosts[0]
                fleet_id = host.get("id")

                if fleet_id:
                    detail_resp = await client.get(
                        f"{self._endpoint}/api/latest/fleet/hosts/{fleet_id}",
                        headers=self._headers(),
                    )
                    if detail_resp.status_code == 200:
                        detail_json = detail_resp.json()
                        detail = detail_json.get("host", detail_json)
                        host = {**host, **detail}

            platform = str(host.get("platform") or "").lower()
            os_type = _PLATFORM_TO_OS_TYPE.get(platform, "unknown")

            # Fleet labels can be a list of dicts {"name": ..., ...} or plain strings.
            raw_labels = host.get("labels") or []
            tags = tuple(
                (label["name"] if isinstance(label, dict) else str(label))
                for label in raw_labels
                if label
            )

            return DeviceProfile(
                device_id=device_id,
                hostname=host.get("hostname") or host.get("computer_name") or uuid,
                platform="fleet",
                os_type=os_type,
                os_name=host.get("os_version") or "unknown",
                ip_address=host.get("primary_ip"),
                tags=tags,
                auto_heal_enabled=False,
                business_criticality="standard",
                client_id=host.get("team_name") or "unknown",
            )
        except Exception as exc:
            logger.warning("FleetExecutor.fetch_device_details(%s) failed: %s", device_id, exc)
            return _stub_profile(device_id, uuid)


def _stub_profile(device_id: str, uuid: str) -> DeviceProfile:
    """The fallback profile AXO returns when Fleet has nothing to say about a device.

    Port of `fleet_healing_adapter.py:755-764`.
    """
    return DeviceProfile(
        device_id=device_id,
        hostname=uuid,
        platform="fleet",
        os_type="unknown",
        os_name="unknown",
        auto_heal_enabled=False,
        business_criticality="standard",
    )
