"""Which translator provides which capability — scoped to translate-only
reality, not the full vendor tool's API. See the module docstring in
`pil_adapters.capabilities` for why `fleet` and `connectwise` carry only
`alert.subscribe` here despite merp-console's own (looser) seed data.
"""

from __future__ import annotations

from pil_adapters.capabilities import TRANSLATOR_CAPABILITIES, capabilities_for
from pil_adapters.registry import TRANSLATOR_TYPES
from pil_capabilities import Capability


def test_every_entry_is_a_known_translator() -> None:
    assert set(TRANSLATOR_CAPABILITIES) <= set(TRANSLATOR_TYPES)


def test_legacy_has_no_capability() -> None:
    """Not a vendor tool a tenant configures — see pil_adapters.registry's
    own comment on it."""
    assert "legacy" not in TRANSLATOR_CAPABILITIES
    assert capabilities_for("legacy") == ()


def test_every_real_translator_provides_exactly_alert_subscribe() -> None:
    """Every translator here does one thing: turn an inbound vendor payload
    into an Envelope. Not host.read/host.list/script.execute/ticket.create —
    those describe a vendor tool's full API or a different, unported AXO
    code path, not this repo's translate-only code."""
    for source in TRANSLATOR_TYPES:
        if source == "legacy":
            continue
        assert capabilities_for(source) == (Capability.ALERT_SUBSCRIBE,), source


def test_unknown_source_provides_nothing() -> None:
    assert capabilities_for("not-a-real-source") == ()
