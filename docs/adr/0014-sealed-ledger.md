# ADR-0014 — The sealed ledger: `pil_ledger`, HMAC chain, and what it deliberately does not store

**Status:** Accepted — decided by Muhammad Shabbar, 2026-09-17 ·
**Relates to:** ADR-0001 (`pil_ledger` already reserved), ADR-0006 (signed bytes must not
depend on a third-party serialiser), ADR-0011 (library owns the algorithm, not the live
store — same split as graph/no driver), ADR-0013 (the gate never writes the ledger;
`GateDecision.to_record()` is the seam), `docs/reference/PIL-PLAN.md` (Friday — sealed
ledger), `MERP-Agent-Handover.md` §6.4, merp-console `0006_ledger.sql` and
`0019_connections_credential_gate_and_ledger_seal.sql`

## Decision

PIL gains a fifth package, `packages/ledger/` (`pil-ledger`, import name `pil_ledger`), that
answers exactly one question — *seal this evidence, and later prove nobody tampered with
it* — with the console's working chain fields: `prev_entry_hash`, `entry_hash`, `signature`,
`payload_hash`, `payload_ref`. It depends on **nothing**. It ships an abstract `Ledger`,
one real sealer/verifier `HmacSealer`, an in-memory chain `MemoryLedger` for tests, and a
test double `StaticLedger`, with tests — not a spec for someone to code later.

The product persists the sealed row. PIL never opens a database, never holds a long-lived
log, and never serves HTTP (I-1). An auditor with an exported slice and the tenant's HMAC
key can call `verify()` fully offline.

Seven sub-decisions, each one paragraph:

1. **Own package, zero dependencies.** Evidence hashing is neither wire shape
   (`pil_contracts`), vendor translation (`pil_adapters`), graph access (`pil_graph`), nor
   authorization (`pil_gate`). The gate's own ADR forbade importing contracts for
   canonicalisation and forbade the gate writing the ledger; this package is that missing
   half. A reviewer should see `dependencies = []` in `pyproject.toml`. `hashlib` and
   `hmac` are stdlib. RFC8785 / a third-party canonicaliser would be a later ADR (0006:
   a dependency must not change signed bytes).

2. **Port the console's HMAC, do not pretend cosign.** merp-console's trigger
   (`ledger_entries_seal_and_sign`, migration 0019) already computes a real HMAC-SHA256
   keyed by a per-tenant secret, algorithm string `hmac-sha256-interim`. Handover §6.4
   names RFC8785 payloads and cosign signatures; those are not what runs today, and
   shipping them in the same change would mix a port with a crypto upgrade. v1 algorithm
   is `hmac-sha256-interim`. KMS, customer-held asymmetric keys, and cosign need their
   own ADR once a key service exists. `HmacSigner` is a protocol-shaped class so that
   ADR can replace the signer without changing `seal()`.

3. **`seal()` is pure; the product supplies `seq` and `prev_entry_hash`.** Same posture
   as `ReferenceGate.decide()`: no I/O, no hidden head-of-chain. Genesis is `seq=1` with
   `prev_entry_hash=None`, hashed as the empty string — `coalesce(v_prev, '')` in the
   console trigger. `MemoryLedger.append()` is the in-process chain that assigns `seq`
   and remembers the head, for tests; it is not the store a product uses in production.

4. **Caller cannot supply `entry_hash` or `signature`.** `SealInput` has no such fields,
   the same way `GateRequest` has no `tier`. Hashes and the signature are computed inside
   `HmacSealer.seal()` and cannot be constructed onto the input type.

5. **The ledger does not import `pil_gate`.** A gate decision is one payload kind
   (`policy_decision`). Findings, attestations, breaker trips are others. The seam is an
   opaque mapping of primitives (`GateDecision.to_record()` or any other dict). The
   workspace may test that seam; the package must not.

