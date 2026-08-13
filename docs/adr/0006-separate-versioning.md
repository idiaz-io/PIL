# ADR-0006 — contracts and adapters are separately versioned and released

**Status:** Accepted · **Date:** 2026-08-11 · **Decides:** §8 decision 6

## Decision

Two distributions, versioned and released independently: `pil-contracts` and
`pil-adapters`. `pil-adapters` depends on `pil-contracts`; nothing depends the other way.

`pil-contracts` has **zero dependencies** — not on anything else in this repo, and not on
anything outside the standard library either.

## Context

QUILL will need contracts and will not need adapters. Keeping them separate makes that a
physical fact rather than a promise, which is the same reasoning `CLAUDE.md` gives for the
directory split.

Taking `pil-contracts` all the way to zero *external* dependencies goes beyond what
`CLAUDE.md` requires, for a reason specific to I-9: delegating serialisation to a
third-party library means its next release can change our bytes and invalidate every
signature written before it. The canonical serialiser is therefore stdlib-only and pinned
by a golden test.

This also settles §8 decision 2 in passing — Python only, no generated code for other
languages yet. The Go side has its own envelopes in `packages/schemas` and is not part of
Phase A.

## Consequences

Adding any dependency to `pil-contracts` requires an ADR. The `pyproject.toml` says so at
the point of temptation.

Two version numbers to move rather than one. A translator change ships as an adapters
release; an envelope change ships as a contracts release and a compatible-range bump in
adapters.
