# ADR-0012 — Reviving the capability catalogue, narrowly

**Status:** Accepted — decided by Hiba, 2026-09-15 · **Amends:** ADR-0009 (the capability-
catalogue clause only — its bus/sink decision is untouched) · **Relates to:** ADR-0006
(contracts is dependency-free), ADR-0011 (the same "closed vocabulary gets its own home"
reasoning applied here), `docs/reference/pil-sourcing-proposal.md` (merp-console's own
account of why this catalogue had no PIL counterpart, until now)

## Decision

PIL now owns the capability-string vocabulary and `risk` for capabilities tied to
translators PIL actually implements, in a new package, `packages/capabilities`
(`pil-capabilities`). `requires_signature` ships as an overridable default
(`requires_signature_default`), not a policy ruling. `gitlab`'s and `connectwise`'s
inventory-path capability grants, and all of `product_requirements`, remain
console-authored — PIL has no translator for the former and no concept of a product for
the latter.

The adapter→capability *mapping* (which of PIL's own translators provides which
capability) lives in `pil_adapters.capabilities`, not in `pil_capabilities` itself — see
"Package boundary" below for why this is two packages' worth of data, not one.

## Context

ADR-0009 cut this catalogue outright: *"The bus and the capability catalogue are cut, not
deferred. No `pil_bus`, no catalogue, and no residue in the docs naming either as a
planned component."* That was correct at the time — both had zero consumers. One
consumer exists now: merp-console's hand-seeded `capabilities`/`adapter_capabilities`
tables (`supabase/migrations/0004`, `0005`, `0008`, `0017`, `0020`, `0022`), duplicating
strings PIL's own translators already imply through what they translate. A second is
coming: the policy gate (`PIL-PLAN.md`, Thursday) needs `risk`/`requires_signature` to
decide `allow`/`hold`/`deny` — exactly the second consumer ADR-0009 said didn't exist yet.

**What this does not revive.** The bus. ADR-0009's bus rationale (zero consumers, AXO
already has its own queue) is untouched by anything here.

### Package boundary: why `pil_capabilities` is its own package, not a module in
### `pil_contracts` or `pil_adapters`

The question raised directly: ten strings and a small mapping *might* belong in
`pil_contracts`, where the closed vocabularies already live. Checked against what's
actually there before answering, rather than assumed:

| Vocabulary | Lives in | Beside |
|---|---|---|
| `MessageKind` | `pil_contracts.envelope` | `Envelope` itself — it's one of Envelope's own fields |
| `TenantSource` | `pil_contracts.tenancy` | `resolve_tenant()` — intrinsic to tenant resolution |
| `Classification` | `pil_contracts.redaction` | `redact()` — intrinsic to field-level redaction |
| `SecretStore` | `pil_adapters.connection` | `CredentialHandle`/`ToolConnection` — **not contracts** |
| `Access` | `pil_adapters.connection` | same — **not contracts** |

Two of the three examples raised (`SecretStore`, `Access`) are **not** in `pil_contracts`
— they live in `pil_adapters`, next to the connection/credential machinery that defines
them. The actual, already-established convention in this repo is not "closed vocabularies
live in contracts" — it's **closed vocabularies live beside the domain that defines them**.
`pil_contracts` itself says what its domain is: *"the shapes every MERP message takes."*
`Capability` is not a message shape. It is a permission vocabulary — what a product may do
to an external system — and that domain isn't contracts' (wire shape) or adapters'
(vendor translation) either. Filing it in either would be grouping unlike things under one
name for the sole reason that both happen to be enums.

A separate package buys three concrete things a module-inside-an-existing-package doesn't:

1. **Correct domain naming**, per the table above — the same precedent ADR-0011 already
   used for the ITKG vocabulary (its own package, not folded into `pil_graph`'s eventual
   consumer or into contracts).
2. **Decoupled churn.** `pil_contracts` is kept deliberately minimal and stable —
   `Envelope`/`AlertBody` are the one shape every consumer, including a bare QUILL
   checkout, depends on staying put. The capability catalogue will be touched on a
   different cadence, by different people, for different reasons (a new capability string
   is an I-6 ADR; a new capability *risk judgment* is a policy conversation) than a wire-
   shape change. Keeping them apart means a capability-catalogue change never has to be
   reviewed as if it were touching what every consumer's byte-compatibility depends on.
3. **A precise dependency signal.** The policy gate can depend on `pil-capabilities`
   without depending on everything `pil_contracts` or `pil_adapters` also carries, and a
   reviewer sees exactly what it needed just from its `pyproject.toml`.

