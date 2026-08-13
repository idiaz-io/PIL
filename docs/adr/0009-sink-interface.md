# ADR-0009 — A translated message goes to a sink behind an interface; the bus is cut

**Status:** Accepted · **Date:** 2026-08-13 · **Amends:** [ADR-0003](0003-message-envelope.md) · **Closes:** IDI-195 D4

## Decision

The bus and the capability catalogue are **cut**, not deferred. No `pil_bus`, no catalogue,
and no residue in the docs naming either as a planned component.

In their place, `pil_adapters.Sink`: an interface with one method, `emit(envelope)`. Two
implementations ship — `CollectingSink` (in-process handoff) and `NullSink` — plus
`RedactingSink`, which wraps another sink and strips credentials at the emit boundary.

`translate()` still returns an envelope to its caller and knows nothing about sinks.

## Context

### Why the bus is cut rather than postponed

Both had zero consumers. AXO already has its own queue, so a shared one would have been
built for a second product that does not exist yet, against requirements nobody has stated.
The capability catalogue is a real future problem that a naming convention solves at two
products — it was premature.

"Cut" and "deferred" read the same in a backlog and differently in a codebase. A deferred
component keeps its name reserved, keeps appearing in the component list, and accumulates
design decisions that assume it will arrive. `CLAUDE.md` listed the bus as one of PIL's six
components with a one-line description of behaviour — "how work moves between products, and
how it rolls back" — which is settled architecture, not a maybe. That is what D4 overturned,
so the docs had to change and not only the code.

The audit found no bus *code* had ever been scaffolded, so there was nothing to delete
there. What remained was four documentation references, now removed:
`CLAUDE.md` component table, `README.md` status row, the `pil_bus` name reserved in
ADR-0001, and the deferral in `phase-a-scope.md`. Each replaced by one line recording that
the bus was cut and why — the history is worth keeping precisely so nobody rebuilds it.

### Why there is a sink at all

D4 does not only cut; it also says what replaces the cut thing: "For Phase A, a translated
message goes to a simple sink behind an interface — a table or an in-process handoff. Not a
message broker."

ADR-0003 said the opposite — "There is no sink, no table, no bus" — while §8 decision 4 of
the scope document asked for exactly the handoff-behind-an-interface D4 restates. Two
documents in this repo contradicted each other, which is why this ADR amends rather than
merely adds.

The half of ADR-0003 that stands is that `translate()` *returns* rather than routes. That is
what keeps I-1 (PIL is a library) and I-4 (products never call each other) true by
construction, and a translator still has no idea a sink exists. The half that was too strong
is "no sink": without a named place to put the result, every product invents one, and they
diverge in exactly the way the redaction implementations already did.

### Why an interface rather than a function

The same reason D4 gave for cutting the bus: nobody knows what the second implementation is.
A `Sink` with two trivial implementations costs almost nothing, and it means the third — a
table, a tenant-scoped store, whatever the cutover needs — is a new class rather than a
refactor of every call site.

### What keeps it from becoming the bus again

The surface is one method plus an `emit_all` convenience, and a test asserts that is all
there is. An `ack`, `retry`, `enqueue` or `subscribe` appearing on `Sink` is the bus coming
back through the door D4 closed, and it should be caught in review rather than discovered
later.

Two deliberate non-features, both tested:

- **`emit` raises rather than swallowing.** A sink that absorbed its own errors would turn a
  delivery failure into silent data loss. Only the caller knows whether the payload can be
  re-derived.
- **`emit_all` is not a transaction.** If the third of five fails, the first two are emitted
  and the last two are not. Atomicity is a store's job; providing it here would be the first
  feature of a broker.

### Redaction belongs here

D1 puts redaction in shapes; this is where it gets *applied*. `RedactingSink` wraps another
sink, so "redacted" is visible at the call site that composes it rather than being a mode
someone forgets to set.

It is a wrapper rather than a default because of I-10. AXO stores the vendor payload
untouched, so redacting during the migration would break parity and would smuggle a
behaviour improvement into a move. Today nothing wraps anything and PIL's output stays
byte-identical to AXO's; after cutover, wrapping the real sink is one line and touches no
translator.

## Alternatives

**Keep the bus as a deferred component.** Rejected — see above. Deferring is what produced
a component table presenting an unbuilt broker as decided architecture.

**No sink; let each product decide.** Rejected. It is the status quo ADR-0003 described, and
it is how PIL ended up with redaction in two products and none in shapes. The cost of the
interface is far below the cost of two divergent handoffs.

**Make `Sink` async.** Rejected for Phase A. Both implementations are an in-memory append
and a no-op; making the interface async would make every caller a coroutine to satisfy an
interface that does no I/O. A sink that genuinely awaits gets an async sibling and its own
ADR.

**Redaction on by default in the sink.** Rejected until cutover, on I-10. It would fail
parity in a way that looks like a porting bug rather than the deliberate improvement it is.

## Consequences

`pil_adapters` gains a module that no translator imports, which is correct: a translator
produces a value and its caller decides where the value goes.

`CollectingSink` doubles as the test double for anything that emits. That is deliberate —
IDI-195's report-only section warns that if PIL does not ship test doubles, each product
writes its own and they drift, so tests pass while production fails. This is the first of
them; the fake gate, ledger and graph are still absent because those components do not
exist.

Nothing in AXO is wired to a sink by this ADR. The switch in `pil_shim.py` maps PIL's
envelope back onto AXO's `StandardAlert` and hands it to AXO's existing pipeline, which is
what a behaviour-preserving migration requires. Pointing AXO at a real sink is a
post-cutover change.
