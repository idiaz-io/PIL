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
