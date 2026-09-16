"""Which of PIL's own translators provide which capability.

Scoped to what Phase A's translate-only code actually does, not to the full
vendor tool's API surface. `0017_seed_pil_confirmed_adapters.sql` (the
merp-console migration that first added `sl1`/`addigy`) already drew this
line for those two: "Neither translator PIL ships for these two sources does
anything beyond alert translation... `host.read`/`host.list` are NOT seeded
here on that basis, unlike `fleet`/`sciencelogic` above, which already carry
those from `0008` on the strength of the full vendor tool's API rather than
what PIL's translate-only Phase A actually ported."

This module applies that same standard *uniformly*, across every translator
PIL has, including `fleet` and `connectwise` — which merp-console's existing
seed data does not: those two adapters' extra rows there
(`host.read`/`host.list`/`script.execute` on `fleet`, `ticket.create` on
`connectwise`) describe the full vendor tool or a *different, unported* AXO
code path, not this repo's translator.

`connectwise` is the sharpest case: :class:`~pil_adapters.translators.
connectwise.ConnectWiseTranslator` (ported from `ticket_normaliser.py`)
normalises an *inbound* ticket-shaped webhook into an Envelope — the
opposite direction from ``ticket.create`` (AXO calling *out* to ConnectWise
to create one). Claiming ``ticket.create`` here would describe AXO's
separate, unported write path (`services/adapters/connectwise_adapter.py`),
not what this translator does.

Every translator here does exactly one thing: turn one inbound vendor
payload into one Envelope. That is ``alert.subscribe``, for all five.
`legacy` has no entry — it is not a vendor tool a tenant configures (see
`pil_adapters.registry`'s own comment on it), so it provides no capability
by name, the same way it has no `adapter_config_fields` in merp-console's
schema.
"""

from __future__ import annotations

from collections.abc import Mapping

from pil_capabilities import Capability

__all__ = ["TRANSLATOR_CAPABILITIES", "capabilities_for"]

#: Every real translator provides exactly one capability today: it ingests
#: one vendor's payload shape and produces an Envelope. Not the same set of
#: capabilities merp-console's own (looser) adapter_capabilities seed
#: currently lists for `fleet`/`connectwise` — see the module docstring.
TRANSLATOR_CAPABILITIES: Mapping[str, tuple[Capability, ...]] = {
    "sciencelogic": (Capability.ALERT_SUBSCRIBE,),
    "sl1": (Capability.ALERT_SUBSCRIBE,),
    "connectwise": (Capability.ALERT_SUBSCRIBE,),
    "fleet": (Capability.ALERT_SUBSCRIBE,),
    "addigy": (Capability.ALERT_SUBSCRIBE,),
}


def capabilities_for(source: str) -> tuple[Capability, ...]:
    """The capabilities this repo's own translator for `source` actually
    provides. Empty for `legacy` and for any unrecognised source — not a
    KeyError, since "provides nothing" is a valid, ordinary answer here
    (unlike `pil_adapters.registry.get_translator`, whose job is to say
    whether a source is known at all)."""
    return TRANSLATOR_CAPABILITIES.get(source, ())
