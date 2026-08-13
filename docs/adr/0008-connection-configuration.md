# ADR-0008 — Adapters obtain connection details through an interface, keyed per product

**Status:** Accepted · **Date:** 2026-08-13 · **Amends:** [ADR-0005](0005-translate-only-scope.md) · **Closes:** IDI-195 D2, D3

## Decision

Adapters obtain connection details — endpoint, credential handle, non-secret options —
through `pil_adapters.connection.ConnectionProvider`, an interface. Never by reading a
product's database, a product's configuration objects, or anything else product-owned.

A credential is keyed by **(tool, tenant, product)**. There is no tool-level credential and
no fallback to one.

Shipped now: the interface, `ToolConnection`, `CredentialHandle`, a JSON
`FileConnectionProvider`, and `StaticConnectionProvider` for tests.

Not shipped now: the real tenant-configuration store, and any code that resolves a handle
to a secret value.

## Context

### Why this lands during a translate-only phase

ADR-0005 defers the `connect` **surface** — the methods that open a socket, execute on a
device, verify a result. That deferral stands, and nothing here connects to anything.

What ADR-0005 did not decide was where an adapter would *learn* how to reach a tool, and in
its absence the answer was nothing at all: `AdapterConfig` had one field, `tenant_id`. IDI-195
D2 says the interface is "required now", and the two are compatible — an interface with no
caller is not a connect surface. So this amends ADR-0005 rather than reversing it.

The audit found no violation to fix. PIL reads nothing from AXO today, and
`tests/test_invariants.py` fails if any module in either package imports a product, dynamic
and function-local imports included. The risk D2 names is prospective: the first adapter
that needs an endpoint is the moment someone reaches for AXO's `platform_settings`, because
that is where the endpoint already is. Having somewhere else to reach is what prevents it,
and it has to exist *before* that adapter is written.

### Why credentials are per product

The obvious shape is one credential per tool. Fleet has an API key, so the API key goes on
the Fleet connection. That shape cannot express what D3 requires.

QUILL reads compliance evidence and must never change anything. AXO remediates and needs
write access. With one credential per tool, QUILL holds AXO's — and the failure is silent.
Nothing errors, no test goes red; QUILL is simply able to do things it should never be able
to do, and the first evidence is an audit finding or an incident.

`Access` (`read_only` / `read_write`) is on the handle so this is checkable in code rather
than a property of how someone provisioned the credential. A caller can refuse before
acting instead of discovering it from a 403.

No credentials exist in production yet, which makes this the cheap moment: today it is a
keyword argument, later it is a migration of live secrets.

### Secrets are handles

I-8. `CredentialHandle` holds a store and a name. Nothing in the module accepts, stores or
returns a value; a `value`, `secret` or `password` key in a configuration file is rejected
outright, and a handle whose *name* looks like a PEM body or a long token is rejected too.
Everything downstream treats a handle as safe to log, so the guard is worth its
false-positive risk.

## Alternatives

**Defer both until Phase B, keeping ADR-0005 literal.** Rejected. It leaves no answer to
"where does an endpoint come from" at exactly the moment the question first gets asked, and
the nearest available answer is AXO's database — which is the defect. An unused interface
costs nothing to carry.

**One credential per tool, add a product dimension later.** Rejected, and this is the
decision D3 exists to force. Adding the dimension later means migrating live credentials
and auditing which products had been sharing which logins in the meantime. The shape is
free now.

**Make `product` an optional argument defaulting to the caller.** Rejected. It reads
harmlessly and produces exactly the per-tool lookup this ADR rules out, because the default
becomes the path everyone takes. `product` is required, positional-or-keyword, no default,
asserted by a test on the interface itself.

**Return `None` when nothing is configured.** Rejected. `None` invites `or default`, and a
default connection is how one tenant ends up talking to another tenant's endpoint.
`ConnectionNotConfiguredError` is a distinct type so "not configured" is
distinguishable from "configured and broken".

**Build the tenant-configuration store now.** Rejected, per D2: it is a fourth store
alongside graph, ledger and runbook vault, and it gets built when a second product needs a
tool connection. A file-backed provider is enough for Phase A and is not a store.

## Consequences

`AdapterConfig` still carries only the tenant. Connection details are a separate object
obtained separately, so a translator — which needs neither — is not handed a credential
handle it has no use for.

`ToolConnection` deliberately carries no session, database handle or product object. An
adapter given one cannot reach back into a product even by accident, which is the property
D2 protects, and the field set is asserted by a test so adding one is visible.

`FileConnectionProvider` reads once at construction rather than per call. "Flip
configuration, no deploy" belongs to the product's switch (`pil_shim.py`), not here; a
provider is cheap to rebuild when a caller wants fresh values.

Nothing resolves a handle yet, and a test asserts no `resolve_secret`-shaped function
appears in the module. When the connect surface arrives it brings its own ADR, and
resolution happens at the moment of use.

The registry still builds translators from `AdapterConfig` alone. Wiring a provider into
translator construction would imply translators need connections, and in Phase A they do
not.
