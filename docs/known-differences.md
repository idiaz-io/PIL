# Known differences between AXO and PIL

Where AXO's existing behaviour turns out to be wrong, it is **not fixed here**. It is
recorded below with a ticket, the parity test keeps asserting AXO's current behaviour, and
the fix ships as a separate change afterwards. Mixing a fix into a migration makes both
unreviewable (I-10, §5 Step 3).

Two categories, kept apart on purpose:

* **Intentional** — PIL deliberately differs, the difference is excluded from the parity
  comparison, and an ADR says why. There should be very few of these; today there is one.
* **Preserved defects** — AXO is wrong, PIL reproduces the wrongness exactly, and a ticket
  tracks fixing it later in both places.

---

## Intentional differences

| Field | AXO | PIL | Why | ADR |
|---|---|---|---|---|
| `tenant_id` | Read from the vendor payload | Taken from the adapter instance's configuration | I-5, and Definition of Done item 7 | [ADR-0004](adr/0004-tenant-resolution.md) |

This is the only field excluded from the byte comparison. `scripts/parity.py` prints the
exclusion on every run so the weaker claim is never mistaken for a full match. PIL records
what the payload claimed in `tenant_hint`, so shadow mode can report how often AXO's
attribution was wrong.

---

## Preserved defects

Behaviour PIL reproduces faithfully **because** it is wrong, so that the migration proves
nothing changed. Each needs a ticket before Phase A closes.

| # | Behaviour | Where in AXO | Ticket |
|---|---|---|---|
| 1 | Tenant derived by string-splitting a vendor URI on the scheduled path — the exact case I-5 says must come from adapter config | `services/sl_poller.py:307` | _to file_ |
| 2 | Tenant read from an unauthenticated-per-tenant webhook body, falling back to the literal `"unknown"` | `integrations/sciencelogic/normaliser.py:143` | _to file_ |
| 3 | An Addigy **policy id** used as the customer id | `integrations/addigy_adapter.py:58` | _to file_ |
| 4 | `datetime.utcnow()` returned when no timestamp field is present, so the same payload yields a different result on every run | `integrations/sciencelogic/normaliser.py:104` | _to file_ |
| 5 | Epoch timestamps parsed with local-time `datetime.fromtimestamp`, so output depends on the host's timezone | `integrations/sciencelogic/normaliser.py:100` | _to file_ |
| 6 | Naive (timezone-less) datetimes emitted throughout | `models/alert.py:24` | _to file_ |

Items 4 and 5 are why the parity harness pins a frozen clock and `TZ=UTC` on both sides.
Without that, "byte-identical" would not be a claim anyone could make.

Items 1–3 are three of the eleven tenant-derivation sites found across AXO. The full list
is in the Phase A findings; fixing them is tracked separately and is explicitly not Phase A
work.

---

## Dead code, not ported

Not a behavioural difference — nothing here executes in AXO, so there is no behaviour to
preserve or diverge from. Recorded so a line-count comparison against AXO's source doesn't
read as a missed port.

| # | Dead code | Where in AXO | Why it's dead |
|---|---|---|---|
| 1 | The `/api/latest/fleet/scripts/run/sync` branch of `execute_on_device`, its 409-Conflict retry, and their exception handling | `backend/integrations/fleet_healing_adapter.py:384-454` | Unreachable — the function always returns or raises inside the retry loop at lines 365-382, before control can fall through to this block. AXO's own comment at line 393 says so: "Keep sync path as dead code in case we want to re-enable." `pil_adapters.execution.fleet.FleetExecutor` ports the live path only: resolve host ID, submit async (`POST /scripts/run`), poll (`GET /scripts/results/{id}`), retry up to 3 times on transient network errors with `30 * attempt` backoff. |

This doesn't interact with the parity harness — `make parity` compares `translate()`
output (alert → `Envelope`), and `execute_on_device` isn't a translation path. Recorded here
for the same audit-trail reason as the other two sections: report it, don't let it be
discovered later by someone diffing line counts.

---

## Fixed during the port, not preserved

Neither an intentional difference (no ADR chose this) nor a preserved defect (the behaviour
is not reproduced) — a third case the two-category framing above doesn't have room for.
`execute_on_device` isn't a translation path, so nothing here is governed by the parity
harness's byte-for-byte comparison; fixing it does not put "parity verified" at risk the way
touching a translator would.

| # | Behaviour in AXO | Where in AXO | What PIL does instead |
|---|---|---|---|
| 1 | `execute_on_device`'s retry-with-backoff loop catches `httpx.ConnectError`/`ConnectTimeout`/`RemoteProtocolError` raised by `_run_async` — but `_run_async` itself wraps its entire body in `except Exception: return ExecutionResult(...)`, so it never raises. The retry loop's own exception handler is unreachable; the same host outage that was meant to trigger a 30s/60s-backed-off retry instead returns a single failed result on the first attempt. | `backend/integrations/fleet_healing_adapter.py:362-382` (loop), `:712-716` (the swallow) | `pil_adapters.execution.fleet.FleetExecutor._run_script` lets those three exception types propagate instead of catching them, so `execute_on_device`'s retry-with-backoff actually fires. Every other exception is still caught inside `_run_script` and turned into a failed `ExecutionResult`, matching AXO. Decided interactively with Hiba during the Phase 3 port (2026-09-19) rather than by ADR, since it isn't an architectural choice — it's restoring behaviour the code was already written to have. |