6. **Payload content never lives on a sealed entry.** `SealedEntry` carries `payload_hash`
   + `payload_ref` only (handover: redaction-at-append). Forbidden payload keys
   (`quoted_text`, `artifact_text`, `narrative`, `content`, `sensor_payload`,
   `device_payload`, `identity_payload`, `playbook_body`) are rejected at `SealInput`
   construction rather than silently stripped — the caller redacts; the ledger refuses
   to hash raw artifact text. `verify_payload(entry, payload)` is how an auditor who
   still has the body checks the hash; `verify()` on a slice does not need the body.

7. **Closed `kind` set, console's five.** `finding | change_record | attestation |
   policy_decision | breaker_trip`, pinned by `KIND_COUNT = 5`. Handover also names
   `oscal_emission` and `exercise_report`; those are not in the console CHECK and are
   not added here (I-6: an ADR to add a member). `event_type` stays an open non-blank
   string — the console's `ledger_event_types` catalogue is console-authored (I-2).

## The chain formula (v1)

`payload_hash` is SHA-256, hex, over canonical JSON (`sort_keys=True`,
`separators=(",", ":")`, UTF-8) of a document that includes tenant, kind, event_type,
subject, actor, assumed role, occurred_at (RFC3339), payload_ref, and the caller's
payload mapping. That is stricter than the console trigger, which hashed
`tenant|event|subject|actor|time` because it had no payload store; PIL actually has a
payload, so the hash covers it. `occurred_at` must be timezone-aware.

`entry_hash` is SHA-256, hex, over `prev_entry_hash || "|" || seq || "|" || payload_hash`
with a missing prev rendered as `""` — byte-for-byte the console trigger's
`entry_hash` preimage shape.

`signature` is HMAC-SHA256 of the UTF-8 `entry_hash` with the tenant secret, hex —
the console trigger's `extensions.hmac(..., 'sha256')`.

Tampering a stored field that is inside the payload document, dropping a seq, swapping
two entries, or signing with the wrong key makes `verify()` report `ok=False` and the
first broken `seq`.

## Alternatives

**Fold into `pil_gate`.** Rejected — only one of five kinds is a policy decision, and
ADR-0013 already forbade the gate writing the ledger.

**Depend on `pil_contracts` for canonical JSON.** Rejected for v1 — ADR-0006's reason
applies even more tightly here: a serialiser bump would change every `payload_hash`.
Stdlib `json` with pinned separators is enough until RFC8785 is its own ADR.

**Ship a Postgres driver / replace the console trigger.** Rejected — I-1, and the
console's trigger is product persistence. Wiring merp-console or AXO to call this
library is a separate cross-repo change, same as the gate.

**Asymmetric signatures in v1.** Rejected — no KMS, and the console is honest that
`public_key` is currently a fingerprint of an HMAC secret. Pretending otherwise in PIL
would be a worse lie.

**Let `seal()` store the chain.** Rejected for the production type (`HmacSealer`).
Hidden state would make two products sharing a process collide, and would hide the
fact that durability is the caller's job. `MemoryLedger` exists so tests (and only
tests) need not fake `seq`/`prev`.

## What this does not resolve

- **Replacing `ledger_entries_seal_and_sign` in merp-console.** Cross-repo.
- **AXO calling this on a remediation.** Product work.
- **RFC8785 / cosign / customer-held keys / `merp verify` CLI.** Later ADRs.
- **A payload blob store** (knowledge vault). `payload_ref` is a URI, not a foreign key.
- **`oscal_emission` / `exercise_report` kinds.** Not in the console CHECK.

## Consequences

- New package `packages/ledger` (`pil-ledger`), `dependencies = []`, pinned by
  `tests/test_invariants.py`.
- I-1 and I-3 scans gain `LEDGER_SRC`.
- Root `pyproject.toml`: `pil-ledger` added to sources, dev, testpaths, ruff, mypy,
  isort. `uv.lock` regenerated.
- `CLAUDE.md` §1 row 4 and `PIL-HANDOVER.md`'s component table change from **Absent**
  to **Real (HMAC-SHA256 interim; no store, no KMS)** in the same commit as the code.
- `PIL-PLAN.md` Friday row: state → shipped, once the suite passes.
