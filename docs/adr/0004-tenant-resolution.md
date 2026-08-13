# ADR-0004 — Tenant resolution, and the I-5 / I-10 conflict

**Status:** Accepted · **Date:** 2026-08-11 · **Implements:** I-5 · **Resolves:** a direct contradiction in the Phase A scope

## Decision

PIL emits the tenant from the **adapter instance's own configuration**, always. The value
the vendor payload claimed is carried alongside as `tenant_hint`, which is evidence and
never identity — nothing may route, authorise or query on it.

The parity harness compares every field **except** `tenant_id`, and separately asserts
that the emitted tenant equals the configured one. This is the single documented
intentional difference between AXO and PIL.

## Context

The scope document contains a contradiction that only shows up once you read AXO.

* **Definition of Done item 7:** "A lint rule or test fails the build if an adapter emits
  a message whose tenant differs from its configured tenant."
* **I-10 and §5 Step 3:** the migration must preserve behaviour identically, and where
  AXO's behaviour is wrong, "keep the parity test asserting the current (wrong) behaviour".

AXO's behaviour is to read the tenant out of the vendor payload. Reproducing that
byte-identically means violating I-5 in new code and failing DoD item 7. Both cannot hold.

The scale of the underlying defect, confirmed in code across eleven sites:

* `integrations/sciencelogic/normaliser.py:143` — `raw.get("client_id") or raw.get("org_id")
  or raw.get("organization_id") or "unknown"`, on a webhook gated only by a single shared
  secret, so any tenant able to post can claim any other tenant's id.
* `services/sl_poller.py:307` — the **scheduled** path, where I-5 explicitly says the
  tenant must come from adapter configuration, derives it by string-splitting a vendor URI.
* `services/adapters/fleet_adapter.py:265` — fuzzy `ILIKE` match on a vendor-supplied team
  name with `LIMIT 1` and no `ORDER BY`, falling back to the raw team name on DB error.
* `integrations/addigy_adapter.py:58` — an Addigy **policy id** used as the customer id.

Nine of those sites default to the literal string `"unknown"`, and `cmdb_sync.py:302`
then merges devices across customers whose tenant failed to resolve, because
`"unknown" == "unknown"` passes its only guard.

## Alternatives

**Preserve the defect, fix separately.** The strict reading of §5 Step 3. Rejected because
DoD item 7 exists specifically, in the scope author's words, "to prevent repeating AXO's
live customer-separation defect **in new code**" — and this option writes the defect into
new code by design. It also leaves the parity suite asserting, in CI, that reading tenancy
from an untrusted payload is correct.

**Enforce I-5 and discard the evidence.** Simplest to reason about. Rejected because
shadow mode running over real production traffic is the only opportunity we will get to
measure how often AXO's tenant attribution is actually wrong, and that number is worth
having before anyone decides how urgently to fix the eleven sites.

## Consequences

Parity is no longer "every byte of the output", it is "every byte except one field, plus
an assertion about that field". That is a weaker claim, stated explicitly rather than
quietly, and `scripts/parity.py` prints it on every run so nobody can mistake it for a
full byte-for-byte match.

Fixing the eleven sites in AXO is out of scope here and tracked separately. PIL stops the
bleeding in new code; it does not treat the patient.
