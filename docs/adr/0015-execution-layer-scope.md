# ADR-0015 — The execution layer: outbound HTTP is not I-1's network surface; secret resolution stays the caller's job

**Status:** Accepted — decided by Hiba, 2026-09-19 · **Relates to:** ADR-0005
(translate-only scope, deferred `connect`/`execute_on_device`/`check_connectivity`/
`fetch_device_details`/`verify_*`), ADR-0006 (contracts is dependency-free), ADR-0008
(`ConnectionProvider`, IDI-195 D2/D3), ADR-0011 (graph ships no live driver, the consumer
injects one — the precedent this ADR extends), `docs/decisions/credential-scoping.md`
(approved 2026-09-19), `docs/reference/PIL-PLAN.md` (Thu–Fri — adapter framework, finish)

## Decision

Two things, decided together because Phase 3's first real adapter (Fleet's connect/fetch/
execute) forces both at once.

**1. An outbound HTTP client in `packages/adapters` does not violate I-1.** I-1 bans PIL
becoming a network *service* — something with a listening surface a state-changing write
could reach without going through the policy gate. It does not ban PIL's own code making
outbound calls, as a client, when a caller who has already cleared the gate invokes an
execution method. `packages/adapters` gains a dependency on `httpx`; `pil_contracts` does
not, and stays dependency-free (ADR-0006, enforced by
`tests/test_invariants.py::test_contracts_declares_no_dependencies` and
`test_contracts_imports_nothing_from_this_repo_or_outside_the_stdlib`, which scan
`packages/contracts` specifically and would fail if `httpx` ever landed there by mistake).

**2. PIL never resolves a `CredentialHandle` to a secret value. Not a Phase A limitation —
a permanent architectural boundary, same posture as `pil_graph` shipping no live Neo4j
driver (ADR-0011).** The execution layer's classes take an already-resolved token from
their caller, as a plain string, never a handle to resolve themselves. `FleetExecutor`'s
constructor is `(endpoint: str, token: str)` — it does not import `CredentialHandle` or
`ConnectionProvider` at all.

## Context

### Why an HTTP client isn't a network surface

I-1's own stated reason, from `CLAUDE.md`: *"MERP requires that no state-changing write can
bypass the policy gate; a library enforces that by not compiling if you skip it, a network
service only enforces it by convention that erodes."* That reasoning is about PIL being
*reachable* — an inbound surface. An `httpx.AsyncClient` call to Fleet's REST API, made
inside a method a caller invokes explicitly, is the opposite direction: PIL as a client
acting on behalf of a caller, not PIL as a destination anything can reach unguarded. The
existing banned-imports test's denylist (`fastapi`, `flask`, `django`, `starlette`,
`uvicorn`, `socket`, `socketserver`) is entirely server/listening-shaped. `httpx` was never
on it — consistent with the distinction already being implicit, not a gap being exploited
here for the first time.

`socket`/`socketserver` deserve a specific note: they're banned as *primitives a server is
built from* (binding, listening, accepting), not as a proxy for "anything network-shaped."
An HTTP client library sits on top of them internally but exposes no bind/listen/accept
surface itself — see the new test below, which checks the property directly rather than by
proxy through an import denylist.

### Why secret resolution doesn't move to PIL, even partially

The original proposal for this ADR included `resolve_secret(handle: CredentialHandle) ->
str`, dispatching on `SecretStore`: trivial for `ENVIRONMENT` (`os.environ[name]`), and an
`httpx` call to Vault's KV v2 API for `VAULT`. Checking that proposal against what it would
actually require exposed the flaw: `CredentialHandle` carries only `store` and `name` — not
a Vault server address or a master/service token. Resolving a `VAULT`-backed handle for
real would force PIL to read `VAULT_ADDR`/`VAULT_TOKEN` from its own environment, which is
the exact anti-pattern `docs/reference/axo-inventory.md` documents in AXO's own Vault
client: *"process-global, not tenant-configurable... nothing resolves the `vault_addr`/
`vault_token` values a tenant might type into the Integrations screen's form."* Building
this into PIL would not be neutral infrastructure — it would be PIL assuming a specific
secret store's deployment topology, which is exactly what ADR-0011 already declined to do
for the graph driver, for the same reason (`[NEEDS-DECISION: ADR-17]`, sovereign/air-gap vs.
AWS, unresolved). A resolver that only handled `ENVIRONMENT` and left `VAULT` to the caller
was considered and rejected too: it would make the contract inconsistent (does a caller
supply a handle or a token, depending on which store?) for no real savings, since a caller
must handle `VAULT` resolution regardless.

A narrower reading of `connection.py`'s own existing docstring supports this without
contradiction: *"resolving a credential to its value... When one does [need it], it
resolves the handle at the moment of use (I-8)."* That sentence never assigned *who*
resolves it. A caller — who has Vault access and knows the deployment's answer to
ADR-17 — resolving the handle immediately before calling PIL's execution method satisfies
"at the moment of use" exactly as well as PIL doing it internally, without requiring PIL to
know anything about Vault's address or master token.

## Alternatives

**PIL resolves secrets internally, `ENVIRONMENT` and `VAULT` both.** Rejected — requires
PIL to read `VAULT_ADDR`/`VAULT_TOKEN` from its own environment, replicating AXO's
documented anti-pattern and assuming a deployment topology ADR-17 hasn't settled.

**PIL resolves `ENVIRONMENT` only, callers resolve `VAULT`.** Rejected — an inconsistent
contract (sometimes a handle, sometimes a token, depending on store) that saves little,
since callers must handle `VAULT` either way.

**Ban `httpx` and defer all of connect/fetch/execute again.** Rejected — ADR-0005 already
deferred this once, explicitly, not permanently; Phase 3 is what that deferral was for.
Deferring again with no new information would be indecision dressed as caution.

## Consequences

- `packages/adapters/pyproject.toml` gains `httpx` as a dependency. `packages/contracts`
  is untouched.
- New subpackage `pil_adapters.execution`: `shapes.py` (`DeviceProfile`,
  `ConnectivityResult`, `ExecutionResult`, `VerificationResult` — tool-agnostic, shared
  across future adapters' execution ports) and `fleet.py` (`FleetExecutor`, taking
  `(endpoint: str, token: str)`, never a `CredentialHandle`).
- `packages/adapters/tests/test_connection.py::test_nothing_here_resolves_a_secret_value`'s
  docstring is updated (not its assertion, which still holds and now holds permanently) to
  say what it now means: not "not yet," but "never, by design — see ADR-0015."
- New test asserting `pil_adapters.execution` contains no server-shaped construct (`bind(`,
  `listen(`, `accept(`), the structural check for Decision 1, alongside the existing
  import-based one.
- `verify_alert_cleared`'s `policy_query` becomes a caller-supplied parameter (AXO's
  `healing_queue` table stays a product dependency PIL must not reach into — I-3,
  unaffected by this ADR, recorded here only because the same port surfaces it).
- The dead `/scripts/run/sync` branch in AXO's `execute_on_device` is not ported; recorded
  in `docs/known-differences.md` per I-10.
- No new `ConnectionProvider` implementation. `FileConnectionProvider` remains sufficient;
  the "fourth store" stays deferred per ADR-0008's own trigger (a second product needing a
  tool connection), converging with `docs/decisions/credential-scoping.md`'s recommendation
  without requiring anything further from it.
