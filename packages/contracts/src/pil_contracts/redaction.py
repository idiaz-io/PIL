"""Redaction — one implementation, owned by shapes.

IDI-195 D1: shapes owns four things, and this is the fourth. "One implementation that
strips credentials and marks classified data. If AXO and QUILL redact differently, we
leak."

That was not a hypothetical when this module was written. There were two redactors, both
inside one product and neither in shapes:

* ``apps/exoagent/internal/evidence/evidence.go:13-16`` — the Go agent's, shipped first
* ``backend/services/pil_capture.py`` — the Python one, whose own comment records that it
  was ported from the Go file above

Two implementations, one product, and QUILL not yet written. This module is the single
implementation both of those become callers of.

**Where redaction is applied is a separate question from who owns it.** This module
deliberately does not hook itself into :class:`~pil_contracts.envelope.Envelope`
construction. AXO stores the vendor payload untouched, and I-10 requires PIL's translator
output to be byte-identical to AXO's during the migration — so silently redacting
``raw_payload`` in ``translate()`` would break parity and, worse, would be a behaviour
improvement smuggled into a migration. :meth:`Envelope.redacted` is available for callers
that want it, and the emit boundary is where it belongs. See ``docs/known-differences.md``.

**Two operations, kept apart because they answer different questions.**

*Stripping* removes credentials. It is irreversible and unconditional: a credential must
never reach a message, a log, a fixture or a ledger entry (I-8). Nothing keys off the
original value, so there is nothing to preserve.

*Pseudonymising* replaces a customer-identifying value with a stable fake. It needs a salt,
is keyed so it cannot be reversed without one, and is stable so that joins between payloads
survive — two payloads naming the same host still name the same host afterwards. This is
what makes a captured corpus usable without holding real customer data.

**Structure is never perturbed.** Same keys, same nesting, same types, same
null/empty/missing distinctions — only leaf values change. The translators under test branch
on which keys are present and on whether a value is empty, so a scrubber that dropped an
empty string or collapsed a null would silently change what the corpus tests.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

__all__ = [
    "REDACTED",
    "Classification",
    "Redaction",
    "classify_key",
    "pseudonymise",
    "redact",
    "redact_text",
]

#: What replaces a stripped credential. A visible marker rather than an empty string, so
#: that "this field held a secret" survives while the secret does not.
REDACTED: Final = "[REDACTED]"


class Classification(StrEnum):
    """How sensitive a value is. A closed vocabulary (I-6) — adding a member is an ADR.

    Ordered by how much damage disclosure does, least first. The point of naming these is
    that "marks classified data" needs somewhere to put the mark; a boolean would collapse
    "this is a customer's hostname" into "this is an API token", and those want different
    handling.
    """

    #: Nothing identifying and nothing secret. Severities, categories, policy names.
    PUBLIC = "public"

    #: Operational detail that is ours rather than a customer's. Internal ids, counters.
    INTERNAL = "internal"

    #: Identifies a real customer, host or person. Pseudonymised, not stripped — the
    #: shape of the value matters to the code under test.
    CONFIDENTIAL = "confidential"

    #: A credential. Stripped unconditionally and never pseudonymised: there is no
    #: use for a stable fake password, and keeping one invites treating it as real.
    SECRET = "secret"


# ----------------------------------------------------------------------------------
# Credential stripping
# ----------------------------------------------------------------------------------

#: Free-text credential patterns. Byte-for-byte the pair used by both existing AXO
#: redactors (`evidence.go:13-16`, `pil_capture.py:67`), so that adopting this module
#: changes no output anywhere and the corpus captured before it stays valid.
#:
#: The first catches ``key: value`` and ``key=value`` shapes. The second catches long
#: base64-ish runs — bearer tokens, PEM bodies, signatures — which carry no label to
#: match on. The 40-character floor is what keeps it from eating ordinary identifiers;
#: it is deliberately conservative, and a UUID (36, with hyphens) does not match.
_CREDENTIAL_PATTERNS: Final = (
    re.compile(r"(?i)(password|secret|token|key|credential|api[_-]?key)\s*[=:]\s*\S+"),
    re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b"),
)

#: Keys whose *value* is a credential regardless of what the value looks like. The
#: patterns above only fire on text that advertises itself; a bare password under a key
#: called ``password`` looks like any other word.
_SECRET_KEYS: Final = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "bearer",
        "authorization",
        "auth",
        "api_key",
        "apikey",
        "api-key",
        "key",
        "private_key",
        "credential",
        "credentials",
        "session_key",
        "signature",
        "sig",
    }
)

#: Keys whose value identifies a real customer, host or person, mapped to the pseudonym
#: prefix used for that kind. The prefix keeps a scrubbed corpus readable — a reviewer can
#: still tell a host from a person without being able to recover either.
#:
#: Matched case-insensitively against the leaf key name anywhere in the payload tree.
#:
#: **This is AXO's list, adopted verbatim** from ``pil_capture.py:75-113``, prefixes
#: included. Moving ownership into shapes must not change output: several entries are
#: tuned to specific vendors (``yname`` and ``aligned_resource_name`` are ScienceLogic's
#: field names) and a generic replacement would quietly stop protecting them. Improving
#: the list is a separate commit from moving it — a commit that does both is two commits
#: pretending to be one.
_CONFIDENTIAL_KEYS: Final = {
    # hosts
    "hostname": "host",
    "host_name": "host",
    "device_name": "host",
    "element_name": "host",
    "aligned_resource_name": "host",
    "yname": "host",
    "fqdn": "host",
    "computer_name": "host",
    "display_name": "host",
    "name": "name",
    # network
    "ip": "ip",
    "ip_address": "ip",
    "primary_ip": "ip",
    "public_ip": "ip",
    "private_ip": "ip",
    "mac": "mac",
    "mac_address": "mac",
    # hardware
    "serial": "serial",
    "serial_number": "serial",
    "uuid": "uuid",
    "host_uuid": "uuid",
    # tenancy — pseudonymised, but the *structure* of how the tenant is expressed is
    # exactly what the translators are tested against, so only values are replaced and
    # URI-shaped references keep their shape.
    "organization": "org",
    "organization_name": "org",
    "org_name": "org",
    "client_name": "org",
    "company_name": "org",
    "identifier": "org",
    # people
    "email": "email",
    "user": "user",
    "username": "user",
    "owner": "user",
    "contact": "user",
}


def classify_key(key: str) -> Classification:
    """Classify a payload key by name.

    By name only, and that is the honest limit of it: a key called ``notes`` holding a
    pasted password classifies as ``PUBLIC`` here. :func:`redact_text` is the second line
    of defence for exactly that case, which is why every string value passes through it
    regardless of how its key classified.
    """
    lowered = key.lower()
    if lowered in _SECRET_KEYS:
        return Classification.SECRET
    if lowered in _CONFIDENTIAL_KEYS:
        return Classification.CONFIDENTIAL
    return Classification.PUBLIC


def redact_text(value: str) -> str:
    """Strip anything that looks like a credential from free text.

    Applied to every string value in a payload, whatever its key classified as. Cheap,
    and the only thing that catches a credential in a field nobody expected to hold one.
    """
    out = value
    for pattern in _CREDENTIAL_PATTERNS:
        out = pattern.sub(REDACTED, out)
    return out


def pseudonymise(value: str, kind: str, salt: bytes) -> str:
    """Map an identifying value to a stable fake one.

    HMAC rather than a plain hash: without the salt the mapping cannot be reversed by
    guessing inputs, and hostnames and company names have a small enough space that a
    bare SHA-256 would be a lookup table.
    """
    digest = hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{kind}-{digest[:12]}"


# ----------------------------------------------------------------------------------
# The recursive pass
# ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Redaction:
    """A redacted payload and what was found in it.

    ``marks`` is the "marks classified data" half of D1. It records what classifications
    were present, by path, so a caller can say "this message carried credentials" without
    holding them. Paths use the same ``$.a.b[0]`` form as ``canonical.py``'s errors.
    """

    payload: Any
    marks: dict[str, Classification] = field(default_factory=dict)

    @property
    def held_secrets(self) -> bool:
        """True when at least one credential was stripped.

        Worth acting on: a vendor payload carrying a credential usually means the
        integration is configured to send more than it should.
        """
        return any(mark is Classification.SECRET for mark in self.marks.values())

    @property
    def classifications(self) -> frozenset[Classification]:
        return frozenset(self.marks.values())


def redact(payload: Any, *, salt: bytes | None = None) -> Redaction:
    """Strip credentials and mark classified data, recursively.

    ``salt`` enables pseudonymisation of customer-identifying values. Without it those
    values are left alone but still *marked*, because the two jobs are separable: a sink
    writing into a tenant-scoped store already knows whose data it holds and wants the
    real hostname, while a fixture leaving production does not.

    Credential stripping is not optional and does not depend on the salt. It is the half
    that cannot be deferred to a caller's judgement.
    """
    marks: dict[str, Classification] = {}
    result = _walk(payload, "$", salt, marks)
    return Redaction(result, marks)


def _walk(value: Any, path: str, salt: bytes | None, marks: dict[str, Classification]) -> Any:
    if isinstance(value, Mapping):
        return {key: _leaf(key, item, f"{path}.{key}", salt, marks) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_walk(item, f"{path}[{index}]", salt, marks) for index, item in enumerate(value)]
    if isinstance(value, str):
        return _mark_if_changed(value, redact_text(value), path, marks)
    return value


def _leaf(
    key: str,
    value: Any,
    path: str,
    salt: bytes | None,
    marks: dict[str, Classification],
) -> Any:
    if isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    ):
        return _walk(value, path, salt, marks)

    classification = classify_key(key)

    if classification is Classification.SECRET:
        # Unconditional, and applied whatever the value's type — a numeric API key is
        # still an API key. Nothing downstream has a use for it.
        marks[path] = Classification.SECRET
        return REDACTED

    if classification is Classification.CONFIDENTIAL and isinstance(value, str) and value:
        marks[path] = Classification.CONFIDENTIAL
        if salt is None:
            return redact_text(value)
        return _pseudonymise_preserving_shape(value, _CONFIDENTIAL_KEYS[key.lower()], salt)

    if isinstance(value, str):
        return _mark_if_changed(value, redact_text(value), path, marks)
    return value


def _pseudonymise_preserving_shape(value: str, kind: str, salt: bytes) -> str:
    """Pseudonymise, keeping URI-shaped references URI-shaped.

    SL1 names an organisation as ``/api/organization/42``, and AXO derives the tenant by
    splitting that on ``/`` (`sl_poller.py:307`). Replacing the whole string would delete
    the very edge case the corpus exists to capture, so only the final segment moves.
    """
    if "/" in value:
        head, _, tail = value.rpartition("/")
        return f"{head}/{pseudonymise(tail, kind, salt)}" if tail else value
    return pseudonymise(value, kind, salt)


def _mark_if_changed(
    original: str,
    redacted: str,
    path: str,
    marks: dict[str, Classification],
) -> str:
    """Record a mark only when a pattern actually fired.

    Keeps ``marks`` a report of what was found rather than a list of every string in the
    payload, which is what makes ``held_secrets`` worth reading.
    """
    if redacted != original:
        marks[path] = Classification.SECRET
    return redacted
