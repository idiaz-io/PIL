"""Every translator in this package cites an AXO source file in its module
docstring — ``msp-platform/...`` — without naming a branch. All of those
paths are on ``idiaz-io/Axo``'s `merp-integration` branch (the merge of
`merp-itkg-spine`, PR #47, 2026-08-15), not `main`.

This matters more than it looks: `main` has taken no commits since
2026-04-07, and checked directly at each branch's current tip, three of the
six cited files are not interchangeable between the two —
`addigy_adapter.py` and `fleet_healing_adapter.py` don't exist on `main` at
all, `sl1_adapter.py` is at a different path there, and `webhook.py`
(`legacy.py`'s source) has different content. Only `ticket_normaliser.py`
(`connectwise.py`) and `sciencelogic/normaliser.py` (`sciencelogic.py`) are
byte-identical on both branches. See `docs/reconciliation.md`'s D6 addendum
(2026-09-16) for the full comparison — that's also where `AXO_PARITY_SHA`
must be pinned to `merp-integration`, not `main`, for exactly this reason.
"""
