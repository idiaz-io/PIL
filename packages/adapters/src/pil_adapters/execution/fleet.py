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

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx

from pil_adapters.execution.shapes import ConnectivityResult, DeviceProfile, ExecutionResult

__all__ = ["FleetExecutor"]

logger = logging.getLogger(__name__)

#: A host not seen within this window is treated as offline. Port of
#: `fleet_healing_adapter.py:308`'s inline ``24 * 3600``.
_OFFLINE_AFTER_SECONDS = 24 * 3600

#: Fleet's `platform` field to PIL's `os_type`. Port of `fleet_healing_adapter.py:195`.
_PLATFORM_TO_OS_TYPE = {"darwin": "macos", "linux": "linux", "windows": "windows"}

#: Seconds between polls of `GET /scripts/results/{id}`, and the total budget for polling
#: before giving up. Port of `ASYNC_POLL_INTERVAL`/`ASYNC_POLL_TIMEOUT`.
_ASYNC_POLL_INTERVAL_SECONDS = 5
_ASYNC_POLL_TIMEOUT_SECONDS = 180

SleepFn = Callable[[float], Awaitable[None]]
MonotonicFn = Callable[[], float]


def _inject_params(script: str, params: Mapping[str, str], language: str) -> str:
    """Prepend parameter assignments to the script body. Port of `_inject_params`."""
    if not params:
        return script
    lang = language.lower()
    if lang in ("bash", "sh", "shell"):
        lines = [f'export {key}="{value}"' for key, value in params.items()]
        return "\n".join(lines) + "\n" + script
    if lang in ("powershell", "ps1"):
        lines = [f'${key} = "{value}"' for key, value in params.items()]
        return "\n".join(lines) + "\n" + script
    return script


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
        sleep: SleepFn | None = None,
        monotonic: MonotonicFn | None = None,
    ) -> None:
        if not endpoint or not endpoint.strip():
            raise ValueError("FleetExecutor.endpoint is required")
        if not token or not token.strip():
            raise ValueError("FleetExecutor.token is required")
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._transport = transport
        # Time is a parameter here for the same reason a translator's clock is
        # (pil_adapters.clock): a 90-second retry-and-poll budget cannot be exercised by a
        # test that actually waits 90 seconds. Production leaves both at their real
        # defaults; tests inject a no-op sleep and a monotonic stub that advances on demand.
        self._sleep: SleepFn = sleep if sleep is not None else asyncio.sleep
        self._monotonic: MonotonicFn = monotonic if monotonic is not None else time.monotonic

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

    def _elapsed_ms(self, start: float) -> int:
        return int((self._monotonic() - start) * 1000)

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

    # ------------------------------------------------------------------
    # Script execution
    # ------------------------------------------------------------------

    async def execute_on_device(
        self,
        device_id: str,
        script: str,
        params: Mapping[str, str] | None = None,
        language: str = "bash",
    ) -> ExecutionResult:
        """Run a script on a Fleet device. Port of `fleet_healing_adapter.py:331-382`.

        Only the live path: resolve the Fleet host ID from ``device_id``'s UUID, submit
        the script for async execution (``POST /scripts/run``), then poll for its result
        (``GET /scripts/results/{id}``). AXO's synchronous ``/scripts/run/sync`` branch,
        its 409-Conflict retry, and the exception handling wrapping both are unreachable
        dead code in the original -- recorded in ``docs/known-differences.md`` -- and are
        not ported.

        AXO has no ``Tool`` registry here: ``script`` is the fully-resolved script body,
        and ``params``/``language`` drive the same env-var injection AXO's ``Tool`` object
        would have carried. A ``Tool`` with its params schema, preconditions and rollback
        is a product concept (PIL has no tool registry) -- this method only needs the
        rendered text to run.

        Retries up to 3 times when submitting or polling raises a transient network error
        (a failed connection, a connection timeout, or a dropped connection mid-response),
        waiting ``30 * attempt`` seconds between attempts. One deliberate behaviour change
        from AXO here: AXO's ``_run_async`` catches *every* exception -- including these
        three -- into a failed ``ExecutionResult``, which means its own retry loop can
        never actually observe one and never fires (recorded in
        ``docs/known-differences.md``). This port lets those three types propagate out of
        ``_run_script`` instead, so the retry-with-backoff the code was evidently written
        to support actually runs. Every other exception is still caught inside
        ``_run_script`` and turned into a failed result, exactly as AXO does -- and a
        transient error that survives all 3 attempts propagates to the caller rather than
        becoming a failed result, matching AXO's ``raise last_error``.
        """
        start = self._monotonic()
        uuid = device_id.removeprefix("fleet:")

        host_id = await self._resolve_host_id(uuid)
        if host_id is None:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"Host {uuid} not found in Fleet",
                duration_ms=self._elapsed_ms(start),
                adapter="fleet",
                error="Host not found",
            )

        rendered = _inject_params(script, params or {}, language)

        last_error: Exception | None = None
        for attempt in range(3):
            if attempt > 0:
                wait = 30 * attempt
                logger.info(
                    "Fleet execute retry %d/2 for host %s -- waiting %ds",
                    attempt,
                    host_id,
                    wait,
                )
                await self._sleep(wait)
            try:
                return await self._run_script(host_id, rendered, start)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError) as exc:
                last_error = exc
                logger.warning("Fleet execute transient error (attempt %d/3): %s", attempt + 1, exc)
                continue

        assert last_error is not None  # the loop above always returns or sets this
        raise last_error

    async def _resolve_host_id(self, uuid: str) -> int | None:
        """Resolve a Fleet host UUID to its numeric ID. Port of `_get_fleet_host_id`.

        Tries the exact-match ``/hosts/identifier/{uuid}`` endpoint first (deterministic),
        then falls back to the fuzzy ``/hosts?query={uuid}`` lookup. Unlike
        :meth:`_run_script`, any failure here -- including a transient network error --
        is swallowed and reported as "not found", matching AXO's own helper exactly: only
        script submission and polling get retried, not host resolution.
        """
        try:
            async with self._client(timeout=10) as client:
                identifier_resp = await client.get(
                    f"{self._endpoint}/api/latest/fleet/hosts/identifier/{uuid}",
                    headers=self._headers(),
                )
                if identifier_resp.status_code == 200:
                    host = (identifier_resp.json() or {}).get("host")
                    if host and host.get("id") is not None:
                        return int(host["id"])

                query_resp = await client.get(
                    f"{self._endpoint}/api/latest/fleet/hosts",
                    params={"query": uuid, "per_page": 1},
                    headers=self._headers(),
                )
                if query_resp.status_code == 200:
                    hosts = (query_resp.json() or {}).get("hosts") or []
                    if hosts:
                        return int(hosts[0]["id"])
        except Exception as exc:
            logger.error("FleetExecutor._resolve_host_id(%s) failed: %s", uuid, exc)
        return None

    async def _run_script(self, host_id: int, script: str, start: float) -> ExecutionResult:
        """Submit a script for async execution and poll for its result.

        Port of `_run_async` (`fleet_healing_adapter.py:651-716`). See
        :meth:`execute_on_device`'s docstring for the one deliberate divergence: the three
        transient exception types its retry loop catches propagate from here instead of
        being swallowed.
        """
        try:
            async with self._client(timeout=30) as client:
                submit_resp = await client.post(
                    f"{self._endpoint}/api/latest/fleet/scripts/run",
                    json={"host_id": host_id, "script_contents": script},
                    headers=self._headers(),
                )
                submit_resp.raise_for_status()
                submitted = submit_resp.json()
                # Fleet uses different field names across versions.
                exec_id = (
                    submitted.get("script_execution_id")
                    or submitted.get("execution_id")
                    or submitted.get("id")
                )
                if not exec_id:
                    logger.error(
                        "Fleet async: unexpected response (no execution_id): %s",
                        str(submitted)[:300],
                    )
                    return ExecutionResult(
                        success=False,
                        exit_code=-1,
                        stdout="",
                        stderr=f"Fleet returned no execution_id. Response: {str(submitted)[:200]}",
                        duration_ms=self._elapsed_ms(start),
                        adapter="fleet",
                    )

                deadline = self._monotonic() + _ASYNC_POLL_TIMEOUT_SECONDS
                while self._monotonic() < deadline:
                    await self._sleep(_ASYNC_POLL_INTERVAL_SECONDS)
                    poll_resp = await client.get(
                        f"{self._endpoint}/api/latest/fleet/scripts/results/{exec_id}",
                        headers=self._headers(),
                    )
                    if poll_resp.status_code == 200:
                        data = poll_resp.json()
                        exit_code = data.get("exit_code")
                        if exit_code is not None:
                            return ExecutionResult(
                                success=int(exit_code) == 0,
                                exit_code=int(exit_code),
                                stdout=data.get("output") or "",
                                stderr=data.get("stderr") or "",
                                duration_ms=self._elapsed_ms(start),
                                adapter="fleet",
                            )
                        if data.get("host_timeout"):
                            return ExecutionResult(
                                success=False,
                                exit_code=-1,
                                stdout="",
                                stderr="Fleet host timed out waiting for script result",
                                duration_ms=self._elapsed_ms(start),
                                adapter="fleet",
                            )

                return ExecutionResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=(
                        f"Timed out polling Fleet script result after "
                        f"{_ASYNC_POLL_TIMEOUT_SECONDS}s"
                    ),
                    duration_ms=self._elapsed_ms(start),
                    adapter="fleet",
                )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RemoteProtocolError):
            raise
        except Exception as exc:
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                duration_ms=self._elapsed_ms(start),
                adapter="fleet",
                error=str(exc),
            )


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
