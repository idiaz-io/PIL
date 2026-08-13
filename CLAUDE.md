# CLAUDE.md — PIL

Read this before doing anything in this repo.

---

## What PIL is

PIL is the shared floor under every MERP product. Six components, no more:

| Component | One line |
|---|---|
| **contracts** | The shapes every message takes. Definitions only, no runtime. |
| **adapters** | Connect to vendor tools; translate their output into contract shapes. |
| **graph** | The only path to the knowledge graph. Tenant-scoped queries. |
| **gate** | Answers: may this action run? Yes / ask a named human / no. |
| **ledger** | Signed, hash-chained evidence. Verifiable offline. |
| **bus** | How work moves between products, and how it rolls back. |

Products that consume PIL: AXO, QUILL, Vigil, Otto, Guardrails, Pavo, Remi.

---

## What PIL is NOT — read this twice

**PIL is a library, not a service.**

Products `import` PIL. Nothing sends PIL a request. There is no PIL server, no PIL
endpoint, no PIL gateway, no PIL container.

This is a deliberate architectural decision, not an oversight. It exists because
MERP has an invariant that no state-changing write may bypass the policy gate. A
library can enforce that mechanically — you cannot compile a product that skips it.
A network service can only enforce it by convention and code review, which means it
will be bypassed eventually and nobody will notice for months.

If a task seems to require an HTTP endpoint in PIL, **stop and ask.** The answer is
almost always that the endpoint belongs to a product, not to PIL.

PIL also does not contain:

- A remediation engine. AXO already has one that works.
- Anything that reads or interprets compliance control text. That is QUILL.
- Analytics, scoring, or risk models. Those are Vigil's and Remi's.
- Natural-language querying. That belongs to a surface, later.
- The graph database itself. That is a store. PIL holds the road to it.
- Device compliance checks. Those are AXO's; they detect, they never authorise.

---

## The invariants

These are not style preferences. Breaking one is a design defect, and several of them
exist because they were violated before and it cost real work.

**I-1 · PIL is a library.**
No HTTP surface. No long-running PIL process. Products import it.

**I-2 · One consumer means not shared.**
If exactly one product needs a capability, it belongs to that product, not to PIL.
This is the test that keeps PIL from growing into a second product.

**I-3 · PIL never depends on a product.**
The dependency arrow points one way, always. If PIL needs something from AXO, that
thing belonged in PIL. `import` statements referencing any product are a defect.

**I-4 · Products never call each other.**
AXO does not call QUILL. They cooperate by leaving records where the other will find
them. PIL must never provide a mechanism that makes product-to-product calls easy.

**I-5 · Tenant identity is never taken from input.**
For request-driven work, the tenant comes from a validated token claim.
For scheduled work (pollers), there is no token — so the tenant comes from the
**adapter instance's own configuration**, and an adapter instance may never emit a
message for any tenant other than its configured one. Never read the tenant out of a
vendor payload. This is currently violated in AXO production and is the highest-risk
class of bug in the system.

**I-6 · Vocabularies are closed.**
Node types, edge types, action classes and decision outcomes are fixed sets. Extend
by adding properties, never by adding a type. Adding a type is an ADR, not a commit.

**I-7 · Message shapes are versioned from the first line of code.**
Every message carries its schema version. A consumer built for v1 must not crash on
a v2 message. Decide the compatibility rule once and encode it in the library.

**I-8 · Secrets are handles, never values.**
Adapter configuration holds a reference to a secret. The value is resolved at the
moment of use and never logged, never stored, never placed in a message.

**I-9 · Deterministic serialisation.**
Anything that will later be hashed or signed must serialise byte-identically every
time. Ordering, whitespace and number formatting all matter. Get this right in
contracts now; retrofitting it invalidates every signature written before the fix.

**I-10 · Behaviour-preserving migration.**
When code moves from a product into PIL, the output must be identical. Not
"equivalent" — identical, proven against saved real payloads. A migration that
improves behaviour while moving it is two changes pretending to be one.

---

## Repo layout

```
pil/
  CLAUDE.md
  README.md
  docs/
    invariants.md            # the list above, canonical copy
    phase-a-scope.md         # what we are doing now
    adr/                     # one file per decision, numbered
  packages/
    contracts/               # shapes. no I/O, no dependencies.
    adapters/                # framework + one module per vendor tool
  fixtures/
    <source>/                # real captured vendor payloads + expected output
  scripts/
```

`contracts` is a separate package from `adapters` on purpose. QUILL needs contracts
and does not need adapters. Keeping them separate makes that a physical fact rather
than a promise.

`contracts` must have **zero dependencies on anything else in this repo**. If you
find yourself importing from `adapters` into `contracts`, the design is wrong.

---

## Working style in this repo

**Plan before writing.** Use plan mode. Present the plan, get it approved, then build.

**Ask rather than assume.** This repo is new and much about the AXO codebase is
unverified. When a decision has architectural consequences and the answer is not in
this file or in `docs/`, ask. A question costs a minute; a wrong assumption baked
into contracts costs a rewrite of everything downstream.

Specific triggers to stop and ask:

- Anything that would add an HTTP endpoint, a server, or a long-running process
- Anything that would add a new node type, edge type or action class
- Anything where the tenant's identity is unclear
- Anything that would make PIL import from a product
- Any place where AXO's current behaviour is ambiguous and you are tempted to pick

**Write the ADR before the code**, for anything on that list. Short is fine — the
decision, the alternatives, the reason. A paragraph each.

**Small commits, one idea each.** A commit that moves code and improves it is two
commits.

**Every claim in a PR description must be checkable.** "Parity verified" means a
command someone else can run and see pass.

---

## Definition of done, generally

A component in PIL is done when:

1. A product actually consumes it in production, and its own copy of that code is
   disconnected.
2. There is a command that proves the behaviour, and it runs in CI.
3. The invariants above are enforced by a test or a lint rule, not by intention.
4. Someone who has never seen the code can run the tests from the README alone.

---

## Current phase

See `docs/phase-a-scope.md`. In short: build the adapter framework in PIL, prove it
produces byte-identical output to AXO's existing adapters, then switch AXO's wiring
to consume PIL while leaving AXO's own adapter code in place and disconnected so
rollback is a config change.

Do not start on other components. Do not refactor AXO beyond the wiring switch.
