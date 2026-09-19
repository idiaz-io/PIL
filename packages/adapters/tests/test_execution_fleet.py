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


class FakeClock:
    """A monotonic clock and sleep function that advance together, instantly.

    `execute_on_device`'s retry-with-backoff and polling loop are written against real
    seconds (30/60s backoff, a 5s poll interval, a 180s poll budget) -- a test that
    actually waited those out would take minutes. Injecting this in place of
    `asyncio.sleep`/`time.monotonic` makes every wait resolve immediately while still
    driving the deadline math for real, and records what was waited for, so a test can
    assert on the backoff schedule without living through it.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def executor_with_clock(handler: httpx.MockTransport, clock: FakeClock) -> FleetExecutor:
    return FleetExecutor(
        ENDPOINT, TOKEN, transport=handler, sleep=clock.sleep, monotonic=clock.monotonic
    )


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
    assert set(params) == {"self", "endpoint", "token", "transport", "sleep", "monotonic"}


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


# ----------------------------------------------------------------------------------
# execute_on_device
# ----------------------------------------------------------------------------------


async def test_execute_on_device_host_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/latest/fleet/hosts/identifier/"):
            return httpx.Response(404)
        return httpx.Response(200, json={"hosts": []})

    clock = FakeClock()
    result = await executor_with_clock(httpx.MockTransport(handler), clock).execute_on_device(
        "fleet:missing", "echo hi"
    )

    assert result.success is False
    assert result.error == "Host not found"
    assert "missing" in result.stderr
    assert clock.sleeps == []


async def test_execute_on_device_submits_and_polls_until_exit_code():
    polls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            assert request.method == "POST"
            return httpx.Response(200, json={"execution_id": "exec-1"})
        if request.url.path == "/api/latest/fleet/scripts/results/exec-1":
            polls["count"] += 1
            if polls["count"] < 2:
                return httpx.Response(200, json={"exit_code": None})
            return httpx.Response(200, json={"exit_code": 0, "output": "done"})
        raise AssertionError(f"unexpected request: {request.url.path}")

    clock = FakeClock()
    result = await executor_with_clock(httpx.MockTransport(handler), clock).execute_on_device(
        "fleet:abc", "echo hi"
    )

    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout == "done"
    assert polls["count"] == 2
    assert clock.sleeps == [5, 5]


async def test_execute_on_device_host_timeout_from_fleet():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            return httpx.Response(200, json={"execution_id": "exec-1"})
        return httpx.Response(200, json={"host_timeout": True})

    result = await executor_with_clock(
        httpx.MockTransport(handler), FakeClock()
    ).execute_on_device("fleet:abc", "echo hi")

    assert result.success is False
    assert "timed out" in result.stderr.lower()


async def test_execute_on_device_missing_execution_id_in_response():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        return httpx.Response(200, json={"unexpected": "shape"})

    result = await executor_with_clock(
        httpx.MockTransport(handler), FakeClock()
    ).execute_on_device("fleet:abc", "echo hi")

    assert result.success is False
    assert "no execution_id" in result.stderr


async def test_execute_on_device_polling_times_out_after_180_seconds():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            return httpx.Response(200, json={"execution_id": "exec-1"})
        return httpx.Response(200, json={"exit_code": None})

    clock = FakeClock()
    result = await executor_with_clock(httpx.MockTransport(handler), clock).execute_on_device(
        "fleet:abc", "echo hi"
    )

    assert result.success is False
    assert "Timed out polling Fleet script result after 180s" in result.stderr
    assert clock.now == 180


async def test_execute_on_device_injects_params_as_bash_exports():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            captured["body"] = request.content.decode()
            return httpx.Response(200, json={"execution_id": "exec-1"})
        return httpx.Response(200, json={"exit_code": 0, "output": ""})

    await executor_with_clock(httpx.MockTransport(handler), FakeClock()).execute_on_device(
        "fleet:abc", "echo hi", params={"TARGET": "prod"}
    )

    assert 'export TARGET=\\"prod\\"' in captured["body"]
    assert "echo hi" in captured["body"]


async def test_execute_on_device_retries_transient_error_then_succeeds():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(200, json={"execution_id": "exec-1"})
        return httpx.Response(200, json={"exit_code": 0, "output": "ok"})

    clock = FakeClock()
    result = await executor_with_clock(httpx.MockTransport(handler), clock).execute_on_device(
        "fleet:abc", "echo hi"
    )

    assert result.success is True
    assert attempts["count"] == 3
    # Two backoff waits (30, 60) before the two failed retries, then one 5s poll wait
    # before the successful attempt's result is ready.
    assert clock.sleeps == [30, 60, 5]


async def test_execute_on_device_raises_after_exhausting_all_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        raise httpx.ConnectTimeout("timed out", request=request)

    clock = FakeClock()
    with pytest.raises(httpx.ConnectTimeout):
        await executor_with_clock(httpx.MockTransport(handler), clock).execute_on_device(
            "fleet:abc", "echo hi"
        )

    assert clock.sleeps == [30, 60]


async def test_execute_on_device_non_transient_error_fails_without_retry():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        raise RuntimeError("unexpected failure")

    clock = FakeClock()
    result = await executor_with_clock(httpx.MockTransport(handler), clock).execute_on_device(
        "fleet:abc", "echo hi"
    )

    assert result.success is False
    assert result.error == "unexpected failure"
    assert clock.sleeps == []


# ----------------------------------------------------------------------------------
# verify_alert_cleared
# ----------------------------------------------------------------------------------


def alert_id_for(uuid: str) -> str:
    return f"fleet-policy-21-{uuid[:8]}"


async def test_verify_alert_cleared_pass_when_query_returns_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts":
            return httpx.Response(200, json={"hosts": [{"id": 5, "uuid": "ACC13DA0-full"}]})
        assert request.url.path == "/api/latest/fleet/queries/run"
        return httpx.Response(200, json={"results": [{"rows": [{"col": "value"}]}]})

    result = await executor(httpx.MockTransport(handler)).verify_alert_cleared(
        alert_id_for("ACC13DA0"), "SELECT 1"
    )

    assert result.verdict == "pass"
    assert result.level1_cleared is True


async def test_verify_alert_cleared_fail_when_query_returns_no_rows():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts":
            return httpx.Response(200, json={"hosts": [{"id": 5, "uuid": "ACC13DA0-full"}]})
        return httpx.Response(200, json={"results": [{"rows": []}]})

    result = await executor(httpx.MockTransport(handler)).verify_alert_cleared(
        alert_id_for("ACC13DA0"), "SELECT 1"
    )

    assert result.verdict == "fail"
    assert result.level1_cleared is False
    assert "did not take effect" in result.error


async def test_verify_alert_cleared_inconclusive_when_host_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"hosts": [{"id": 5, "uuid": "OTHERUUID-full"}]})

    result = await executor(httpx.MockTransport(handler)).verify_alert_cleared(
        alert_id_for("ACC13DA0"), "SELECT 1"
    )

    assert result.verdict == "inconclusive"
    assert result.level1_cleared is None


async def test_verify_alert_cleared_inconclusive_on_query_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts":
            return httpx.Response(200, json={"hosts": [{"id": 5, "uuid": "ACC13DA0-full"}]})
        return httpx.Response(500)

    result = await executor(httpx.MockTransport(handler)).verify_alert_cleared(
        alert_id_for("ACC13DA0"), "SELECT 1"
    )

    assert result.verdict == "inconclusive"


async def test_verify_alert_cleared_inconclusive_on_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    result = await executor(httpx.MockTransport(handler)).verify_alert_cleared(
        alert_id_for("ACC13DA0"), "SELECT 1"
    )

    assert result.verdict == "inconclusive"


# ----------------------------------------------------------------------------------
# verify_device_state
# ----------------------------------------------------------------------------------


async def test_verify_device_state_no_checks_passes_trivially():
    result = await executor(httpx.MockTransport(lambda r: httpx.Response(500))).verify_device_state(
        "fleet:abc", []
    )

    assert result.verdict == "pass"
    assert result.level2_passed is True
    assert result.checks == ()


async def test_verify_device_state_compares_actual_to_expected():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            return httpx.Response(200, json={"execution_id": "exec-1"})
        return httpx.Response(200, json={"exit_code": 0, "output": "1"})

    result = await executor_with_clock(
        httpx.MockTransport(handler), FakeClock()
    ).verify_device_state(
        "fleet:abc", [{"name": "disk free", "command": "check_disk", "expected": "1"}]
    )

    assert result.verdict == "pass"
    assert result.level2_passed is True
    assert result.checks[0]["actual"] == "1"
    assert result.checks[0]["pass"] is True


async def test_verify_device_state_no_expected_uses_exit_code():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            return httpx.Response(200, json={"execution_id": "exec-1"})
        return httpx.Response(200, json={"exit_code": 1, "output": ""})

    result = await executor_with_clock(
        httpx.MockTransport(handler), FakeClock()
    ).verify_device_state("fleet:abc", [{"command": "check_thing"}])

    assert result.verdict == "fail"
    assert result.level2_passed is False
    assert result.checks[0]["pass"] is False


async def test_verify_device_state_skips_checks_without_a_command():
    result = await executor(httpx.MockTransport(lambda r: httpx.Response(500))).verify_device_state(
        "fleet:abc", [{"name": "no command here"}]
    )

    assert result.verdict == "pass"
    assert result.checks == ()


async def test_verify_device_state_all_must_pass():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/latest/fleet/hosts/identifier/abc":
            return httpx.Response(200, json={"host": {"id": 5}})
        if request.url.path == "/api/latest/fleet/scripts/run":
            calls["count"] += 1
            return httpx.Response(200, json={"execution_id": f"exec-{calls['count']}"})
        exit_code = 0 if calls["count"] == 1 else 1
        return httpx.Response(200, json={"exit_code": exit_code, "output": ""})

    result = await executor_with_clock(
        httpx.MockTransport(handler), FakeClock()
    ).verify_device_state(
        "fleet:abc",
        [{"command": "check_one"}, {"command": "check_two"}],
    )

    assert result.verdict == "fail"
    assert result.level2_passed is False
    assert len(result.checks) == 2
