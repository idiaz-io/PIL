# ADR-0001 — Package naming and import paths

**Status:** Accepted · **Date:** 2026-08-11 · **Decides:** §8 decision 3

## Decision

Flat, prefixed top-level packages: `pil_contracts` and `pil_adapters`, published as the
distributions `pil-contracts` and `pil-adapters`. Later components follow the same shape:
`pil_graph`, `pil_gate`, `pil_ledger`.

`pil_bus` was reserved here originally and is not, since IDI-195 D4 cut the bus.

## Context

§8 flags this as needing a human because "renaming later touches every product". The
obvious choice — `pil.contracts`, `pil.adapters` — is unsafe:

**`PIL` is Pillow's top-level import name.** Pillow is one of the most widely installed
Python packages and arrives transitively through matplotlib, reportlab, weasyprint and
others. macOS filesystems are case-insensitive by default, so `site-packages/PIL/` and
`site-packages/pil/` are the *same directory*. The failure mode is import shadowing that
appears only once some product happens to pull Pillow in, long after the naming is baked
into every consumer.

## Alternatives

**`merp.contracts` / `merp.adapters` as a namespace package.** Reads better and scales to
six components under one namespace. Rejected for two reasons. It depends on PEP 420
implicit namespace packages, where a single stray `merp/__init__.py` silently breaks the
split between separately-released distributions. And if products are ever named
`merp.axo` or `merp.quill`, the namespace stops distinguishing PIL from a product, which
weakens the I-3 lint rule from "no import outside our namespace" to a hand-maintained
list.

**`pil.contracts` / `pil.adapters`.** Rejected: the Pillow collision above.

## Consequences

The I-3 rule is unambiguous — nothing under `pil_*` may import a product name — and is
enforced in `pyproject.toml` under `tool.ruff.lint.flake8-tidy-imports.banned-api`.

Six flat top-level packages is less elegant than one namespace. That is the price, and it
is paid in exchange for a rule a linter can state in one line and a name that cannot
collide.
