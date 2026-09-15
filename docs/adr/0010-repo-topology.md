# ADR-0010 — PIL lives in its own repository, not `/packages/pil-contracts` in a monorepo

**Status:** Accepted · **Date:** 2026-09-14 · **Records a deviation from:** the MERP
Project Plan's monorepo recommendation (referred to in that plan's own numbering as
ADR-05, still **Open** there — see Context)

## Decision

PIL lives in `idiaz-io/PIL`, a standalone repository with its own git history, CI,
and release cadence — not as a package inside a monorepo alongside AXO, the console,
or any other product.

This ADR **records why that's correct**, given that PIL was already extracted this
way (IDI-195). It does **not** resolve the umbrella repo-topology question for MERP
as a whole — that question, tracked as ADR-05 in the MERP Project Plan's own
numbering, is still open, and nothing here closes it.

## Context

The MERP Project Plan recommends a monorepo, with PIL as `/packages/pil-contracts`
alongside every product. That recommendation's own ADR-05 has never been marked
Accepted — `merp-console`'s own `CLAUDE.md` lists it as Open. PIL was extracted from
AXO into a standalone repository anyway (IDI-195), which is the reality this ADR
explains rather than a choice being newly proposed here.

Three reasons the standalone-repo shape is right, independent of whether ADR-05 is
ever decided the monorepo's way:

1. **Consumers aren't co-located today.** AXO and `merp-console` are already
   separate repositories. A monorepo package only reduces friction if every
   consumer already lives inside it — that isn't true now, and won't become true by
   PIL choosing a location; it would require AXO and the console to move first,
   which is a much larger decision than this one.
2. **A separate repository makes I-3 a physical boundary, not a convention.**
   "PIL never depends on a product" is enforced today by a lint rule and an
   AST-walking test inside this repo. Those still matter in a monorepo, but a
   separate remote adds a boundary that doesn't depend on either mechanism working
   correctly — there's no shared working tree for a stray relative import to even
   reach across.
3. **`merp-console`'s own consumption pattern already presumes an independently
   versioned artifact.** `scripts/pil-sync/` pins PIL by commit SHA, clones it, and
   extracts via real imports against a real install — a pattern built for pulling
   from an external, independently tagged repository, not for reading a sibling
   directory in the same checkout.

## Alternatives

**Monorepo, per the Project Plan's own ADR-05.** Not rejected — deferred, because
it's a different, larger decision than this one, and it isn't this repo's to make
unilaterally. If ADR-05 is ever accepted in the monorepo's favor, migrating PIL's
history into it is its own deliberate ticket, not a side effect of this ADR.

**No formal position — leave it as an accident of how the extraction happened.**
Rejected. IDI-195's own reconciliation work already surfaced consequences of PIL
having no committed history and no ratified home; leaving the repo's location
undocumented invites the same kind of drift that produced that finding.

## Consequences

Two release cadences to track, not one: a change that spans PIL and a product
requires two PRs (and, per `merp-console`'s own docs, a deliberate pin bump — never
an automatic one) rather than one atomic commit.

If MERP's own ADR-05 is later decided in favor of a monorepo, this ADR is
superseded, not merely amended — folding a standalone repo's history into a
monorepo is a migration with its own risks (exactly the kind IDI-195 already
flagged for PIL's own git history), and deserves its own review rather than being
implied by a change to a different document in a different repository.
