# ADR-0011 — Graph access: PIL vs. AXO's `packages/itkg`, and the language question blocking it

**Status:** Accepted — decided by Hiba, 2026-09-15 · **Relates to:** ADR-0001 (package
naming), ADR-0006 (contracts is Python, zero dependencies), ADR-0009 (bus cut),
ADR-0010 (repo topology), MERP-Agent-Handover.md §6.1/6.2 and ADR-08 (unratified),
`docs/reference/PIL-PLAN.md` (Wednesday — graph access path)

## Decision

**PIL stays Python.** `MERP-Repository-Structure.pdf`'s "pil (Go)" is not adopted.
PIL is built, tested, and working in Python today — nine ADRs, 264 passed (1 skipped)
at commit `5530434` with AXO built at `~/axo/msp-platform`,
`uv`/`ruff`/`mypy` tooling throughout, `pil-contracts` deliberately stdlib-only
(ADR-0006) so a third-party release can never change a signed byte. Rewriting that
in Go would serve an unratified proposal document, not any consumer that actually
exists. No product imports PIL as Go today; nothing is lost by not becoming Go.

### Consequence for itkg-ownership

**PIL owns the ITKG interface and the closed vocabulary, in Python.** AXO's Go
`packages/itkg` is a **deliberate product-side exception that predates this
rule** — real, merged, and it is not being undone by this ADR — but it is **not
canonical, and it is not the pattern other products should follow.** A future
product needing graph access takes PIL's Python interface, not AXO's Go package.
Reconciling AXO's existing implementation against that (port it behind PIL's
interface, wrap it, or leave it as a documented, contained exception
indefinitely) is **out of scope for this ADR** — file it as its own issue,
separate from the language decision made here.

### Consequence for the vocabulary

**The closed vocabulary (10 node labels, 13 edge types) now exists in two
languages, independently.** That is accepted, not ignored: the rule going
forward is **a change to either — AXO's `packages/itkg/vocab.go` or PIL's
Python equivalent — requires the identical change to both, in the same
change set, reviewed together.** Each side carries its own test pinning the
count (`10` node labels, `13` edge types) so a silent, one-sided addition
fails CI on whichever side didn't get the memo, rather than silently
diverging until someone notices in production. This mirrors AXO's own
`TestVocabularyIsClosed` — PIL's Python side gets the equivalent, not a
weaker version of it.

### What this ADR does not resolve

**The gateway and bus contradictions in `MERP-Repository-Structure.pdf` are
unchanged — still open findings, not touched by this decision.** This ADR
answers the language question and its two direct consequences (itkg-ownership,
the vocabulary) only. `pil/gateway/` (contradicts I-1) and `pil/bus/`
(contradicts ADR-0009) remain exactly as documented previously: real
disagreements between that proposal and this repo's own invariants, neither
decided here.

## Context

Unchanged from the prior revision of this ADR — repeated here for the record,
not re-litigated:

Three sources described PIL's graph-access component and disagreed on shape,
ownership, and language. This repo, as built: Python throughout. AXO's
`packages/itkg` (merged into `merp-integration` 2026-08-15, PR #47, commit
`b04cae7`, verified directly against GitHub — not into `main`, which has
diverged 87 ahead / 21 behind): Go, a live Neo4j driver, held inside a
product's own repository, with its own PR description stating the intent to be
a cross-product shared library. `MERP-Repository-Structure.pdf` (14 Aug 2026,
explicitly unratified): states PIL is Go, and states — as a rule the build
should enforce — that all graph access goes through `pil/itkg`, which is why
AXO's package reads as a deviation from that proposal rather than a precedent
for one.

The proposal's order-of-work (§6: *"Merge PR #46 and #47... unlanded until
then"*) was also verified stale: #47 was already merged the day after the
proposal's own date; #46 is an unrelated PR on a different base branch,
touching neither contracts nor ITKG.

## Alternatives

**Rewrite PIL in Go, adopting the proposal wholesale.** Rejected. Discards a
working, tested Python codebase to match a document that itself says
*"nothing here should be created until the topology decision is signed
off"* — the proposal is explicit that it isn't a mandate yet. No current
consumer needs PIL in Go; AXO's own Go graph code doesn't import PIL either
way.

**Adopt AXO's `packages/itkg` as PIL's canonical implementation, unmodified,
in place.** Rejected as the general rule, though not undone where it already
exists — see itkg-ownership above. Doing this as policy would mean PIL's
"library other products import" is actually "whatever one product happened
to build first," which is a worse precedent than the one-time exception this
ADR is choosing to tolerate.

**Say nothing about the vocabulary now existing twice, and hope it doesn't
drift.** Rejected — this is exactly the failure mode redaction already
demonstrated once (two implementations, one product, before PIL centralized
it). Naming the rule and requiring a test on both sides is cheap; discovering
a silent drift in production is not.

## Consequences

`packages/graph/` is **unblocked.** The language question that stopped it is
resolved: Python, in this repo, following `PIL-PLAN.md`'s original Wednesday
scoping (query builder + interface, no live driver — that scoping was never
the blocker; the language underneath it was, and it's answered now).

Building it means **porting the design from AXO's `vocab.go` and `itkg.go` —
same vocabulary (byte-identical label/relationship-type strings, not just
equivalent names), same tenancy-by-construction pattern (tenant set
server-side, after caller-supplied properties, never trusted from input),
same openCypher-portability constraint (no APOC/GDS/Enterprise-only
constructs) — rewritten in Python, not reinvented from the vocabulary
counts alone.** A module-structure proposal for this, following that
instruction, is separate from this ADR and comes before any code is written.

`[NEEDS-DECISION: pil-language]` is closed. `[NEEDS-DECISION: itkg-ownership]`
is narrowed but not closed — PIL owns the interface going forward; what
happens to AXO's existing Go implementation is still open, filed separately.
`[NEEDS-DECISION: gateway-ownership]` and the bus contradiction remain
exactly as they were.
