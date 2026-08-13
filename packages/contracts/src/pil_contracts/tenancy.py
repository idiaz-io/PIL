"""Tenancy resolution — one function that produces the customer identity.

IDI-195 D1: shapes owns four things, and this is the third. I-5: "Tenant identity is never
taken from input."

**Why this is in shapes rather than in adapters.** The enforcement already existed and was
already strong — ``pil_adapters.Translation`` has no tenant field, so a translator has
nowhere to put one, and the base class is the only code that ever assigns ``tenant_id``.
That is better than a test: it does not compile the mistake in the first place.

But it lived in ``pil_adapters``, and ``contracts`` is a separate distribution precisely
because QUILL takes it *without* adapters. So QUILL got the envelope and no tenancy rule
at all, and would have had to write its own — which is the divergence D1 exists to
prevent, arriving by a different route than redaction did.

**The two sources of a tenant, and why only these two.**

*Request-driven work* has a validated token. The tenant is a claim in it. This module does
not validate tokens — that is a product's job, and the products differ — it takes the
already-validated claim and refuses everything else.

*Scheduled work* has no token at all. A poller wakes up on a timer; there is no caller and
no request. The tenant therefore comes from the adapter instance's own configuration, and
an instance may only ever emit for its configured tenant. This is the case AXO gets wrong
in eleven places today, by reaching into the vendor payload for something tenant-shaped —
splitting a URI, fuzzy-matching a team name, treating an MDM policy id as a customer id.

There is deliberately no third source. In particular there is no "derive it from the
payload if the configuration is missing" fallback, because that is exactly how the eleven
sites in AXO came to exist: each one is a reasonable-looking fallback that became the
normal path.

**What this module refuses to do.** It will not read a tenant out of a payload, and it has
no function that takes a payload. If you need to record what a payload *claimed*, that is
:class:`~pil_contracts.envelope.TenantHint` — evidence, never identity. Nothing may route,
authorise or query on a hint.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = ["TenancyError", "Tenant", "TenantSource", "resolve_tenant"]


class TenantSource(StrEnum):
    """Where a resolved tenant came from. A closed vocabulary (I-6).

    Recorded on the result because "this tenant came from configuration" and "this tenant
    came from a token claim" carry different weight in an audit, and because a third
    member appearing here should require an ADR rather than a commit.
    """

    #: A claim in a validated token. Request-driven work.
    TOKEN_CLAIM = "token_claim"

    #: The adapter instance's own configuration. Scheduled work, which has no token.
    ADAPTER_CONFIG = "adapter_config"


class TenancyError(ValueError):
    """A tenant could not be resolved, or something tried to resolve one unsafely.

    Its own type rather than a bare ``ValueError`` so that a caller can catch precisely
    this and so that a test can assert on it — an I-5 violation that surfaced as a generic
    parse error would be easy to swallow by accident.
    """


@dataclass(frozen=True, slots=True)
class Tenant:
    """A resolved customer identity, and where it came from.

    Frozen: once resolved, a tenant is not adjusted. Code that wants a different tenant
    resolves a different one, which keeps the decision at a single point.
    """

    tenant_id: str
    source: TenantSource

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.tenant_id.strip():
            raise TenancyError(
                "tenant_id is blank. I-5: a tenant is never optional and has no sensible "
                "default — a message with no owner cannot be authorised or scoped."
            )
        if self.tenant_id != self.tenant_id.strip():
            raise TenancyError(
                f"tenant_id {self.tenant_id!r} has surrounding whitespace. Two spellings "
                "of one tenant become two tenants in a store that keys on the string."
            )

    def __str__(self) -> str:
        return self.tenant_id


def resolve_tenant(
    *,
    token_claim: str | None = None,
    adapter_config_tenant: str | None = None,
) -> Tenant:
    """Produce the customer identity. The only function that may do so.

    Exactly one source must be supplied. Both are keyword-only, and neither has a
    positional form, so a call site always says which it means:

        resolve_tenant(token_claim=claims["tenant"])           # request-driven
        resolve_tenant(adapter_config_tenant=config.tenant_id) # scheduled

    Supplying both raises rather than picking one. A precedence rule here would be the
    beginning of the fallback chain this module exists to prevent — and if a caller holds
    both, it has a genuine ambiguity about who owns the work that silently preferring one
    would hide.

    Supplying neither also raises. There is no anonymous tenant.
    """
    if token_claim is not None and adapter_config_tenant is not None:
        raise TenancyError(
            "both a token claim and an adapter configuration tenant were supplied. There "
            "is no precedence rule on purpose: a caller holding both has an ambiguity "
            "about who owns this work, and choosing one silently would hide it. Resolve "
            "the ambiguity at the call site."
        )

    if token_claim is not None:
        return Tenant(_require_str(token_claim, "token_claim"), TenantSource.TOKEN_CLAIM)

    if adapter_config_tenant is not None:
        return Tenant(
            _require_str(adapter_config_tenant, "adapter_config_tenant"),
            TenantSource.ADAPTER_CONFIG,
        )

    raise TenancyError(
        "no tenant source was supplied. Request-driven work passes a validated token "
        "claim; scheduled work passes the adapter instance's configured tenant. There is "
        "no third source, and in particular a vendor payload is never one (I-5)."
    )


def _require_str(value: Any, name: str) -> str:
    """Reject non-strings loudly.

    A tenant arriving as an ``int`` is how ``42`` and ``"42"`` become two tenants, and how
    a ``None`` becomes the string ``"None"`` and then a real-looking row in a store.
    """
    if not isinstance(value, str):
        raise TenancyError(
            f"{name} must be a string, got {type(value).__name__} ({value!r}). Coercing "
            "would let 42 and '42' become two tenants."
        )
    return value
