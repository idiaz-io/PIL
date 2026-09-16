# PIL-PLAN.md — one week, two people, Claude Code implementing

**Written 2026-09-14.** Companion to `PIL-HANDOVER.md`, which stays state-only.
**Owner of this document: Hiba Hasan** — everyone else proposes edits.

Two rules carried forward, unchanged: report before building, verify against
the live system.

**Target: PIL is complete by Friday**, where "complete" means exactly what
the table below says it means — including the two things deliberately not
part of that claim (cut, and not PIL's to own).

---

## Component table

| Component | What it does, one line | Owner | Days | State |
|---|---|---|---|---|
| Shared shapes | The envelope, versioning, redaction, tenancy — the vocabulary everything else builds on. | *None* | *None* | **Frozen this week.** Already real. A change is its own stop-and-agree ADR (Coupling a), never folded into another day's work. |
| Credential-scoping memo | Compares AXO/PIL/console's three credential models, what each breaks, a recommendation — for a human to approve. | Hiba | Mon | **Ships this week**, unconditionally — writing and submitting it doesn't depend on anything. Its *approval* is what's conditional (see Adapter framework). |
| Capability catalogue | The ten capabilities, risk levels, product requirements, adapter mapping — as PIL contract data. | Hiba | Tue | **Ships this week** (PIL side only — `merp-console`'s own switch to consuming it is a separate, cross-repo PR, per ADR-0010). |
| Graph access path | Tenant-scoped query builder + interface over the closed ITKG vocabulary. No live Neo4j driver. | Hiba | Wed | **Ships this week.** |
| Adapter framework (finish) | Real `ConnectionProvider` + Fleet's connect/fetch/execute, ported from AXO. | Hiba | Thu–Fri | **Conditional.** Ships this week only if the credential-scoping memo is approved by end of Wednesday. Drops out of the week, explicitly, otherwise — see Thursday/Friday fallback. |
| Fixture corpus + test suite | Real (where reachable) or labeled-synthetic payloads per source, scrubbed, plus the known harness bug fixed. | Shabbar | Mon–Wed | **Ships this week.** |
| Policy gate | Answers: may this act run — allow / hold / deny. Interface **and** a real implementation **and** tests. | Shabbar | Thu | **Shipped.** Reference implementation; no `safe-auto-heal`, no ledger write. |
| Sealed ledger | Signed, hash-chained, offline-verifiable evidence. Interface **and** a real implementation **and** tests. | Shabbar | Fri | **Ships this week.** |
| Bus + orchestrator | How work would move between products and roll back. | *None* | *None* | **Cut** (ADR-0009) — zero consumers, AXO has its own queue. Reviving it needs a new ADR overturning that one, not a day on this week's schedule. |
| Gateway | One door for auth/authz/tenancy-scoping/rate-limiting/audit, per the architecture diagram. | *None* | *None* | **Blocked**, structurally — I-1 means it can't be PIL's regardless of who owns it. `[NEEDS-DECISION: gateway-ownership]` — not this week's to resolve. |

---

## How to use this

Open the repo, point a session at this file, say which day/component you're
on. For example:

> Read `PIL-HANDOVER.md`, then `PIL-PLAN.md`. I'm on Wednesday — the graph
> access path. Read `docs/reference/pil-inventory.md` first, then propose
> `pil_graph`'s shape (query builder, vocabulary enforcement, driver
> interface) per Wednesday's scope below. Don't write code yet.

---

## Monday — Hiba: precondition + credential-scoping memo

**Morning, quick:** the Phase-0 precondition carried forward from the
previous revision of this plan — `tailscale status`, `tailscale set
--accept-routes`, `curl` the SL1 API directly. This gates whether Shabbar's
Monday–Wednesday work (below) can use real `sciencelogic`/`sl1` payloads or
falls back to labeled-synthetic for those two sources as well. Confirm
before Shabbar needs the answer, not after.

**Rest of the day:** the credential-scoping decision memo. All three models
(AXO's global `platform_settings`, PIL's `(tool, tenant, product)`, the
console's tenant-only schema), what each breaks if adopted as the target, a
recommendation — written for whoever has standing to approve it, submitted
by end of day so there are two full days for review before Wednesday's gate.

## Monday — Shabbar: fixture corpus, day 1 of 3

Using Hiba's morning reachability finding: begin capture where reachable,
begin the `docs/known-issues.md` fix (`test_parity_harness.py` crashing
instead of skipping on a partial `../axo` checkout), begin the scrub
pipeline.

**Scrub rules:** `pil_contracts.redact()` runs directly on the raw captured
payload, before translation — never `Envelope.redacted()`, which is a
narrower, post-translation method whose own docstring warns that redacting
inside `translate()` breaks I-10 parity. Order is load-bearing: capture →
scrub → confirm scrubbed → commit `fixtures/<source>/` → `record-golden` →
commit `fixtures/_expected/<source>/`. Never the reverse — `record-golden`
run against raw data with the input scrubbed afterward guarantees a false
mismatch on every redacted field.

## Tuesday — Hiba: capability catalogue

New module `packages/contracts/src/pil_contracts/capabilities.py` — same
distribution as shared shapes, a different file; does not touch
`envelope.py`/`tenancy.py`/`redaction.py`/`versioning.py` (Coupling a).
Reviving what ADR-0009 cut gets its own short ADR, written the same day,
before the code.

**Exit:** ten capabilities, risk levels, product requirements,
adapter→capability mapping, shipped as data with a passing test suite
validating shape and closed vocabulary. `merp-console`'s own switch to
generating from this instead of hand-seeding is unblocked by today, not
included in it — a different repo's PR (ADR-0010).

## Tuesday — Shabbar: fixture corpus, day 2 of 3

Continue capture/scrub; review gate applied (a human reads scrubbed output
before commit — the scrubber marking something is evidence it worked, not
proof); synthetic fixtures built for whichever sources are unreachable,
explicitly labeled.

**What must never appear in a committed fixture, unredacted:** any
credential/token/API key/bearer value; any real hostname, device name, IP,
MAC, or hardware serial/UUID; any real organisation or company name; any
real username or email; anything `redact()` doesn't catch but a reviewer
does.

## Wednesday — Hiba: graph access path, then the memo checkpoint

New `packages/graph/` (`pil_graph`). **Scope: a tenant-scoped query builder
and a driver interface. No live Neo4j driver ships from PIL** — mirrors how
`ConnectionProvider` treats adapters, and avoids assuming an answer to
`[NEEDS-DECISION: ADR-17]` before hosting is settled. Own short ADR for this
scoping, written today.

**Closed-vocabulary enforcement:** `NodeType`/`EdgeType` as `StrEnum`s, ten
and thirteen members. A caller passing the wrong static type is caught by
mypy in CI; constructing an enum from an invalid value raises a runtime
`ValueError` — two different mechanisms for two different mistakes, neither
a compile-time rejection (Python has none). Property extension via an open
`properties` mapping, never a new enum member. Member count pinned by a test
against a named constant, so an addition fails CI until deliberately bumped
next to its ADR. No query constructable without a tenant scope,
structurally — no default, no "all tenants" escape hatch.

**Exit:** query builder, both enums, the driver interface, an in-memory
fake, and a test suite proving (a) no unscoped query is constructable and
(b) an unlisted node/edge type is rejected. No live Neo4j instance required.

**End of day — the decision checkpoint.** Has the credential-scoping memo
been approved?

- **Yes → Thursday and Friday are adapters** (below).
- **No → adapters drop out of this week, explicitly, in this plan and in
  the handover — not started on a guess.** Thursday and Friday become:
  hardening Monday–Wednesday's three shipped deliverables (additional test
  coverage on the catalogue and graph packages), and revising the memo if it
  came back with named objections rather than silence. `PIL-HANDOVER.md`
  gets one line added stating plainly that adapters did not ship this week
  and why.

## Wednesday — Shabbar: fixture corpus, day 3 of 3

Finish the known-issues.md fix. Get `make parity` passing in CI against the
corpus assembled Monday–Wednesday — real payloads for whatever Monday's
reachability check confirmed, labeled synthetic for the rest, per ADR-0007's
own caution that synthetic fixtures cover only the edge cases someone
thought of.

## Thursday — Hiba: adapter framework, day 1 of 2 (conditional — see Wednesday)

**If approved:** real `ConnectionProvider` implementation, resolving
credentials under whichever model Wednesday's approval landed on. Begin
porting Fleet from `fleet_healing_adapter.py` (764 lines, the one AXO source
that's fully real, not demo-gated) — `connect`, `check_connectivity`,
`fetch_device_details`.

**If not approved:** hardening day, per Wednesday's fallback.

## Thursday — Shabbar: policy gate

New `packages/gate/` (`pil_gate`). **Interface and a real implementation and
tests — not a spec for someone to code later.** Target shape from the
console's own working version: `allow`/`hold`/`deny`, `policy_version`,
`required_approvers`, `approval_ttl`. A real decision function, not just the
dataclass — given a capability's risk and an actor's held permissions,
returns a consistent decision — plus a test double alongside it for
consumers that don't need the real logic.

**Exit:** shipped — interface, `ReferenceGate`, `StaticGate`, passing tests.
No `safe-auto-heal` from the reference implementation, no ledger write.

## Friday — Hiba: adapter framework, day 2 of 2 (conditional)

**If approved:** finish the Fleet port — `execute_on_device`,
`verify_alert_cleared`, `verify_device_state` — with a passing test suite
proving it end-to-end against a fake Fleet-like test double, not a live
vendor call (PIL still has no deployable surface; I-1/I-10 hold).

**If not approved:** fallback continues. `PIL-PLAN.md` and
`PIL-HANDOVER.md` both get the honest note: adapters did not ship this
week, and why — a stated gap, not a silent slip.

## Friday — Shabbar: sealed ledger

New `packages/ledger/` (`pil_ledger`). **Interface and a real implementation
and tests.** Target shape from the console's own working HMAC chain:
`prev_entry_hash`, `entry_hash`, `signature`, append-only. A real
signer/verifier, not just the shape — sign an entry, chain it, verify
tampering breaks the chain — plus a test double for consumers that only
need to assert against *something* emitting ledger-shaped entries.

**Exit:** the interface, a working reference implementation, and a passing
test suite. One day.

---

## Ownership and directories — overlap check

| Component | Owner | Directory | Day |
|---|---|---|---|
| Credential-scoping memo | Hiba | `docs/decisions/` (new, not code) | Mon |
| Capability catalogue | Hiba | `packages/contracts/src/pil_contracts/capabilities.py` (new file) | Tue |
| Graph access path | Hiba | `packages/graph/` (new) | Wed |
| Adapter framework, finish | Hiba | `packages/adapters/` (existing) | Thu–Fri, conditional |
| Fixture corpus + test suite | Shabbar | `fixtures/`, `tests/`, `scripts/` | Mon–Wed |
| Policy gate | Shabbar | `packages/gate/` (new) | Thu |
| Sealed ledger | Shabbar | `packages/ledger/` (new) | Fri |

No directory has two owners on the same day. `packages/contracts/` has
exactly one person touching it this week (Hiba, one new file, Tuesday), and
the shared-shapes files inside it (`envelope.py`, `tenancy.py`,
`redaction.py`, `versioning.py`) have no owner at all — see Coupling (a).

## Unowned, with reasons

- **Bus + orchestrator.** Cut (ADR-0009). No directory, no day — reviving
  it overturns an ADR, it doesn't pick up unfinished work.
- **Gateway.** `[NEEDS-DECISION: gateway-ownership]`. No directory exists
  until where it lives is decided; I-1 forbids it being here regardless.

## Two couplings

**(a) Shared shapes have no owner.** `Envelope`/`AlertBody` aren't assigned
to any day above. A change is its own stop-and-agree ADR, never folded into
Tuesday's or Thursday–Friday's work even though Tuesday touches a different
file in the same package.

**(b) Fixture assertions are not blocked on anything.** The six translators
already exist and are tested, so the `Envelope` shape they produce already
exists today — Shabbar's assertions aren't waiting on anything from Hiba.
The only real coupling is (a): if `Envelope` changes later, that ADR is
what invalidates and re-triggers them.

---

## Testing — how a change gets proven correct here

1. **The invariant/unit suite** — runs today, no preconditions, `uv run
   pytest`.
2. **The fixture corpus + parity harness** (`make parity`) — proves
   byte-identical translator output against AXO's recorded behaviour, once
   Monday–Wednesday's corpus exists. Fails honestly on an empty corpus
   rather than passing vacuously.
3. **The bug in `docs/known-issues.md`** — fixed as part of
   Monday–Wednesday, not a footnote: a testing story that depends on an
   unfixed crash in the harness itself isn't one yet.
4. **No live deployment exists to test against.** "Correct" is bounded by
   the above three, honestly, not stretched further.

## Flagged, not resolved here

- `[NEEDS-DECISION: ADR-17]` — sovereign/air-gap vs. AWS. Referenced by
  Wednesday's graph-driver scoping.
- `[NEEDS-DECISION: ADR-05]` — repo topology. `docs/adr/0010-repo-topology.md`
  records why PIL is standalone; doesn't resolve the umbrella question.
- `[NEEDS-DECISION: gateway-ownership]` — unowned above for exactly this
  reason.
- `[NEEDS-DECISION: credential-scoping]` — Monday's memo is the deliverable
  that lets a human resolve it. Its approval, by Wednesday, is what this
  entire week's honesty about "complete" hinges on.

None of the four are Claude Code's to decide, in this session or a future
one — per `CLAUDE.md`'s own working style, they get flagged and waited on.
