"""Tenancy resolution — IDI-195 D1, invariant I-5.

The tests that carry the decision are
:func:`test_a_vendor_payload_is_not_a_tenant_source` and
:func:`test_there_is_no_precedence_between_sources`. Everything else is boundary work.

I-5 is described in `CLAUDE.md` as "currently violated in AXO production and the
highest-risk class of bug in the system", so the interesting assertions here are about what
this module *refuses*, not what it accepts.
"""

from __future__ import annotations

import inspect

import pytest

from pil_contracts import (
    TenancyError,
    TenantSource,
    resolve_tenant,
    tenancy,
)

# ----------------------------------------------------------------------------------
# The two legitimate sources
# ----------------------------------------------------------------------------------


def test_a_validated_token_claim_resolves():
    tenant = resolve_tenant(token_claim="tenant-acme")
    assert tenant.tenant_id == "tenant-acme"
    assert tenant.source is TenantSource.TOKEN_CLAIM


def test_adapter_configuration_resolves():
    """The scheduled-work case. No token exists, so configuration is the only source."""
    tenant = resolve_tenant(adapter_config_tenant="tenant-acme")
    assert tenant.tenant_id == "tenant-acme"
    assert tenant.source is TenantSource.ADAPTER_CONFIG


def test_the_source_is_recorded_not_just_the_id():
    """ "Came from configuration" and "came from a token" differ in an audit."""
    assert resolve_tenant(token_claim="t").source != (
        resolve_tenant(adapter_config_tenant="t").source
    )


# ----------------------------------------------------------------------------------
# What it refuses — the reason the module exists
# ----------------------------------------------------------------------------------


def test_a_vendor_payload_is_not_a_tenant_source():
    """There must be no way to hand this function a payload.

    Structural rather than behavioural: the check is that no parameter exists that could
    accept one. AXO derives tenancy from payload content in eleven places — splitting a
    URI, fuzzy-matching a team name, using an MDM policy id as a customer id — and each
    started as a plausible-looking parameter.
    """
    parameters = set(inspect.signature(resolve_tenant).parameters)
    assert parameters == {"token_claim", "adapter_config_tenant"}

    forbidden = {"payload", "raw", "body", "event", "alert", "data", "message", "hint"}
    assert not parameters & forbidden


def test_every_parameter_is_keyword_only():
    """A positional call cannot say which source it means.

    ``resolve_tenant(x)`` would read identically whether ``x`` came from a token or from a
    payload, which is precisely the ambiguity that has to be impossible.
    """
    for parameter in inspect.signature(resolve_tenant).parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_there_is_no_precedence_between_sources():
    """Supplying both must raise rather than quietly preferring one.

    A precedence rule is the first link in the fallback chain this module exists to
    prevent: "use the token, or the payload if there is no token" is how AXO's sites
    became the normal path rather than the exception.
    """
    with pytest.raises(TenancyError, match="no precedence rule"):
        resolve_tenant(token_claim="a", adapter_config_tenant="b")


def test_supplying_nothing_raises():
    """There is no anonymous tenant and no default."""
    with pytest.raises(TenancyError, match="no tenant source"):
        resolve_tenant()


def test_the_module_has_no_function_taking_a_payload():
    """Nothing else in the module offers a back door.

    A second helper that accepted a mapping would be exactly as harmful as a parameter on
    the first one, and easier to miss in review.
    """
    suspicious = {"payload", "raw", "body", "event", "alert", "data", "message"}
    for name, obj in vars(tenancy).items():
        if name.startswith("__") or not inspect.isfunction(obj):
            continue
        assert not set(inspect.signature(obj).parameters) & suspicious, (
            f"{name} accepts something payload-shaped"
        )


# ----------------------------------------------------------------------------------
# Boundaries
# ----------------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", " ", "\t", "\n"])
def test_a_blank_tenant_is_rejected(blank):
    with pytest.raises(TenancyError, match="I-5"):
        resolve_tenant(adapter_config_tenant=blank)


@pytest.mark.parametrize("value", [42, None, [], {}, 1.5, True])
def test_a_non_string_tenant_is_rejected(value):
    """Coercion is how 42 and "42" become two tenants.

    ``None`` is the one that matters most: coerced, it becomes the string "None" and then a
    real-looking row in a tenant-scoped store.
    """
    if value is None:
        # None means "not supplied" for these keyword arguments, so it lands on the
        # no-source branch rather than the type check. Either way it must raise.
        with pytest.raises(TenancyError):
            resolve_tenant(adapter_config_tenant=value)
        return
    with pytest.raises(TenancyError, match="must be a string"):
        resolve_tenant(adapter_config_tenant=value)


def test_surrounding_whitespace_is_rejected_rather_than_stripped():
    """Two spellings of one tenant become two tenants in a store that keys on the string.

    Rejecting rather than silently trimming: if configuration holds " acme", that is a
    configuration bug worth surfacing, not something to paper over on every call.
    """
    with pytest.raises(TenancyError, match="whitespace"):
        resolve_tenant(adapter_config_tenant=" tenant-acme ")


def test_a_tenant_is_frozen():
    """Once resolved, a tenant is not adjusted — that keeps the decision at one point."""
    tenant = resolve_tenant(token_claim="tenant-acme")
    with pytest.raises(AttributeError):
        tenant.tenant_id = "someone-else"  # type: ignore[misc]


def test_str_gives_the_bare_id():
    """So that formatting a tenant into a log line cannot leak the source enum."""
    assert str(resolve_tenant(token_claim="tenant-acme")) == "tenant-acme"


def test_tenancy_error_is_a_value_error():
    """Existing callers catching ValueError keep working."""
    assert issubclass(TenancyError, ValueError)


def test_tenant_source_is_a_closed_vocabulary():
    """I-6. A third source is an ADR, not a commit."""
    assert {member.value for member in TenantSource} == {"token_claim", "adapter_config"}
