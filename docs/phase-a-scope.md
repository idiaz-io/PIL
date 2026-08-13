# PIL — Phase A Scope

**Status:** scoping complete, planning not started
**Owner:** Shabbar
**Planning happens in:** a Claude Code session, plan mode, in the PIL repo
**This document is the brief for that session. It is not the plan.**

---

## 1. What Phase A is

Move the adapter framework out of AXO and into PIL, without AXO noticing.

That is the whole of Phase A. It is deliberately the smallest useful thing, chosen
because it is the least risky way to prove the repo, the conventions, the migration
pattern and the test approach all work — before anything harder is attempted.

**Why adapters first, and not something more valuable:** because adapters are the one
component where the code already exists and works. Everything we learn about how to
migrate safely, we learn here, where a mistake is cheap.

---

## 2. What Phase A is not

- Not a rewrite. The output must be identical, not better.
- Not the other five components. Contracts is included only as a thin slice.
- Not deleting anything from AXO. AXO's adapter code stays in the repo, disconnected.
- Not adding new vendor integrations.
- Not fixing AXO's known defects. Those are tracked separately and run in parallel.

---

## 3. Scope boundary

**In scope**

| Item | Note |
|---|---|
| Repo initialisation | layout, tooling, CI, CLAUDE.md, ADR folder |
| A slice of `contracts` | only what adapters need — see §4 |
| The adapter framework | connect + translate + retry + registry |
| Migration of existing adapters | whichever AXO actually has; count unknown |
| Parity harness | captured real payloads, byte-identical comparison |
| A three-state wiring switch in AXO | legacy / pil / shadow |
| Documentation | invariants, ADRs, README that a stranger can follow |

**Out of scope**

Graph access. The gate. The ledger. The bus beyond a trivial sink interface. The
capability catalogue. Any change to AXO's reasoning, execution or verification.
Any new HTTP surface anywhere.

---

## 4. The contracts slice

Adapters cannot be written without knowing what they translate into. But the whole of
contracts is not needed yet.

**Needed now**

- The message envelope: its fields, its types, its version field
- Which tenant this message belongs to
- Which source produced it, and which adapter version
- When it happened, and when it was observed
- The action-class vocabulary, if the framework also dispatches actions outbound
- Deterministic serialisation (invariant I-9)

**Not needed yet**

Node and edge vocabularies (those belong with graph access). Decision outcomes (those
belong with the gate). Anything about findings, attestations or change records.

**Estimated size:** two to three days, and worth taking the full time. This is the
cheapest component in PIL and the only one where a mistake reworks all five others.

---

## 5. The migration pattern

This pattern is the most important idea in Phase A. It should be reused for every
future component migration.

### Step 1 — Capture reality

Before writing anything, save real payloads from every source AXO currently talks to.
Ten to twenty per source, including the ugly ones: malformed fields, missing values,
unexpected nulls, unicode, very large payloads.

Run each through AXO's **current** code and save what comes out. That saved output is
now the specification. Not the docs, not anyone's memory — the actual behaviour.

### Step 2 — Build in PIL

Write the framework in PIL. Its target is to reproduce the saved output exactly.

### Step 3 — Prove parity

One command. Feeds every captured payload through both implementations and diffs the
result. Byte-identical or it fails. This runs in CI.

Where AXO's existing behaviour turns out to be **wrong**, do not fix it here. Record
it as a known difference with a ticket, keep the parity test asserting the current
(wrong) behaviour, and fix it as a separate change afterwards. Mixing a fix into a
migration makes both unreviewable.

### Step 4 — Switch the wiring, don't remove the code

Add a switch in AXO with three positions:

| Position | Behaviour |
|---|---|
| `legacy` | AXO's own adapters, as today. The default. |
| `shadow` | Both run. PIL's result is compared and logged. **Legacy's result is used.** |
| `pil` | PIL's adapters are used. Legacy code still present, just not called. |

Runtime configuration, not a build flag. Flipping back must not require a deploy.

**Shadow mode is the point of this design.** It produces parity evidence from real
production traffic, at zero risk, for as long as you want before committing. A test
suite proves the cases you thought of; shadow mode proves the ones you didn't.

### Step 5 — Cut over

Run shadow until the difference count has been zero for an agreed period. Then flip
to `pil`. AXO's adapter code stays in the repository, uncalled, until a later ticket
removes it deliberately.

---

## 6. Definition of done for Phase A

All of these, demonstrable:

1. AXO runs in production on PIL's adapters, switch set to `pil`.
2. AXO's own adapter code is still present and disconnected. Flipping to `legacy`
   restores previous behaviour without a deploy.
3. The parity command passes in CI, covering every source AXO supports.
4. Shadow mode reported zero differences over the agreed observation window.
5. `contracts` has zero dependencies on anything else in the repo, enforced by a test.
6. A lint rule fails the build if PIL imports from any product.
7. A lint rule or test fails the build if an adapter emits a message whose tenant
   differs from its configured tenant.
8. A new engineer can clone the repo and run the full test suite using only the README.
9. Every decision listed in §8 has an ADR, even the ones answered in one line.

