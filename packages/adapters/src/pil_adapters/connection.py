"""How an adapter obtains connection details. IDI-195 D2 and D3.

D2: "Adapters must obtain connection details (endpoint, credential handle) through an
**interface**, never by reading AXO's database, AXO config objects, or anything else
product-owned. If adapters currently reach into AXO for config, PIL depends on a product
and the whole point of the extraction is lost."

D3: "The config shape must allow AXO and QUILL to hold **different credentials for the same
tool**. QUILL read-only; AXO with permission to make changes. One shared login per tool
means QUILL can do things it should never be able to do."

---

**What is here and what is deliberately not.**

Here: the interface (:class:`ConnectionProvider`), the shape a resolved connection takes
(:class:`ToolConnection`), and a plain config-file implementation
(:class:`FileConnectionProvider`). That is what D2 says is required now.

Not here: the real tenant-configuration store. D2 is explicit that it is a fourth store
alongside graph, ledger and runbook vault, and that it gets built when a second product
needs a tool connection. A provider is an interface with one file-backed implementation
until then.

Also not here: resolving a credential to its value. Phase A translates and nothing more —
nothing in PIL opens a socket — so no code path needs the secret yet. When one does, it
resolves the handle at the moment of use (I-8).

**Why credentials are keyed by product and not by tool.**

The obvious shape is one credential per tool: Fleet has an API key, so put the API key on
the Fleet connection. That shape cannot express what D3 requires. QUILL reads compliance
evidence and must never change anything; AXO remediates and needs write access. One shared
login per tool gives QUILL AXO's permissions, and the failure is silent — nothing breaks,
QUILL simply becomes able to do things it should not.

So the credential is keyed by ``(tool, product)``, and there is no tool-level default to
fall back to. A missing credential for a product is an error, not an inheritance.

This is the cheap moment to get it right: no credentials exist in production yet, so the
shape costs a keyword argument today and a migration later.

**Secrets are handles, never values** (I-8). :class:`CredentialHandle` holds a *reference* —
which secret store, and a name within it. Nothing in this module accepts, stores or returns
a secret value, and ``__repr__`` is overridden so a handle cannot be logged into looking
like one.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

__all__ = [
    "Access",
    "ConnectionNotConfiguredError",
    "ConnectionProvider",
    "CredentialHandle",
    "FileConnectionProvider",
    "SecretStore",
    "StaticConnectionProvider",
    "ToolConnection",
]


class SecretStore(StrEnum):
    """Where a secret actually lives. A closed vocabulary (I-6).

    Named rather than free text because a handle is only resolvable if the resolver knows
    which store to ask, and a typo in a free-text field would surface as a missing secret
    at the moment of use — which for a scheduled poller means at 3am.
    """

    #: HashiCorp Vault. What AXO uses in production.
    VAULT = "vault"

    #: Process environment. Local development and CI.
    ENVIRONMENT = "environment"


class Access(StrEnum):
    """What a credential is permitted to do. A closed vocabulary (I-6).

    This is the field that makes D3 enforceable rather than aspirational. A provider can
    hand QUILL a ``READ_ONLY`` handle and AXO a ``READ_WRITE`` one for the same tool, and
    a caller can assert on it before acting — so "QUILL must never change anything" becomes
    checkable in code rather than a property of how the credential was provisioned.
    """

    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


@dataclass(frozen=True, slots=True)
class CredentialHandle:
    """A reference to a secret. Never the secret (I-8).

    ``store`` says who to ask, ``name`` says what to ask for, ``access`` records what the
    referenced credential is permitted to do so a caller can refuse before acting rather
    than discovering it from a 403.
    """

    store: SecretStore
    name: str
    access: Access = Access.READ_ONLY

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError(
                "CredentialHandle.name is required. A handle that names nothing cannot be "
                "resolved, and the failure would surface at the moment of use rather than "
                "at configuration time."
            )
        # Cheap guard against a *value* being passed where a *name* belongs. Not
        # foolproof, and not meant to be — but a PEM body or a long bearer token in this
        # field is a mistake worth failing loudly on, because everything downstream treats
        # this string as safe to log.
        if len(self.name) > 256 or "\n" in self.name or self.name.startswith("-----BEGIN"):
            raise ValueError(
                "CredentialHandle.name looks like a secret value rather than a reference. "
                "I-8: adapter configuration holds a handle; the value is resolved at the "
                "moment of use and never stored."
            )

    def __repr__(self) -> str:
        """Deliberately explicit that this is a reference.

        A handle is safe to log, and this repr is written so that a reader of a log line
        can tell at a glance that nothing sensitive is in it.
        """
        return (
            f"CredentialHandle(store={self.store.value!r}, name={self.name!r}, "
            f"access={self.access.value!r})"
        )

    @property
    def can_write(self) -> bool:
        return self.access is Access.READ_WRITE


@dataclass(frozen=True, slots=True)
class ToolConnection:
    """Everything an adapter needs to reach one tool, for one tenant, for one product.

    Note what is absent: no secret value, no database handle, no product object, no session.
    An adapter given one of these cannot reach back into a product even by accident, which
    is the property D2 is protecting.
    """

    tool: str
    tenant_id: str
    product: str
    endpoint: str
    credential: CredentialHandle

    #: Vendor-specific knobs that are not secret — page sizes, API versions, team filters.
    #: Deliberately untyped: constraining it would mean this module knowing about individual
    #: vendors, and it does not.
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("tool", "tenant_id", "product", "endpoint"):
            value = getattr(self, name)
            if not value or not str(value).strip():
                raise ValueError(f"ToolConnection.{name} is required and may not be blank")

    @property
    def read_only(self) -> bool:
        return not self.credential.can_write


class ConnectionNotConfiguredError(LookupError):
    """No connection is configured for this (tool, tenant, product).

    A distinct type so a caller can tell "not configured" from "configured and broken".
    Raised rather than returning ``None``: a provider returning ``None`` invites
    ``or default``, and a default connection is how a tenant ends up talking to another
    tenant's endpoint.
    """


class ConnectionProvider(ABC):
    """The interface D2 requires. The only way an adapter learns how to reach a tool.

    Implementations may read a file, a store, or hold values in memory. What they may not
    do is read a product's database or configuration objects — that is the dependency
    direction I-3 forbids and the thing that would make the extraction cosmetic.

    Deliberately not ``async``. A file read and a dictionary lookup are not I/O worth
    colouring the whole call graph for, and Phase A has no provider that needs it. When one
    does, it gets an async sibling rather than making every caller a coroutine.
    """

    @abstractmethod
    def connection_for(self, tool: str, tenant_id: str, product: str) -> ToolConnection:
        """Return the connection for one tool, tenant and product.

        All three are required, and none has a default. ``product`` in particular: making
        it optional would immediately produce a "the credential for this tool" lookup,
        which is precisely the shape D3 rules out.

        Raises :class:`ConnectionNotConfiguredError` when there is no such connection.
        """

    def has_connection(self, tool: str, tenant_id: str, product: str) -> bool:
        """Whether a connection exists, without raising.

        For callers deciding whether to schedule work at all, so that "not configured" does
        not have to be discovered through an exception on a hot path.
        """
        try:
            self.connection_for(tool, tenant_id, product)
        except ConnectionNotConfiguredError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class StaticConnectionProvider(ConnectionProvider):
    """A provider over an in-memory mapping. For tests and for callers that already hold
    their configuration.

    Keyed ``(tool, tenant_id, product)``. This is also the test double D2's report-only
    section notes PIL will eventually need in quantity — shipping it here means AXO and
    QUILL do not each write their own and drift.
    """

    connections: Mapping[tuple[str, str, str], ToolConnection] = field(default_factory=dict)

    def connection_for(self, tool: str, tenant_id: str, product: str) -> ToolConnection:
        try:
            return self.connections[(tool, tenant_id, product)]
        except KeyError:
            raise _not_configured(tool, tenant_id, product, sorted(self.connections)) from None


class FileConnectionProvider(ConnectionProvider):
    """The plain config-file implementation D2 asks for. JSON, read on construction.

    Shape:

    .. code-block:: json

        {
          "connections": [
            {
              "tool": "fleet",
              "tenant_id": "tenant-acme",
              "product": "axo",
              "endpoint": "https://fleet.example.com",
              "credential": {"store": "vault", "name": "axo/fleet/acme", "access": "read_write"},
              "options": {"per_page": 100}
            },
            {
              "tool": "fleet",
              "tenant_id": "tenant-acme",
              "product": "quill",
              "endpoint": "https://fleet.example.com",
              "credential": {"store": "vault", "name": "quill/fleet/acme", "access": "read_only"}
            }
          ]
        }

    Those two entries are the point of D3: one tool, one tenant, two products, two
    credentials, two permission levels. The file cannot express a tool-level credential,
    so it cannot accidentally give QUILL write access.

    Read once at construction rather than per call. A provider is cheap to rebuild, and
    re-reading per call would put a file system access on every poll — while caching
    *within* a call and not across construction keeps the "flip config, no deploy"
    behaviour where it belongs, in the product's switch rather than here.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._connections = _load(self._path)

    @property
    def path(self) -> Path:
        return self._path

    def connection_for(self, tool: str, tenant_id: str, product: str) -> ToolConnection:
        try:
            return self._connections[(tool, tenant_id, product)]
        except KeyError:
            raise _not_configured(
                tool, tenant_id, product, sorted(self._connections), source=str(self._path)
            ) from None

    def __repr__(self) -> str:
        return (
            f"FileConnectionProvider(path={str(self._path)!r}, "
            f"connections={len(self._connections)})"
        )