Found while porting, not before — worth noting because it means AXO's retry has likely
never actually fired in production either, on either side of this migration.

---

## AXO-internal ambiguity, surfaced by this migration

Not a PIL/AXO difference — PIL isn't party to this one. AXO's own two entry points
disagree with *each other* about what the source string `"sciencelogic"` means, on
AXO's `dev` branch (the only branch where the shadow/pil switch exists). This predates
PIL and would be exactly as true if PIL didn't exist; it surfaced now because
`pil_shim.normalise(source, ...)` takes a single string key, and that key is the thing
both call sites disagree about.

| Entry point | What `"sciencelogic"` dispatches to |
|---|---|
| `backend/routes/webhook.py:83-85` | `normalise_sciencelogic_alert(payload)` — the webhook-shaped ScienceLogic normaliser, matching PIL's `sciencelogic` translator |
| `backend/services/orchestrator_v2.py:59-61` (`get_adapter`, the scheduled/poller path) | `SL1Adapter(demo_mode=True).normalize_alert(payload)` — a different adapter entirely, matching PIL's separate `sl1` translator, not `sciencelogic` |

Both call sites pass the *same* string, `"sciencelogic"`, into `pil_shim.normalise()`. On
the webhook path that string correctly pairs with PIL's `sciencelogic` translator. On the
scheduled path, the same string means AXO calls `SL1Adapter`, not the ScienceLogic
normaliser — so if the switch were ever set to `shadow` or `pil` on that path, PIL's
`sciencelogic` translator would be compared against (or substituted for) the wrong AXO
adapter's output. This is not a translation bug on either side; it is AXO's two entry
points not agreeing on what their own shared vocabulary means.

Previously visible only as a citation inside `pil_adapters/translators/sl1_healing.py`'s
module docstring ("`orchestrator_v2.py:61`... demo_mode=True unconditionally"), which
explained the *adapter's* demo-gating but didn't name the dispatch collision itself.
Recorded here because it's a real question about AXO's own wiring that someone has to
answer — do the two paths mean to name the same vendor differently, or is one of them
wrong? — before any real cutover, not something either repo's migration work can resolve
unilaterally.

---

## Shadow mode's blind spot

Found running a local shadow-mode rehearsal (`pil_shim.normalise()` called directly, real
AXO call sites, all 33 synthetic fixtures — 2026-09, against a worktree of AXO's `dev`).
Not a bug — `shadow` mode's behaviour here is *consistent* with `legacy` mode's, which is
exactly why nobody would have written it differently. But it's a real, structural gap in
what shadow mode's evidence can say, worth knowing before anyone reads a clean
`shadow_stats()` report as full coverage.

`pil_shim.normalise()`'s shadow branch (`backend/services/pil_shim.py`, `dev` branch —
this code doesn't exist on `handoff`):

```python
# -- shadow ---------------------------------------------------------------------
# Legacy's result is what the system uses. PIL's is compared and thrown away.
legacy_result = await _call_legacy(legacy)          # <- outside the try/except below

try:
    envelope = _translate_with_pil(source, payload, tenant_id or "shadow-unconfigured")
    ...                                              # comparison, _record(), logging
except Exception as exc:
    _record(source, "error")
    ...
```

`_call_legacy(legacy)` — the call into AXO's own normaliser — runs **unguarded**. When
AXO's legacy path raises on a payload, `pil_shim.normalise()` propagates that exception to
its caller immediately, before `_translate_with_pil` is ever invoked. `_record()` is never
called; no `PIL shadow:` or `PIL shim: handled` log line is ever emitted. The event leaves
no trace in `shadow_stats()` — not `identical`, not `different`, not even `error`; that
`error` bucket is only for a failure inside the *comparison*, after both sides ran.

This matches `legacy` mode's own behaviour exactly (same unguarded call, same
propagation) — the switch doesn't change what happens when AXO's own code raises, which is
presumably the intended, deliberate design: shadow mode's job is to observe, not to change
what production does on any input, including the ones that already error today. That
consistency is exactly what makes the gap easy to miss: **a clean shadow report over real
traffic — 100% identical, 0 different, 0 error — would look like full coverage while
silently omitting every payload where AXO's own normaliser raises**, because those payloads
never reach the counters at all.

Demonstrated directly by three of the 33 synthetic fixtures, each built to make AXO's own
normaliser raise (and each already confirmed, separately, via the parity harness, to make
PIL's translator raise too — "both raise" is the correct, matching behaviour; this section
is not about a disagreement):

| Fixture | AXO's exception (observed via `pil_shim.normalise()`) |
|---|---|
| `fixtures/_synthetic/connectwise/02-null-company-raises-attributeerror.json` | `AttributeError: 'NoneType' object has no attribute 'get'` |
| `fixtures/_synthetic/legacy/03-malformed-timestamp-raises.json` | `ValueError: Invalid isoformat string: 'not-a-date'` |
| `fixtures/_synthetic/legacy/04-empty-string-timestamp-key-present-also-raises.json` | `ValueError: Invalid isoformat string: ''` |

All three propagated out of `pil_shim.normalise()` itself in the rehearsal — none produced
a `shadow_stats()` entry, none logged. A cutover decision that leans on "shadow mode ran
clean for N days" should account for this: clean means *the traffic that didn't already
error* agreed, not that every payload was compared. Whatever fraction of real traffic hits
AXO's own raise-on-malformed-input paths is invisible to this evidence, by construction,
on both `legacy` and `shadow`.
