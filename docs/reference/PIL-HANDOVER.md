# PIL — handover (state)

**Written 2026-09-14, split the same day** into this file (state only) and
`PIL-PLAN.md` (phases, ownership, exit criteria) — the week-plan content that used
to live here has moved there. Drop both in `docs/` and point a fresh session at
this file first, then `PIL-PLAN.md` for what to actually do.

---

## What is built and real

**merp-console** (`idiaz-io/merp-console`) — the admin surface. Deployed nowhere yet;
runs on localhost.

Real, verified against a live Supabase Postgres:

- Auth, tenancy, principals, memberships — RLS forced on every tenant-scoped table
- People & access — invitations with token hashes, accept flow, role bundles from data
- Connections — adapters, config, ingest settings, grants, the gate, credential refs
- The sealed ledger — real HMAC chain (`prev_entry_hash`, `entry_hash`, `signature`),
  append-only, enforced by trigger
- Transactional email via Resend from `noreply@idiaz.io`

Still fixture-backed: Products & plan, Audit record, My products, onboarding.

## What PIL actually is today

Read from `idiaz-io/PIL` at commit `5530434`. Full detail in
`docs/reference/pil-inventory.md`.

- **Library-only by design.** Invariant I-1, enforced by a banned-imports test for
  fastapi/flask/uvicorn. No deploy config anywhere.
- **Shared shapes exist** — Envelope, AlertBody, versioning, canonical serialisation,
  redaction, tenancy resolution. Zero dependencies, Python stdlib only.
- **`ConnectionProvider` interface exists**, keyed `(tool, tenant, product)`. Nothing
  implements real secret resolution.
- **Adapters translate only — verified 2026-09-14.** No HTTP client dependency
  anywhere in `packages/` (`pil-adapters`'s one declared dependency is
  `pil-contracts`); no `connect`/`execute_on_device`/`check_connectivity`/
  `fetch_device_details`/`verify_*` method exists anywhere in this repo; secret
  resolution is absent by a **tested guarantee**, not merely unbuilt
  (`packages/adapters/tests/test_connection.py:283` asserts no
  `resolve_secret`-shaped function exists). **The working implementation lives in
  AXO, unported** — `fleet_healing_adapter.py` (764 lines) is real, demo-free
  connect/fetch/execute code and is the intended port source (see `PIL-PLAN.md`,
  Thursday–Friday — conditional on the credential-scoping memo being approved
  by Wednesday). Six translators — the *inbound* half — are real and tested;
  the outbound half hasn't started.

**Correction, 2026-09-14 — the CI parity complaint is stale.** `pil-inventory.md`
documents a real false pass found during the IDI-195 audit: the `parity` CI job
skipped (and went green) when `AXO_READ_TOKEN` was missing, so Definition of Done
item 7 could read as satisfied with zero payloads ever compared. **That's fixed.**
Read `.github/workflows/ci.yml` directly rather than repeating this: a missing
`AXO_READ_TOKEN` or `AXO_PARITY_SHA` now fails the job outright, with an explicit
`::error` explaining why, per `docs/reconciliation.md`'s own outcome table (D6).
What's still genuinely open is the corpus (`fixtures/` is empty), not the
check-that-can't-fail problem.

Also worth knowing before trusting any pass/fail count from a doc: the test
suite's real result is environment-sensitive. Running it here found a live bug —
`docs/known-issues.md` — where a partial sibling `../axo` checkout makes ten
`test_parity_harness.py` tests crash instead of skipping. Rerun the suite
yourself; don't cite a number from this file or from `pil-inventory.md` without
doing so. (Filed, not fixed — it's part of Shabbar's Monday–Wednesday
fixture-corpus work in `PIL-PLAN.md`.)

## The architecture's six PIL components, scored

| Component | State |
|---|---|
| Shared shapes | Exists |
| Adapter framework | Partial — translate only, no connect/fetch |
| Policy gate | **Real (reference implementation; no `safe-auto-heal`, no ledger write)** |
| Sealed ledger | Absent from PIL (a working version exists in the console's Postgres) |
| Graph access path | Absent — no ITKG code at all |
| Bus + orchestrator | **Cut, not merely absent** (IDI-195 D4) — zero consumers, AXO already has its own queue, a naming convention does what a catalogue would at two products. Replaced by `pil_adapters.Sink`. Reviving it means overturning ADR-0009, not just getting to it. |
| *API Gateway* (in the diagram, outside PIL) | Absent everywhere |

**Correction, 2026-09-14:** this table has always said six, correctly. What was
wrong was this repo's own `CLAUDE.md`, which said *"Five components, no more"* and
simply didn't list the bus — silently undercounting rather than recording that it
was cut. Fixed: `CLAUDE.md` now lists all six and marks the bus cut, with the
reason, matching this table. Read the row above, not the old five-component
framing, if the two ever seem to disagree again.

## Three conflicts nobody has resolved

1. **Credential scoping, three incompatible models.** AXO resolves credentials from a
   global `platform_settings` table with no `tenant_id` — one Fleet token for the whole
   deployment. PIL's interface is keyed `(tool, tenant, product)` specifically to prevent
   that. The console is keyed tenant-only. All three disagree. **Needs a human.**
   `PIL-PLAN.md` now schedules the decision memo for Monday — the
   conflict itself isn't resolved by that memo existing, only by someone signing off on it,
   and adapters (Thu–Fri) don't start without that approval landing by Wednesday.

2. **How many products.** The architecture diagram shows seven. The console ships five —
   Guardrails and Pavo were removed. `DECISIONS.md` #1.

3. **Who builds the gateway, and where does it live.** The diagram requires one; PIL's
   own invariant says it can't be in PIL; ADR-05 (repo topology, in `merp-console`'s own
   numbering) is still open. `docs/adr/0010-repo-topology.md` in *this* repo records why
   PIL itself lives outside a monorepo — it does not resolve the gateway question, which
   is a different decision.

## The capability catalogue — a gift, not a gap

The architecture flags this as unspecified and says it belongs in PIL. The console
already authored it: ten capabilities with read/write risk levels, plus product
requirements and an adapter→capability mapping, all live in Postgres. It is
console-authored with no upstream source (ADR-0009 cut it from PIL).

`PIL-PLAN.md` schedules moving it for Tuesday.

---

## The two rules that hold regardless of phase

- **Report before building.** Every good outcome in this project came from an inventory
  or a proposal read before code was written.
- **Verify against the live system, not the code.** Claims about what works should come
  from actually running the suite, actually importing the module, actually checking the
  file — never from reading a function and assuming it behaves as documented. The test
  suite's own pass/fail count has already proven environment-sensitive once (see above)
  — don't repeat a cached number from a previous session without rerunning it.