# ----------------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------------

#: Product names must be simple, because they end up in secret paths and log lines.
_PRODUCT_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


def _not_configured(
    tool: str,
    tenant_id: str,
    product: str,
    known: list[tuple[str, str, str]],
    source: str = "the provider",
) -> ConnectionNotConfiguredError:
    """Build an error that says what was asked for and what exists.

    Worth the effort: the common mistake is asking for the right tool and tenant under the
    wrong product name, and a bare KeyError makes that indistinguishable from a missing
    tenant.
    """
    detail = ""
    same_tool = [entry for entry in known if entry[0] == tool]
    if same_tool:
        listed = ", ".join(f"({t}, {n}, {p})" for t, n, p in same_tool[:8])
        detail = f" Configured for {tool!r}: {listed}."
    return ConnectionNotConfiguredError(
        f"no connection configured for tool={tool!r} tenant={tenant_id!r} "
        f"product={product!r} in {source}.{detail} Credentials are per product, not per "
        "tool (IDI-195 D3), so there is deliberately no tool-level entry to fall back to."
    )


def _load(path: Path) -> dict[tuple[str, str, str], ToolConnection]:
    if not path.is_file():
        raise FileNotFoundError(
            f"no connection configuration at {path}. FileConnectionProvider is the plain "
            "file implementation of the provider interface; point it at a JSON file, or "
            "use StaticConnectionProvider in tests."
        )

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc

    entries = raw.get("connections") if isinstance(raw, Mapping) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path} must hold a 'connections' array")

    loaded: dict[tuple[str, str, str], ToolConnection] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"{path}: connections[{index}] must be an object")
        connection = _connection_from(entry, f"{path}: connections[{index}]")
        key = (connection.tool, connection.tenant_id, connection.product)
        if key in loaded:
            # Silently keeping the last would mean a duplicated block quietly overriding
            # a credential — including replacing a read-only one with read-write.
            raise ValueError(
                f"{path}: duplicate connection for tool={key[0]!r} tenant={key[1]!r} "
                f"product={key[2]!r}. Two entries for one key means one of them is being "
                "ignored, and which one would depend on file order."
            )
        loaded[key] = connection
    return loaded


