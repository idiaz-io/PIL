"""Tool-agnostic execution-result shapes (ADR-0015)."""

from __future__ import annotations

import dataclasses

import pytest

from pil_adapters.execution.shapes import (
    ConnectivityResult,
    DeviceProfile,
    ExecutionResult,
    VerificationResult,
)


def test_device_profile_defaults():
    profile = DeviceProfile(
        device_id="fleet:abc-123",
        hostname="abc-123",
        platform="fleet",
        os_type="unknown",
        os_name="unknown",
    )
    assert profile.ip_address is None
    assert profile.tags == ()
    assert profile.auto_heal_enabled is False
    assert profile.business_criticality == "standard"
    assert profile.client_id == ""


def test_device_profile_is_frozen():
    profile = DeviceProfile(
        device_id="fleet:abc", hostname="abc", platform="fleet", os_type="macos", os_name="14.5"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        profile.hostname = "renamed"  # type: ignore[misc]


def test_connectivity_result_defaults():
    result = ConnectivityResult(reachable=True, method="fleet", endpoint="fleet:abc")
    assert result.latency_ms is None
    assert result.error is None


def test_execution_result_requires_no_defaults_for_core_fields():
    result = ExecutionResult(
        success=True, exit_code=0, stdout="ok", stderr="", duration_ms=42, adapter="fleet"
    )
    assert result.error is None


def test_verification_result_defaults():
    result = VerificationResult(verdict="inconclusive")
    assert result.level1_cleared is None
    assert result.level2_passed is None
    assert result.checks == ()
    assert result.error is None


def test_verification_result_carries_checks():
    checks = ({"name": "disk free", "expected": "1", "actual": "1", "pass": True},)
    result = VerificationResult(verdict="pass", level2_passed=True, checks=checks)
    assert result.checks == checks
