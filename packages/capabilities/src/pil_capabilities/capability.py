"""The closed capability vocabulary: what a product may do to an external
system through a connection. Ported from merp-console's own `capabilities`
table (`supabase/migrations/0008_seeds.sql`), which ADR-0009 had cut PIL's
ownership of outright: "The bus and the capability catalogue are cut, not
deferred. No `pil_bus`, no catalogue, and no residue in the docs naming
either as a planned component." ADR-0012 narrows that decision back for
this table specifically — the bus stays cut.

A standalone package, not a module inside `pil_contracts` or `pil_adapters`:

- **Not `pil_contracts`.** That package's own charter is message shape —
  Envelope, AlertBody, tenant resolution, versioning, redaction of message
  fields (its own docstring: "the shapes every MERP message takes"). A
  capability isn't a message shape, it's a permission vocabulary — filing
  it there would be lumping shape data and authorization data under one
  name for the sole reason that both happen to be "a closed vocabulary,"
  which is exactly the reasoning that does *not* hold elsewhere in this
  repo: `SecretStore` and `Access` are also closed vocabularies, and they
  live in `pil_adapters` next to `ConnectionProvider`/`CredentialHandle` —
  the domain that actually defines them — not centralised into contracts
  merely for being an enum. `Capability` follows that same precedent: its
  own package, because its domain (authorization) is neither contracts'
  domain (wire shape) nor adapters' domain (vendor translation).
- **Not `pil_adapters`**, for the opposite reason: which capability a given
  translator actually provides is real adapters-domain data (see
  `pil_adapters.capabilities`), changing at the same cadence as new
  translators land. This module is the closed, ADR-gated vocabulary itself
  — ten strings and their risk — which changes far less often and for a
  different reason (I-6: extend by property, never by member, an ADR to
  add one). Tying the two together in one package would bind a
  rarely-changing vocabulary's release to a routinely-changing mapping's.

Closed (I-6): extend by adding a property to :class:`CapabilityDefinition`,
never by adding a member to :class:`Capability` without an ADR.
``risk`` is a fact PIL asserts outright — whether exercising the capability
mutates the external system. ``requires_signature_default`` is exactly
that, a default: MERP's policy layer may override it for a given
tenant/capability without this module changing, the same way
merp-console's own schema already treats it ("stored, not computed, so
policy can override without a schema change" — its `capabilities` table
comment).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

__all__ = ["CAPABILITIES", "CAPABILITY_COUNT", "Capability", "CapabilityDefinition", "Risk"]


class Capability(StrEnum):
    """What a product may do to an external system through a connection.
    The set is closed — see the module docstring."""

    HOST_READ = "host.read"
    HOST_LIST = "host.list"
    ALERT_SUBSCRIBE = "alert.subscribe"
    REPO_READ = "repo.read"
    LLM_INFER = "llm.infer"
    SCRIPT_EXECUTE = "script.execute"
    POLICY_ENFORCE = "policy.enforce"
    TICKET_CREATE = "ticket.create"
    NOTIFY_SEND = "notify.send"
    REPO_WRITE = "repo.write"


#: Pinned so an addition on this side fails its own test rather than
#: silently drifting from what merp-console's schema expects.
CAPABILITY_COUNT: Final = 10


class Risk(StrEnum):
    """Whether exercising a capability mutates the external system."""

    READ = "read"
    WRITE = "write"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """One capability's fact sheet.

    ``requires_signature_default`` is named ``_default`` on purpose — see
    the module docstring. It is not this module's job to be the final word
    on whether a signature is required; it is this module's job to say
    what happens absent an override.
    """

    key: Capability
    risk: Risk
    requires_signature_default: bool
    description: str


#: Values ported verbatim from `0008_seeds.sql`'s own `insert into
#: public.capabilities` — including that migration's own inference that
#: `requires_signature` mirrors `risk` (write => True) for every row.
CAPABILITIES: Mapping[Capability, CapabilityDefinition] = {
    Capability.HOST_READ: CapabilityDefinition(
        Capability.HOST_READ, Risk.READ, False, "Read host inventory and state."
    ),
    Capability.HOST_LIST: CapabilityDefinition(
        Capability.HOST_LIST, Risk.READ, False, "List hosts."
    ),
    Capability.ALERT_SUBSCRIBE: CapabilityDefinition(
        Capability.ALERT_SUBSCRIBE, Risk.READ, False, "Subscribe to alerts."
    ),
    Capability.REPO_READ: CapabilityDefinition(
        Capability.REPO_READ, Risk.READ, False, "Read repository contents."
    ),
    Capability.LLM_INFER: CapabilityDefinition(
        Capability.LLM_INFER, Risk.READ, False, "Run LLM inference."
    ),
    Capability.SCRIPT_EXECUTE: CapabilityDefinition(
        Capability.SCRIPT_EXECUTE, Risk.WRITE, True, "Execute a script on a host."
    ),
    Capability.POLICY_ENFORCE: CapabilityDefinition(
        Capability.POLICY_ENFORCE, Risk.WRITE, True, "Enforce a policy action."
    ),
    Capability.TICKET_CREATE: CapabilityDefinition(
        Capability.TICKET_CREATE, Risk.WRITE, True, "Create a ticket."
    ),
    Capability.NOTIFY_SEND: CapabilityDefinition(
        Capability.NOTIFY_SEND, Risk.WRITE, True, "Send a notification."
    ),
    Capability.REPO_WRITE: CapabilityDefinition(
        Capability.REPO_WRITE, Risk.WRITE, True, "Write to a repository."
    ),
}
