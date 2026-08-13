# fixtures/

The parity corpus. **Currently empty, and that is the one remaining blocker on IDI-195.**

```
fixtures/
  <source>/            real captured vendor payloads, scrubbed
  _expected/<source>/  AXO's output for each — the specification
```

`_expected/` is underscore-prefixed so `collect_fixtures` skips it when gathering payloads.

## Why it is empty

The corpus is captured from AXO **in production**. It cannot be written by hand — that is
the whole point of D6, and ADR-0007 explains it at length: hand-written stubs encode what we
believe the payloads look like, and the reason to capture real ones is precisely that our
beliefs are wrong in ways we cannot predict.

Capture requires three things that are outside this repo:

1. `PIL_CAPTURE_ENABLED` set in AXO's `platform_settings`
2. `PIL_CAPTURE_SALT` set in AXO's environment — capture fails closed without it rather
   than writing unscrubbed customer data
3. Real traffic through AXO's ingest paths, over enough time to see malformed fields,
   missing values, nulls, unicode and oversized bodies

Everything else is built and tested. What is missing is a production run.

## What "done" looks like

D6 asks for 10–20 payloads per source, including the awkward ones. `make parity` enforces
the lower bound per source via `--min-per-source` (default 10) and fails rather than
skipping, so this file cannot quietly become the thing nobody did.

Sources needing a corpus: `sciencelogic`, `sl1`, `connectwise`, `fleet`, `addigy`,
`legacy`. `sl1_poller` is captured but deliberately excluded from parity — see
`OUT_OF_SCOPE_SOURCES` in `scripts/parity.py`.

## Filling it

On the AXO side, once capture has run:

```bash
# 1. Copy the scrubbed corpus out of AXO. PIL never vendors a product (I-3), so this is
#    a copy of data, not a checkout.
cp -R "$PIL_CAPTURE_DIR"/* fixtures/

# 2. Record AXO's current output as the specification. Review this diff carefully — on a
#    first run everything is new; afterwards, any change to an existing file means AXO's
#    behaviour moved, which is a finding and a ticket, not a routine update.
make record-golden AXO_PATH=../axo
git add fixtures/
git diff --cached --stat

# 3. Prove parity. Byte-identical except tenant_id (ADR-0004), or it fails.
make parity AXO_PATH=../axo
```

Before committing anything here, confirm the payloads are scrubbed. `pil_capture` scrubs
before writing and `.gitignore` blocks `*.raw.json` and `/raw-capture/` as a backstop, but
the backstop is not the control — the control is looking.

## Committing the payloads is deliberate

They are real customer traffic, scrubbed: credentials stripped, identifiers pseudonymised
with a keyed hash. Structure is preserved exactly — same keys, same nesting, same
null/empty/missing distinctions — because the translators branch on which keys are present
and on whether a value is empty. A scrubber that dropped an empty string would change what
the corpus tests without changing any test.

The scrubbing implementation is `pil_contracts.redaction`, and it is the only one:
`pil_capture` delegates to it (IDI-195 D1).
