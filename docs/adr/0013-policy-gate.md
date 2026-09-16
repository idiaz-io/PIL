# ADR-0013 — The policy gate: `pil_gate`, its vocabulary, and what it deliberately does not do

**Status:** Accepted — decided by Muhammad Shabbar, 2026-09-16 ·
**Relates to:** ADR-0011 (a closed vocabulary gets its own package; no live driver ships from
PIL), ADR-0012 (`pil-capabilities` — this gate is the "second consumer" that ADR names),
ADR-0009 (bus cut; the gate emits nothing to a bus), `docs/reference/PIL-PLAN.md`
(Thursday — policy gate), `MERP-Agent-Handover.md` §6.5 (policy gate I/O, in
`idiaz-io/merp-console`), `merp-console` `supabase/migrations/0005_products_and_entitlement.sql`
(`gate_decisions`) and `0019_connections_credential_gate_and_ledger_seal.sql`
(`sign_write_grant` — the only working gate logic anywhere in MERP today)

## Decision

PIL gains a fourth package, `packages/gate/` (`pil-gate`, import name `pil_gate`), that
answers exactly one question — *may this act run?* — with a decision shaped identically to
`merp-console`'s working `gate_decisions` row: `decision ∈ {allow, hold, deny}`,
`tier ∈ {observe-only, safe-auto-heal, approval-required, blocked-by-default}`,
`policy_version`, `required_approvers`, `approval_ttl`, `reason`, `decision_id`. It depends on
`pil-capabilities` and nothing else. It ships an abstract `PolicyGate`, one real
`ReferenceGate`, and one test double `StaticGate`, with tests — not a spec for someone to code
later (the plan's own words).

Six sub-decisions, each one paragraph:

1. **Own package, depending only on `pil-capabilities`.** Same reasoning ADR-0012 gave for
   the catalogue: authorization is neither wire shape (`pil_contracts`) nor vendor
   translation (`pil_adapters`) nor graph access (`pil_graph`). `pil_gate` needs a
   capability's `risk`; it does not need `Envelope`, a translator, or a Cypher builder, and a
   reviewer should be able to see that from its `pyproject.toml` alone. The graph *input* the
   handover describes (blast radius "computed by an ITKG query") arrives as a plain typed
   value the caller computed — the gate does not run the query, so it does not import
   `pil_graph`.

2. **Vocabulary: the console's three words, the handover's four tiers, both closed (I-6).**
   `Decision` is `allow | hold | deny` — the console's strings, because the plan says to take
   the console's shape and because those rows already exist in a live database. The
   handover's `allow_auto | require_named_human | deny` is the *same* three outcomes under
   other names; the mapping is recorded in the enum's docstring, not modelled as a fourth
   thing. `Tier` is the handover's four, byte-for-byte as the console's CHECK constraint spells
   them. Both counts pinned by test (`DECISION_COUNT = 3`, `TIER_COUNT = 4`), the way
   `NODE_LABEL_COUNT`/`EDGE_TYPE_COUNT` are.

3. **`observe-only` is the tier of an allowed read.** §6.5 maps three tiers to decisions and
   leaves `observe-only` ("detect and record; never act") unmapped. A capability with
   `Risk.READ` does not mutate the external system — exercising it *is* observation — so the
   reference gate returns `allow` / `observe-only` for it, mirroring the console's
   `granted_via = 'auto_read'` path (reads never enter `sign_write_grant`). This is the one
   judgement call in the mapping and is called out so it can be overruled in review rather than
   discovered later.

4. **`deny` structurally requires a `reason`.** The console enforces
   `gate_decisions_deny_requires_reason` as a CHECK ("an auditor asking why didn't you patch
   this gets an answer"). `GateDecision.__post_init__` enforces the same: a `deny` with a
   blank reason cannot be constructed. The reference gate populates `reason` on every
   decision, not only denies.

5. **The gate never writes the ledger; it returns something ledger-shaped.** §6.5 says every
   decision, including `deny`, is a ledger entry. `pil_ledger` does not exist until Friday.
   Rather than couple Thursday's package to Friday's, `GateDecision.to_record()` returns a
   plain, sorted-key mapping of primitives that `pil_ledger` (and, before it exists, any
   caller) can canonicalise and append. The gate has no `Sink`, no callback, no side effect —
   `decide()` is a pure function of its input plus one injectable `id_factory` for
   `decision_id`.

6. **Blast radius and breaker are typed, optional inputs — `None` means "not computed", never
   "safe".** `BlastRadius` and `Breaker` carry §6.5's fields exactly. In v1 the only `allow`
   for a write-risk capability is the human-signed one, so an absent blast radius can never
   widen an outcome; a present one can only narrow it (`tenants_crossed > 0` → `deny`;
   `breaker.tripped` → `hold`). Computing them is the caller's job — AXO's, via `pil_graph` —
   and stays so until a product actually needs the gate to do it (I-2).

## Context

The gate is scored **Absent** in `CLAUDE.md` §1 and `PIL-HANDOVER.md` — no code, no ADR.
Everything that does exist is in `merp-console`: the `gate_decisions` table (0005), the
`sign_write_grant` RPC (0019), and the handover's §6.5 contract. None of it is importable from
here (I-3 forbids it even if it were Python), so the shape is *ported* — the same posture
`pil_graph` took toward AXO's `packages/itkg`.

What `sign_write_grant` actually encodes, read from the SQL rather than from a description of
it: only `risk = 'write'` capabilities pass through the gate at all; the signer must be
`principal_type = 'user'` (`human_only` — "never automate the approval" made structural); the
signer must hold `org.grant.sign`; a signed write is recorded as `decision = 'allow'`,
`tier = 'approval-required'`, `policy_version = 'console-v1'`, `required_approvers = 1`; a
principal with `org.grant.request` but not `org.grant.sign` produces a `pending_requests` row
instead — which is what `hold` means. The reference gate reproduces those rules and nothing
the console does not already do.

The handover's §6.5 adds what the console's UI-driven gate did not need yet: an actor of
`kind` human or service, a target, a blast radius from the graph, a circuit breaker
(default threshold 3 per action class per asset), and the rule that the tier "comes from
policy, never from the caller." `GateRequest` carries all of it; `ReferenceGate` is the policy.

## The reference decision table

Evaluated top to bottom; first match wins. Every row is a test.

| # | Condition | `decision` | `tier` | Notes |
|---|---|---|---|---|
| 0 | `tenant_id` blank | — | — | `ValueError` at `GateRequest` construction (I-5, same as `pil_graph._require`) |
| 1 | `risk == READ` | `allow` | `observe-only` | Sub-decision 3. `required_approvers = 0`, `approval_ttl = None`. The console's CHECK is `> 0` only because reads never reach its gate (`auto_read`); PIL records them, so `0` is the honest value and `GateDecision` allows `>= 0` |
| 2 | `blast_radius.tenants_crossed > 0` | `deny` | `blocked-by-default` | Cross-tenant write is never a hold; reason names the count |
| 3 | `breaker.tripped` | `hold` | `approval-required` | §6.5: a tripped breaker routes to human review; reason names the class rate |
| 4 | `actor.kind == HUMAN` and `GRANT_SIGN in actor.permissions` | `allow` | `approval-required` | The `sign_write_grant` path. `required_approvers` from config (≥ 1) |
| 5 | otherwise (service actor, or human without `org.grant.sign`) | `hold` | `approval-required` | The `pending_requests` path. `approval_ttl` from config |

`safe-auto-heal` is **not produced by the reference gate in v1.** It requires a playbook
registry entry asserting reversibility and bounded blast radius (handover §7 E6.5) — nothing
in PIL or any product has one. Producing it from the gate alone would be the gate asserting
a fact it cannot know. The tier exists in the vocabulary so a product-specific gate can
return it; the reference gate does not.

## Alternatives

**Fold into `pil_capabilities`.** Rejected — that package is the vocabulary of *what* may be
done; the gate is *whether it may be done now, by this actor*. Different cadence, different
reviewers (a new capability is an I-6 ADR; a new gate rule is a policy conversation), and
`pil_capabilities` must stay dependency-free per its own test.

**Use the handover's decision names (`allow_auto`/`require_named_human`).** Rejected for v1 —
the plan says the console's shape, and rows with the console's strings already exist. If the
umbrella handover is later ratified with its names, renaming an enum's *values* is a
property-level change with an ADR, not a vocabulary change.

**Let the caller pass the tier.** Rejected outright — §6.5: "never from the caller."
`GateRequest` has no tier field, the same way `Translation` has no tenant field.

**Take `Actor.can_sign: bool` instead of `permissions`.** Considered. It would keep the
console's permission-key vocabulary (`org.grant.sign`) out of PIL entirely. Rejected for v1
because the plan's exit criterion is "given a capability's risk and an actor's held
permissions" — and because a boolean decided upstream is exactly the caller-supplied
authorization §6.5 forbids. `GRANT_SIGN` is one named constant, ported from `sign_write_grant`,
overridable per `ReferenceGate` instance.

**Have the gate emit to a `Sink` or write the ledger directly.** Rejected — sub-decision 5.
`pil_adapters.Sink` is an envelope handoff for translators, not a ledger; and `pil_ledger`
lands Friday. Coupling either way is premature.

## What this does not resolve

- **`safe-auto-heal` / Otto tier.** Needs a playbook registry (E6.5). Out of scope.
- **Two-person rule.** `required_approvers` is configurable and `> 0` is enforced; *tracking*
  how many have signed is the caller's state, not the gate's.
- **`max_classification` (CUI/ITAR).** `BlastRadius.data_classifications` carries the strings
  §6.5 names; the reference gate does not act on them yet (CLAUDE.md §4 point 5 — no PIL
  counterpart exists). A rule can be added as a property-level change.
- **Where decisions are persisted.** `pil_ledger` (Friday) for PIL; `gate_decisions` for the
  console. `to_record()` is the seam between them.
- **Whether AXO's `policy_evaluation_approval_gate` is replaced by this.** That is E4.x in the
  umbrella handover and a brownfield refactor in `idiaz-io/Axo`, not this repo.

## Consequences

- New package `packages/gate` (`pil-gate`), `dependencies = ["pil-capabilities>=0.1.0"]`,
  pinned by `tests/test_invariants.py::test_gate_depends_only_on_capabilities`.
- `tests/test_invariants.py`'s I-1 and I-3 scans gain `GATE_SRC`.
- Root `pyproject.toml`: `pil-gate` added to `[tool.uv.sources]`, `dev`, `testpaths`,
  `ruff.src`, `mypy.files`, `isort.known-first-party`. `uv.lock` regenerated.
- `CLAUDE.md` §1 row 3 and `PIL-HANDOVER.md`'s component table change from **Absent** to
  **Real (reference implementation; no `safe-auto-heal`, no ledger write)** — in the same
  commit as the code, so the docs never claim something the tree does not contain.
- `PIL-PLAN.md` Thursday row: state → shipped, once `make check` passes on `dev`.
