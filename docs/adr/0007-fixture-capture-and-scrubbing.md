# ADR-0007 — Sourcing the parity corpus

**Status:** Accepted · **Date:** 2026-08-11 · **Decides:** how §5 Step 1 is actually done

## Decision

Capture real inbound payloads from AXO in production, **scrubbed at the moment of
capture**, and commit the scrubbed result as `fixtures/<source>/`.

The recorder lives in AXO at `backend/services/pil_capture.py`, is gated on the
`PIL_CAPTURE_ENABLED` row in `platform_settings`, and defaults to off. Before anything
reaches disk it:

* redacts credentials, using the pattern ported from the Go agent's redactor
  (`apps/exoagent/internal/evidence/evidence.go:14` — the Python side had none);
* replaces hostnames, IPs, serials, organisation names, emails and device names with a
  **stable keyed hash**, so the same host maps to the same pseudonym across payloads and
  correlation edge cases survive;
* preserves structure exactly — same keys, same nesting, same empty-versus-missing
  versus null distinctions — because those are precisely what the translators branch on.

Capture **fails closed**: with no `PIL_CAPTURE_SALT` configured there is no way to
pseudonymise, so recording is disabled rather than writing raw data.

## Context

§5 Step 1 assumes payloads can be captured. It does not say from where, and the scope
document was written without knowing what AXO already had.

What AXO has is nothing. There is not one real vendor payload saved anywhere in the repo —
no fixtures, no cassettes, no recorded HTTP interactions, no vcr. The nearest candidate,
`tests/demo_alerts/*.yaml`, is five hand-written *pipeline assertions* carrying a
four-field synthetic alert. Real SL1 payloads use `xid`, `yname`, `yseverity`, `ytype` and
`organization`, which `sl_poller.py` reverse-engineers as undocumented "Format A" and
"Format B". Nothing in the repo resembles them.

So the corpus has to be built, and it accrues by calendar time — which is why the recorder
ships before the library rather than after it, contradicting the order in §10.

## Alternatives

**Pull from live vendor APIs.** Needs live credentials and tenant access for four vendors,
and captures API responses rather than the webhook bodies AXO actually receives — a
different shape from the one under test.

**Hand-author payloads from the field names the code sniffs.** Fast and unblocked, but it
is exactly the thin happy-path corpus §9 Risk 3 warns about. It can only contain the edge
cases someone thought of, which is the failure mode capture exists to avoid.

**Capture raw, scrub later.** Rejected: it means real customer data at rest, in a second
store someone has to own, for no gain — the parity comparison feeds both implementations
the same scrubbed fixture, so it is equally valid either way.

## Consequences

Fixtures are pseudonymous, not real. A human reading `host-a1b2c3d4e5f6` cannot tell which
customer it came from, which is the point, and makes the corpus safe to commit and clone.

Parity remains meaningful because both implementations read the same scrubbed input.
Shadow mode, which runs in-process on real unscrubbed traffic, is the backstop for
anything scrubbing might have flattened.

`_malformed/` holds payloads AXO failed to process, captured from the exception path.
These are the most valuable fixtures in the corpus and the ones a happy-path capture never
sees.
