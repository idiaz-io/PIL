"""Translator registry.

A function, not a module-level dict, and that is the whole point.

AXO reads configuration at module import time — `services/adapters/fleet_adapter.py:31`
evaluates ``os.getenv("FLEET_SYNC_ENABLED")`` when the module loads, which is why
`tests/conftest.py:9-11` has to mutate ``os.environ`` before importing the application,
and why the same file then needs three separate layers of DB/env/module reconciliation to
work out whether the adapter is on. Shadow mode would inherit every bit of that: you
cannot run two configurations side by side in one process when configuration is decided
at import.

So: nothing here runs at import. Configuration and the clock are arguments, an instance
is cheap, and a caller can hold a legacy and a PIL registry at once.
"""

from __future__ import annotations

from pil_adapters.base import AdapterConfig, Translator
from pil_adapters.clock import Clock
from pil_adapters.translators.addigy import AddigyTranslator
from pil_adapters.translators.connectwise import ConnectWiseTranslator
from pil_adapters.translators.fleet import FleetTranslator
from pil_adapters.translators.legacy import LegacyTranslator
from pil_adapters.translators.sciencelogic import ScienceLogicTranslator
from pil_adapters.translators.sl1_healing import SL1HealingTranslator

__all__ = ["TRANSLATOR_TYPES", "build_registry", "get_translator"]

#: Every translator PIL knows about, keyed by source.
#:
#: ``sciencelogic`` and ``sl1`` are both ScienceLogic and are deliberately separate
#: entries: AXO runs two different SL1 translations on two different paths, and they
#: disagree. Collapsing them would be a behaviour change, not a tidy-up.
TRANSLATOR_TYPES: dict[str, type[Translator]] = {
    "sciencelogic": ScienceLogicTranslator,
    "sl1": SL1HealingTranslator,
    "connectwise": ConnectWiseTranslator,
    "fleet": FleetTranslator,
    "addigy": AddigyTranslator,
    "legacy": LegacyTranslator,
}


def build_registry(config: AdapterConfig, clock: Clock | None = None) -> dict[str, Translator]:
    """Instantiate every translator for one tenant.

    All instances share the config, so every message this registry produces carries the
    same tenant (I-5). Two tenants means two registries.
    """
    return {source: cls(config, clock) for source, cls in TRANSLATOR_TYPES.items()}


def get_translator(
    source: str,
    config: AdapterConfig,
    clock: Clock | None = None,
) -> Translator:
    """Build the translator for one source.

    Unlike AXO's ``get_adapter``, an unknown source raises rather than returning a stub.
    `orchestrator_v2.py:62` falls back to ``StubAdapter``, whose every method raises
    ``NotImplementedError`` when called — so the failure surfaces somewhere else, later,
    with no indication of which source was unhandled. Fail where the mistake is.
    """
    try:
        cls = TRANSLATOR_TYPES[source]
    except KeyError:
        known = ", ".join(sorted(TRANSLATOR_TYPES))
        raise KeyError(f"no translator for source {source!r}. Known sources: {known}") from None
    return cls(config, clock)
