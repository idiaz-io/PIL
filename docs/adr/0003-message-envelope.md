# ADR-0003 — The message envelope

**Status:** Accepted · **Date:** 2026-08-11 · **Decides:** §4, §8 decision 4 · **Implements:** I-6, I-7, I-9

## Decision

A new envelope, defined in `pil_contracts`, kind-agnostic from the first commit:

```
Envelope
  schema_version   tenant_id      source            occurred_at   body
  kind             tenant_hint    adapter_version   observed_at   raw_payload
  event_id
```

`kind` is a closed vocabulary (I-6) with one member today, `alert`. Kind-specific fields
live in `body` — `AlertBody` carries `alert_id`, `device_id`, `device_name`, `severity`,
`category`, `message`, `device_history`.

`translate()` **returns** an envelope to its caller. There is no sink, no table, no bus
(§8 decision 4).

## Context

§4 asks for the envelope, its version field, the tenant, the source and adapter version,
and both "when it happened" and "when it was observed".

AXO has no single shape to start from. There are two classes both named `StandardAlert`
— `backend/models/alert.py:9` (Pydantic, field `description`) and
`backend/services/reasoning/interfaces.py:20` (dataclass, field `message`) — with
`routes/webhook.py:99` reconciling them by reflection at runtime. Neither carries a
version, both default their timestamp to a naive `datetime.utcnow()`.

## Alternatives

**Adopt one of AXO's two shapes.** Rejected: adopting either means changing the other's
producers, and neither meets I-7 or I-9. Choosing between them is a behaviour change
whichever way it goes, so the cost is the same as designing properly.

**A flat, alert-shaped envelope** with `severity` and `category` at the top level.
Rejected on §9 Risk 4: adapters are the only producer today, findings and attestations
are coming, and reworking the envelope after messages are signed is exactly the retrofit
I-9 warns about. Splitting `body` out costs one level of nesting now and avoids a
migration later.

**Route the translated message onto a bus or into a table.** Rejected: the bus is a later
component, and anything PIL provides for moving messages between products makes I-4
easier to break. Returning a value keeps I-1 and I-4 true by construction.

## Consequences

`raw_payload` is carried verbatim, matching AXO. That means input non-determinism
propagates into output, which the parity harness handles by pinning the clock rather than
by editing the payload.

Field values are unvalidated strings. AXO emits `"P1"`–`"P4"` from some paths, raw vendor
severities from others and the literal `"unknown"` from several; I-10 requires reproducing
that exactly. Tightening any of them is a separate change after the migration.

Adding a second `kind` is an ADR, not a commit.
