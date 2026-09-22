# fixtures/_synthetic/

Hand-authored fixtures proving PIL's six translators do what their source says, for now
— every vendor source is unreachable (the homelab is offline), so real capture per
`docs/adr/0007-fixture-capture-and-scrubbing.md` cannot happen yet.

## This is not the parity corpus

`fixtures/<source>/` and `fixtures/_expected/<source>/` (real, captured, scrubbed
production traffic, compared against AXO byte-for-byte) are untouched by anything here.
ADR-0007 explicitly rejected hand-authored payloads as parity evidence: *"it can only
contain the edge cases someone thought of, which is the failure mode capture exists to
avoid."* That rejection stands. What lives here answers a narrower, different question —
does PIL's own translator produce the output its source and cited AXO line numbers say it
should — never IDI-195 DoD 7.

**A file never moves between here and the real corpus, in either direction.** A synthetic
fixture "graduating" to real would smuggle a hand-derived expectation in as AXO's actual
captured behaviour. The reverse would quietly shrink real coverage.

The leading underscore is load-bearing, not decorative: `scripts/parity.py`'s
`collect_fixtures` already skips any top-level child of `fixtures/` starting with `_` (the
same mechanism that already excludes `_expected/`). `_synthetic/` is therefore structurally
invisible to the real corpus walk, `--min-per-source`, and DoD 7 coverage reporting — it
cannot be silently counted as real coverage.

## Layout

```
fixtures/_synthetic/
  <source>/
    01-happy-path.json
    02-<slug-naming-the-branch-it-exercises>.json
  _expected/
    <source>/
      01-happy-path.json
      02-<slug>.json
```

Mirrors the real corpus's own `fixtures/<source>/` + `fixtures/_expected/<source>/`
pairing, one level deeper, so the mental model transfers when real capture eventually
lands. Checked by `tests/test_synthetic_fixtures.py`, which runs in every ordinary
`uv run pytest` — no AXO, no secret, no external dependency.

## How an expected file gets written — the rule that matters most

**Derived by hand from the translator's source and its cited AXO line number, before ever
running PIL. Never recorded from PIL's own output.**

Recording PIL's output as PIL's own specification is circular: it would prove the
translator is stable, not that it is correct, and would degrade this corpus into exactly
the kind of decorative padding it exists to avoid. When a hand-derived expectation
disagrees with what PIL actually produces, that disagreement is reported as a finding —
either the derivation misread the source, or there is a real translator bug — and the
fixture is not quietly edited to make it pass.

## Secondary use: replay against a real AXO checkout (not yet wired up)

The plan is for `scripts/parity.py --demo` to read these same fixtures and replay them
against AXO live, for whoever has a local checkout — still printing "Harness OK... NOT a
parity result", same as today's hardcoded `DEMO_PAYLOADS`, and not wired into CI (same
posture as `make neo4j-test`: a local dev tool, not a CI gate). That would validate the
hand-derived expectations above against AXO's actual current behaviour, closing the loop
without needing production traffic or `AXO_READ_TOKEN`. Not implemented yet — this corpus
is being built source by source first; `--demo`'s extension is a separate, later change.
