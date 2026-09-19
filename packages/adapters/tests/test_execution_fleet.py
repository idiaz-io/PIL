"""FleetExecutor -- ported from `fleet_healing_adapter.py` (ADR-0015).

Every test drives an in-process :class:`httpx.MockTransport`, never a live Fleet. The
handler functions below stand in for Fleet's REST API and are written to fail loudly
(``AssertionError``) on an unexpected request rather than silently 404ing, so a broken
test reads as "wrong request shape" rather than "host not found".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from pil_adapters.execution.fleet import FleetExecutor

ENDPOINT = "https://fleet.example.com"
TOKEN = "test-token"


def executor(handler: httpx.MockTransport) -> FleetExecutor:
    return FleetExecutor(ENDPOINT, TOKEN, transport=handler)


# ----------------------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------------------


def test_endpoint_is_required():
    with pytest.raises(ValueError, match="endpoint"):
        FleetExecutor("", TOKEN)


def test_token_is_required():
    with pytest.raises(ValueError, match="token"):
        FleetExecutor(ENDPOINT, "")


def test_endpoint_trailing_slash_is_stripped():
    assert FleetExecutor(f"{ENDPOINT}/", TOKEN).endpoint == ENDPOINT


def test_constructor_has_no_credential_handle_parameter():
    """ADR-0015 decision 2: FleetExecutor never imports CredentialHandle."""
    import inspect

    params = inspect.signature(FleetExecutor.__init__).parameters
    assert set(params) == {"self", "endpoint", "token", "transport"}


# ----------------------------------------------------------------------------------
# check_connectivity
# ----------------------------------------------------------------------------------


async def test_check_connectivity_reachable_via_identifier_match():
    recently_seen = (datetime.now(UTC) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/latest/fleet/hosts/identifier/abc-123"
        return httpx.Response(
            200,
            json={"host": {"id": 42, "status": "online", "seen_time": recently_seen}},
        )

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:abc-123")

    assert result.reachable is True
    assert result.method == "fleet"
    assert result.endpoint == f"{ENDPOINT}/hosts/42"
    assert result.error is None


async def test_check_connectivity_falls_back_to_fuzzy_query():
    recently_seen = (datetime.now(UTC) - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc-123":
            return httpx.Response(404)
        assert request.url.path == "/api/latest/fleet/hosts"
        assert request.url.params["query"] == "abc-123"
        return httpx.Response(
            200,
            json={"hosts": [{"id": 7, "status": "online", "seen_time": recently_seen}]},
        )

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:abc-123")

    assert result.reachable is True
    assert result.endpoint == f"{ENDPOINT}/hosts/7"


async def test_check_connectivity_offline_when_last_seen_over_24h_ago():
    stale = (datetime.now(UTC) - timedelta(hours=30)).isoformat().replace("+00:00", "Z")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"host": {"id": 1, "status": "offline", "seen_time": stale}}
        )

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:abc")

    assert result.reachable is False
    assert "30h ago" in result.error
    assert "offline" in result.error


async def test_check_connectivity_host_not_found_is_a_real_escalation():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/latest/fleet/hosts/identifier/"):
            return httpx.Response(404)
        return httpx.Response(200, json={"hosts": []})

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:missing")

    assert result.reachable is False
    assert "not found" in result.error


async def test_check_connectivity_transient_lookup_failure_defers_to_execution():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:abc")

    assert result.reachable is True
    assert "deferring to script execution" in result.error


async def test_check_connectivity_transport_error_defers_to_execution():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:abc")

    assert result.reachable is True
    assert "boom" in result.error


async def test_check_connectivity_missing_seen_time_defaults_reachable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"host": {"id": 9, "status": "online"}})

    result = await executor(httpx.MockTransport(handler)).check_connectivity("fleet:abc")

    assert result.reachable is True
    assert result.error is None


# ----------------------------------------------------------------------------------
# fetch_device_details
# ----------------------------------------------------------------------------------


async def test_fetch_device_details_merges_search_and_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts":
            return httpx.Response(
                200,
                json={"hosts": [{"id": 42, "hostname": "web-01", "platform": "darwin"}]},
            )
        assert request.url.path == "/api/latest/fleet/hosts/42"
        return httpx.Response(
            200,
            json={
                "host": {
                    "id": 42,
                    "hostname": "web-01",
                    "platform": "darwin",
                    "os_version": "macOS 14.5",
                    "primary_ip": "10.0.0.5",
                    "team_name": "infra",
                    "labels": [{"name": "prod"}, "canary"],
                }
            },
        )

    profile = await executor(httpx.MockTransport(handler)).fetch_device_details(
        "fleet:abc-123"
    )

    assert profile.device_id == "fleet:abc-123"
    assert profile.hostname == "web-01"
    assert profile.platform == "fleet"
    assert profile.os_type == "macos"
    assert profile.os_name == "macOS 14.5"
    assert profile.ip_address == "10.0.0.5"
    assert profile.tags == ("prod", "canary")
    assert profile.auto_heal_enabled is False
    assert profile.business_criticality == "standard"
    assert profile.client_id == "infra"


async def test_fetch_device_details_unknown_platform_maps_to_unknown_os_type():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts":
            return httpx.Response(200, json={"hosts": [{"id": 1, "platform": "freebsd"}]})
        return httpx.Response(200, json={"host": {"id": 1, "platform": "freebsd"}})

    profile = await executor(httpx.MockTransport(handler)).fetch_device_details("fleet:x")

    assert profile.os_type == "unknown"


async def test_fetch_device_details_stub_when_host_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hosts": []})

    profile = await executor(httpx.MockTransport(handler)).fetch_device_details(
        "fleet:missing"
    )

    assert profile.hostname == "missing"
    assert profile.os_type == "unknown"
    assert profile.client_id == ""


async def test_fetch_device_details_stub_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    profile = await executor(httpx.MockTransport(handler)).fetch_device_details("fleet:x")

    assert profile.hostname == "x"
    assert profile.os_type == "unknown"


async def test_fetch_device_details_stub_when_search_errors_http_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    profile = await executor(httpx.MockTransport(handler)).fetch_device_details("fleet:x")

    assert profile.hostname == "x"


async def test_fetch_device_details_falls_back_to_search_result_when_detail_fetch_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts":
            return httpx.Response(
                200, json={"hosts": [{"id": 5, "hostname": "search-only", "platform": "linux"}]}
            )
        return httpx.Response(404)

    profile = await executor(httpx.MockTransport(handler)).fetch_device_details("fleet:y")

    assert profile.hostname == "search-only"
    assert profile.os_type == "linux"
