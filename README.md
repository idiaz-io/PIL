# PIL — Platform Intelligence Layer

The shared floor under every MERP product. **PIL is a library, not a service.** Products
`import` it; nothing sends it a request. See [`CLAUDE.md`](CLAUDE.md) for why that is a
deliberate architectural decision and not an oversight.

Six components are planned. Two exist:

| Package | Distribution | Status |
|---|---|---|
| [`pil_contracts`](packages/contracts) | `pil-contracts` | Phase A — the message envelope |
| [`pil_adapters`](packages/adapters) | `pil-adapters` | Phase A — inbound translation only |
| `graph`, `gate`, `ledger` | — | not started |

They are separate distributions on purpose. QUILL needs contracts and does not need
adapters, and `pil-contracts` has **zero dependencies** — not on this repo, and not on
anything outside the standard library.

---

## Getting started

You need [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
make install     # create the venv, install both packages
make test        # run the suite
make check       # lint + typecheck + test — this is what CI runs
```

That is the whole setup. If any of it does not work from a fresh clone, that is a bug
worth reporting — "a new engineer can clone the repo and run the full test suite using
only the README" is Definition-of-Done item 8, and it is tested in CI.

---

## What Phase A is doing

Moving AXO's alert **translation** into PIL, proving the new implementation produces
identical output, then switching AXO over while leaving its own code in place so that
reverting is a configuration change and not an incident.

The scope, the investigation that preceded it and the decisions taken are in
[`docs/phase-a-scope.md`](docs/phase-a-scope.md) and [`docs/adr/`](docs/adr).

**Phase A is translate-only.** AXO's adapters also connect, execute and verify, but
those paths run in demo mode for every source except Fleet — so capturing "what AXO
currently produces" would enshrine hardcoded fakes as the specification. `normalize_alert`
is the only adapter method that does not branch on `demo_mode`, which makes it the only
surface where a parity proof means anything. See [ADR-0005](docs/adr/0005-translate-only-scope.md).

---

## Proving the migration

```sh
make parity AXO_PATH=../axo
```

Feeds every captured payload in [`fixtures/`](fixtures) through both AXO's normalisers
and PIL's translators and compares the canonical bytes. Byte-identical or it fails.

Two things about that comparison are deliberate and documented rather than accidental:

* **`tenant_id` is excluded.** AXO reads the tenant out of the vendor payload; PIL takes
  it from the adapter's own configuration (I-5). This is the single intentional
  difference, and PIL records what the payload claimed in `tenant_hint` so shadow mode
  can measure how often AXO was wrong. See [ADR-0004](docs/adr/0004-tenant-resolution.md).
* **Both sides run under a frozen clock and `TZ=UTC`.** AXO's normalisers fall back to
  `datetime.utcnow()` when a payload has no usable timestamp, and parse epochs in local
  time. Without pinning both, "byte-identical" is not a meaningful claim.

Anything else that differs is recorded in
[`docs/known-differences.md`](docs/known-differences.md) with a ticket, and the parity
test keeps asserting AXO's current behaviour. Fixing a defect while moving it makes two
changes pretend to be one (I-10).

---

## Fixtures

`fixtures/<source>/` holds real vendor payloads captured from AXO in production and
**scrubbed at capture time** — credentials redacted, identifiers replaced with a stable
keyed hash. No raw customer data is committed. The recorder lives in AXO at
`backend/services/pil_capture.py` and is off by default.

Payloads under `_malformed/` are ones AXO failed to process. They are the most valuable
fixtures in the corpus and the ones a happy-path capture never sees.

---

## The rules

[`docs/invariants.md`](docs/invariants.md) is the canonical list. The ones with teeth are
enforced mechanically rather than by intention:

| Invariant | Enforced by |
|---|---|
| I-3 · PIL never depends on a product | `ruff` banned-api + `tests/test_invariants.py` |
| I-5 · Tenant identity is never taken from input | `tests/test_invariants.py`, over every fixture |
| I-7 · Message shapes are versioned | `packages/contracts/tests/test_versioning.py` |
| I-9 · Deterministic serialisation | `packages/contracts/tests/test_canonical.py` |
| contracts has zero dependencies | `tests/test_invariants.py` |

Before writing code, read `CLAUDE.md`. Plan first, ask rather than assume, and write the
ADR before the code for anything on its list.