Item 2 is the one that makes this safe. Item 7 is the one that prevents repeating
AXO's live customer-separation defect in new code.

---

## 7. What the Claude Code session must find out first

The chat session that produced this document could not read the AXO codebase. These
questions must be answered by reading it, **before** planning, and the answers will
change the plan's shape. Report findings before proposing a plan.

### About the shape of what exists

1. **Is there one adapter system or two?** There appear to be at least two distinct
   paths: a scheduled inventory sync pulling from several MSP tools, and an event
   ingestion path receiving alerts. Periodic full-state reconciliation and discrete
   event streams are different shapes. If AXO built them separately, PIL must support
   both, and that is a design decision rather than a lift.

2. **Which sources are actually implemented, versus stubbed or aspirational?** Count
   the real ones. The documentation names more than the code may contain.

3. **Is there already a common internal shape**, or does each source normalise ad hoc?
   If a common shape exists, contracts should start from it rather than from a blank page.

4. **Is there an outbound path?** Does the same framework also dispatch actions to
   machines, or is execution a separate subsystem? This changes the scope materially.

### About coupling

5. **What does the adapter code import from the rest of AXO?** Internal types,
   database models, config objects, logging helpers. This list is the actual work of
   the migration; the translation logic is usually the easy part.

6. **Where does the tenant come from today, in each path?** Be specific per source.
   Expect to find that it sometimes comes from the payload, which is invariant I-5
   being violated.

7. **How are credentials obtained today?** Environment, a vault, a config file, a
   database row? Whatever it is, PIL takes a handle, not a value.

### About what already exists that we should not rebuild

8. **Are there existing tests or captured fixtures?** If real payloads are already
   saved anywhere, that is the parity corpus and it saves days.

9. **Is retry, backoff, rate limiting or dead-lettering already implemented?** If so,
   it moves; if not, note it as new work rather than migration.

10. **What are the tooling facts?** Language version, package manager, test runner,
    lint setup, CI. PIL should match AXO's where there is no reason to differ.

### Report format

A short document: one line per question, with a file path or a "not present". Then a
list of anything found that contradicts this scope document. Then the plan.

---

## 8. Decisions that need a human

These are not for Claude Code to choose. Flag them and wait.

| # | Decision | Blocks | Recommendation |
|---|---|---|---|
| 1 | Version compatibility rule — how a v1 consumer handles a v2 message | contracts, therefore everything | Additive-only within a major version; unknown fields ignored, never rejected |
| 2 | Which languages need generated contract code | contracts | Python only for now. Add TypeScript when Guardrails becomes real work, not before. |
| 3 | Package naming and import paths | repo init | Decide once; renaming later touches every product |
| 4 | Where a translated message goes in Phase A | adapters | A simple table or in-process handoff behind an interface. Not the bus — that is a later component. |
| 5 | Shadow-mode observation window before cutover | step 5 | Long enough to cover a full business cycle for every source |
| 6 | Whether contracts and adapters are separately versioned and released | repo init | Yes. QUILL will need contracts without adapters. |

---

## 9. Risks, and what we do about them

| Risk | Why it is likely | Mitigation |
|---|---|---|
| The lift turns out to be a rewrite because of coupling | Adapters were written against AXO's internals | Question 5 answers this before any commitment. If coupling is deep, the plan changes shape and that is fine — better to know in week one. |
| Two adapter shapes, not one | The inventory and alert paths look different | Question 1. If confirmed, treat them as two migrations and sequence them. |
| The parity corpus is too thin to be meaningful | Easy to capture only the happy path | Deliberately capture malformed and edge-case payloads. Shadow mode is the backstop. |
| Contracts gets designed around adapters alone | Adapters are the only consumer right now | Design the envelope for findings and attestations too, even though nothing emits them yet. Have Sam review the envelope and version rule specifically. |
| Scope creep into "while we're here" fixes | Very likely, and it feels productive | Invariant I-10. Known-wrong behaviour is recorded and preserved, then fixed separately. |
| Someone builds PIL as a service | It is the most natural wrong turn available | Stated three times in CLAUDE.md and enforced by a lint rule. |

---

## 10. Sequence

```
Repo init  ──▶  contracts slice  ──▶  framework  ──▶  parity harness
                                                            │
                            AXO wiring switch  ◀────────────┘
                                    │
                            shadow mode  ──▶  cut over to pil
```

Investigation (§7) precedes all of it and gates the plan.

---

## Appendix — the one-paragraph version

We are creating a new repository for PIL, the shared floor beneath all MERP products.
PIL is a library that products import, never a service they call. The first component
is the adapter framework, which already exists inside AXO and is being moved rather
than rewritten. We will capture real vendor payloads, record exactly what AXO
currently produces from them, rebuild the framework in PIL to produce byte-identical
output, then switch AXO to use PIL's version while leaving its own code in place and
disconnected, so that reverting is a configuration change and not an incident. Before
any of this is planned in detail, a Claude Code session must read AXO's adapter code
and answer ten specific questions, because this scope was written without access to it.