**Why the adapter→capability mapping is not in `pil_capabilities` either.** Which
capability a given translator provides is adapters-domain data — it changes at the same
cadence as new translators landing in `pil_adapters.registry.TRANSLATOR_TYPES`, not at the
cadence of the closed vocabulary itself (I-6: extend by property, never by member, an ADR
to add one). It lives in `pil_adapters.capabilities`, importing `Capability` from
`pil_capabilities` the same way `pil_adapters` already imports shapes from `pil_contracts`.

### Scoping the mapping to what Phase A's translators actually do

`0017_seed_pil_confirmed_adapters.sql` already drew this line for `sl1`/`addigy`: *"Neither
translator PIL ships for these two sources does anything beyond alert translation...
`host.read`/`host.list` are NOT seeded here on that basis, unlike `fleet`/`sciencelogic`
above, which already carry those from `0008` on the strength of the full vendor tool's API
rather than what PIL's translate-only Phase A actually ported."*

`pil_adapters.capabilities` applies that same standard **uniformly**, across every
translator, including `fleet` and `connectwise` — which merp-console's existing seed data
does not. Every translator PIL ships does exactly one thing: turn one inbound vendor
payload into one Envelope. That is `alert.subscribe`, for all five real translators
(`sciencelogic`, `sl1`, `connectwise`, `fleet`, `addigy`) — not `host.read`, `host.list`,
`script.execute`, or `ticket.create`, which describe either the full vendor tool (Fleet's
real remote-execution API — AXO's own unported `fleet_healing_adapter.py`) or a different,
unported AXO code path (ConnectWise's real ticket-*creation* API — AXO's
`connectwise_adapter.py`).

`connectwise` is the sharpest case: `ConnectWiseTranslator` (ported from
`ticket_normaliser.py`) normalises an **inbound** ticket-shaped webhook into an Envelope —
the opposite direction from `ticket.create` (AXO calling *out* to ConnectWise to create
one). Claiming `ticket.create` here would describe AXO's separate, unported write path,
not what this translator does. `legacy` has no entry: it is not a vendor tool a tenant
configures.

This is narrower than what was reported in this ADR's own preceding proposal round, which
described PIL as sourcing `fleet`'s and `connectwise`'s fuller capability sets — that was
wrong, corrected here before anything shipped with the looser claim.

### `requires_signature` — default, not ruling

`0008_seeds.sql`'s own comment already treats `requires_signature` as an overridable
default, not a hard rule: *"Derived from risk by default (write => true) but stored, not
computed, so policy can override without a schema change."* `CapabilityDefinition` names
the field `requires_signature_default` for exactly that reason — self-documenting against
a future reader treating it as gospel. `risk` itself is not a default; PIL asserts it
outright, as a fact about whether exercising the capability mutates the external system.

## What this does not resolve

- **`product_requirements`** stays entirely console-authored. PIL has no concept of a
  product (`axo`/`quill`/`vigil`/…).
- **`gitlab`'s `repo.read`/`repo.write`**, and **`connectwise`'s inventory path**
  (`host.read`/`host.list`) — both sourced directly from AXO's own code
  (`gitlab_service.py`, `connectwise_adapter.py`), never ported into PIL. Stay
  console-authored, same as `slack`'s `notify.send` and `anthropic`'s `llm.infer` (neither
  `anthropic` nor `slack` is even in `pil_adapters.registry.TRANSLATOR_TYPES` — PIL has no
  translator for either, so neither can be PIL-sourced at all).
- **`scripts/pil-sync/`** — not touched by this ADR. Extending `extract.py`/`generate.mjs`
  to pull `pil_capabilities.CAPABILITIES` and `pil_adapters.capabilities.
  TRANSLATOR_CAPABILITIES` into a generated migration is follow-on work in
  `idiaz-io/merp-console`, not this repo.

## Alternatives

**Fold into `pil_contracts`.** Rejected — see "Package boundary" above. Two of the three
vocabularies offered as precedent for this aren't actually there, and contracts' own
stated charter (message shape) doesn't fit a permission vocabulary.

**Fold into `pil_adapters`.** Rejected. Would force a future policy-gate consumer to
depend on every translator/connection/sink class just to read a capability's risk, and
would tie the closed vocabulary's release cadence to the adapter mapping's faster one.

**Keep merp-console's fuller capability-grant claims for `fleet`/`connectwise`.** Rejected
— see "Scoping the mapping" above. Would assert PIL confirms behaviour (remote execution,
ticket creation) that Phase A's translate-only code does not have.

## Consequences

- New package `packages/capabilities` (`pil-capabilities`), zero dependencies, same
  posture as `pil-contracts` (ADR-0006) — enforced by
  `tests/test_capabilities_declares_no_dependencies` and
  `tests/test_capabilities_imports_nothing_from_this_repo_or_outside_the_stdlib`.
- `packages/adapters` gains a new dependency on `pil-capabilities` and a new module,
  `pil_adapters.capabilities`, holding `TRANSLATOR_CAPABILITIES` and `capabilities_for()`.
  `tests/test_invariants.py`'s `test_adapters_depends_only_on_contracts_and_capabilities`
  pins the new, still-short dependency list.
- `tests/test_invariants.py`'s I-1/I-3 scans (`test_nothing_in_pil_imports_a_web_framework
  _or_a_socket`, `test_no_pil_module_imports_a_product`) now also cover
  `packages/capabilities/src`.
- `docs/reference/pil-sourcing-proposal.md`'s "No capability-string catalogue... this
  isn't a gap to source around; there is nothing there" is now stale for the subset this
  ADR sources — a follow-up in `idiaz-io/merp-console` should update it alongside the
  `scripts/pil-sync/` change, not silently leave it contradicting this ADR.

### Sync safety: PIL-owned rows must be identifiable, and the sync must never
### full-table-replace `adapter_capabilities`

Written down now, before `scripts/pil-sync/` is extended, because getting this wrong is a
data-loss bug, not a stale-value bug.

PIL's honestly-scoped `TRANSLATOR_CAPABILITIES` (see "Scoping the mapping" above) claims
far less than merp-console's existing `adapter_capabilities` seed does for the *same
adapter keys* — `fleet`'s `host.read`/`script.execute`, `connectwise`'s inventory path
(`host.read`/`host.list`), and `gitlab`'s `repo.read`/`repo.write` are all true of the full
vendor tool or of AXO's own unported code, and **none of them true of PIL**.
`scripts/pil-sync/` currently regenerates `pil_translators` as a whole-table
`BEGIN/END GENERATED` block (`0018`'s `generate.mjs`), which is safe there because
`pil_translators` has no other writer. `adapter_capabilities` is not that kind of table —
it already carries rows PIL did not create and cannot regenerate. The same whole-table-
replace pattern applied here would silently delete every console/AXO-sourced row on the
next sync.

**Required of the sync, stated now as a precondition of building it:**

- `adapter_capabilities` needs a schema-level way to tell a PIL-authored row from a
  console-authored one. **Recommended: a `source` column** —
  `source text not null check (source in ('pil', 'console')) default 'console'` — added in
  a merp-console migration before `scripts/pil-sync/` is ever pointed at this table.
  - *Rejected: a key prefix* (namespacing `capability_key`/`adapter_key` themselves, e.g.
    `pil:fleet`). Would ripple into every FK that already references these exact keys as
    written — `product_requirements`, `grants`, `pending_requests` — for no benefit a
    column doesn't already give more simply.
  - *Rejected as sole mechanism: an allowlist with no schema backing.* Workable
    procedurally (see below) but leaves nothing in the schema itself to catch a future
    hand-authored row that happens to collide with a PIL-owned `(adapter_key,
    capability_key)` pair — the collision would be silently overwritten on the next sync
    with no constraint ever having fired.
- The generated block's `DELETE` must be scoped to `where source = 'pil'` before
  re-inserting the current set — structurally unable to reach a `source = 'console'` row,
  regardless of what the manifest contains that run. Same "make the wrong thing
  inexpressible" preference this repo already applies elsewhere (`UpsertEdge`'s single
  `tenant_id` field for both endpoints; merp-console's own `CLAUDE.md` §1.9 barring any
  direct query against `PRINCIPALS`). A scoped delete-then-insert within `source = 'pil'`
  is fine even though it isn't row-level-additive within that subset — it can never become
  a full-table replace because the predicate makes the other partition unreachable.
- **Until that column exists, `scripts/pil-sync/` must not touch `adapter_capabilities` at
  all.** Extend it only for the closed `capabilities` table itself first — a pure upsert by
  primary key `capability_key`, with no rows from any other source to protect, since that
  table currently has exactly one writer (`0008_seeds.sql`) and this ADR's package is
  positioned to become its second, agreeing one. Hold the adapter-mapping sync until the
  schema change lands. Shipping it against the current schema without the column would be
  the same category of mistake as reading `PRINCIPALS` directly instead of through its
  sanctioned view: a shortcut that looks fine right up until it silently isn't.
