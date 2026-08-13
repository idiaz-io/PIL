# ADR-0002 — Version compatibility rule

**Status:** Accepted · **Date:** 2026-08-11 · **Decides:** §8 decision 1 · **Implements:** I-7

## Decision

**Additive-only within a major version. Unknown fields are ignored, never rejected.**

* Adding an optional field is a minor bump and is always safe.
* Removing a field, renaming one, narrowing a type, or changing what a value means is a
  major bump.
* A consumer reading a message from a newer version keeps what it understands and drops
  the rest. It does not raise.
* `SchemaVersion.parse` is **total**: any unparseable version becomes `UNKNOWN_VERSION`
  rather than an exception.
* A missing *required* field is a malformed message, not a version mismatch, and does
  raise.

Encoded in `pil_contracts/versioning.py` and `Envelope.from_dict`.

## Context

I-7 requires that a consumer built for v1 must not crash on a v2 message, and that the
rule is decided once and encoded in the library rather than reimplemented per consumer.

AXO has no message versioning at all today — a repo-wide search for
`schema_version|message_version|envelope_version` finds only one unrelated string in
`provenance_service.py`. So there is nothing to be compatible with, and no migration
burden. This is the cheapest moment this decision will ever be available.

## Alternatives

**Reject messages from an unknown major.** Rejected: it is precisely the crash I-7
forbids, and it makes every producer upgrade a coordinated outage.

**No version field, rely on structural sniffing.** Rejected: this is what AXO does today
between its two `StandardAlert` shapes, via `getattr(alert, 'description', None) or
getattr(alert, 'message', '')` at `routes/webhook.py:99`. It works until it silently does
not.

## Consequences

The library never drops a message on the floor by itself. A consumer that needs to behave
differently on a newer major asks `SchemaVersion.is_newer_major_than` and decides. That
keeps the policy where the context is, and keeps PIL from making a routing decision on a
product's behalf.