def _connection_from(entry: Mapping[str, Any], where: str) -> ToolConnection:
    credential_raw = entry.get("credential")
    if not isinstance(credential_raw, Mapping):
        raise ValueError(
            f"{where}: 'credential' must be an object holding a secret handle. I-8: "
            "configuration holds a reference, never a value."
        )

    store_raw = credential_raw.get("store")
    try:
        store = SecretStore(str(store_raw))
    except ValueError:
        known = ", ".join(member.value for member in SecretStore)
        raise ValueError(
            f"{where}: unknown secret store {store_raw!r}. Known stores: {known}. Adding "
            "one is an ADR (I-6), because a handle is only resolvable if the resolver "
            "knows which store to ask."
        ) from None

    access_raw = credential_raw.get("access", Access.READ_ONLY.value)
    try:
        access = Access(access_raw)
    except ValueError:
        known = ", ".join(member.value for member in Access)
        raise ValueError(f"{where}: unknown access {access_raw!r}. Known: {known}.") from None

    if "value" in credential_raw or "secret" in credential_raw or "password" in credential_raw:
        raise ValueError(
            f"{where}: a credential value is present in configuration. I-8: secrets are "
            "handles, never values — put the secret in a store and name it here."
        )

    product = str(entry.get("product", ""))
    if not _PRODUCT_PATTERN.match(product):
        raise ValueError(
            f"{where}: product {product!r} must be lowercase alphanumeric with - or _. "
            "It appears in secret paths and log lines, so it is kept boring on purpose."
        )

    options = entry.get("options") or {}
    if not isinstance(options, Mapping):
        raise ValueError(f"{where}: 'options' must be an object")

    return ToolConnection(
        tool=str(entry.get("tool", "")),
        tenant_id=str(entry.get("tenant_id", "")),
        product=product,
        endpoint=str(entry.get("endpoint", "")),
        credential=CredentialHandle(
            store=store,
            name=str(credential_raw.get("name", "")),
            access=access,
        ),
        options=dict(options),
    )
