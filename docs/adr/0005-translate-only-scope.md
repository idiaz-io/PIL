# ADR-0005 — Phase A migrates translation only

**Status:** Accepted · **Date:** 2026-08-11 · **Amends:** §3 of the Phase A scope

## Decision

Phase A migrates the **inbound translate** surface and nothing else. `connect`,
`execute_on_device`, `check_connectivity`, `fetch_device_details` and the `verify_*`
methods stay in AXO and are deferred, along with the inventory-sync path.

## Context

The scope document describes "the adapter framework — connect + translate + retry +
registry" as though it were one thing. Reading AXO shows otherwise.

**There are five live adapter shapes**, not one or two: the CMDB inventory adapters
(`backend/services/adapters/`, producing `NormalisedDevice`), the healing adapters
(`backend/integrations/`, producing `StandardAlert` *and executing*), the webhook
normaliser functions (`msp-platform/integrations/`), the v1 monolith
(`services/self_healing.py`), and the Go ExoAgent adapters.

**Only `normalize_alert` is real.** Every other method on the healing adapter base class
branches on `self._demo`, and `orchestrator_v2.py:55,61` constructs both `AddigyAdapter`
and `SL1Adapter` with `demo_mode=True` unconditionally. `normalize_alert` is the sole
method with no demo branch.

That matters because of what §5 Step 1 asks for: "Run each through AXO's **current** code
and save what comes out. That saved output is now the specification." For SL1 and Addigy,
the execute and verify paths return `_demo_device_profile()` — a hardcoded
`10.10.5.99` on `macOS Sonoma 14.3`. Capturing that would make the parity suite assert, in
CI, that a fixture is the specification. The test would pass and mean nothing, which is
worse than not having it.

**Retry does not exist to migrate.** There is exactly one retry loop in the entire
integration surface (`fleet_healing_adapter.py:364`, linear 30s, connection errors only,
ignores 429 and 5xx). No `tenacity`, no `backoff`, no rate limiting, no dead-lettering,
and pagination hand-rolled four times. Two of the four words in "connect + translate +
retry + registry" describe new construction, not a lift.

## Alternatives

**Migrate the whole healing adapter interface.** Matches §3 literally. Rejected: for
everything but Fleet, parity would prove the fakes match the fakes.

**Migrate the inventory path instead.** It has the cleanest coupling in AXO — its base
class imports stdlib only. Rejected for Phase A because it is the periodic-reconciliation
shape rather than the event shape, and doing both at once doubles a first migration whose
whole purpose is to be small. Deferred to Phase B as the second migration §9 Risk 2
anticipated.

## What "translate" turned out to mean: six paths, not one

Once the surface was scoped, the count of things to port was not obvious either. Six
distinct translations produce a `StandardAlert` in AXO today, and they disagree with each
other:

| Source | From | Note |
|---|---|---|
| `sciencelogic` | `integrations/sciencelogic/normaliser.py:107` | webhook; `or` chains |
| `sl1` | `backend/integrations/sl1_adapter.py:44` | **a second, different** SL1 mapping |
| `connectwise` | `integrations/connectwise/ticket_normaliser.py:69` | `.get` defaults, not `or` |
| `fleet` | `backend/integrations/fleet_healing_adapter.py:108` | 764-line file with no tests |
| `addigy` | `backend/integrations/addigy_adapter.py:43` | policy id used as customer id |
| `legacy` | `backend/routes/webhook.py:22` | lives in a route file; raises where others fall back |

`sciencelogic` and `sl1` are both ScienceLogic and are kept as separate translators. They
use different severity maps (`"critical"` → P2 in one, P1 in the other), derive category
differently, and disagree on field precedence. Collapsing them would be a behaviour
change.

**Deferred: `services/sl_poller.py:238` `_normalise_api_alert`.** This was counted as a
seventh translate path during planning. It is not one. It returns a **dict shaped for a
database row** — `description` rather than `message`, `timestamp` as a possibly-empty
string, plus `ext_ticket_ref` and `counter` — and it feeds `_process_alert`, which writes
to the alerts feed. The healing path for poller events goes through `SL1Adapter.
normalize_alert`, which *is* ported. Mapping the row shape onto the envelope means
deciding where `ext_ticket_ref` and `counter` live, which is an envelope question and so
an ADR of its own. It is out of Phase A.

## Consequences

Phase A is smaller than the scope document implies, and honest about which surface a
parity proof can cover.

Splitting inbound translation from outbound execution is a design decision that Phase A
defers rather than makes. `backend/integrations/base.py:47` puts `execute_on_device` on
the same ABC as `normalize_alert`; whether PIL should reproduce that fusion or separate
them needs its own ADR, written when the outbound surface is no longer demo-locked.
