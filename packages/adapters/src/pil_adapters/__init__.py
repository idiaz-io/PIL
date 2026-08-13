"""pil_adapters — translate vendor payloads into contract shapes.

Phase A is translate-only (ADR-0005). Nothing here connects to anything, executes
anything or retries anything; a translator turns one payload into one
:class:`~pil_contracts.Envelope` and returns it to its caller.
"""

from pil_adapters.base import AdapterConfig, Translation, Translator
from pil_adapters.clock import Clock, FrozenClock, SystemClock
from pil_adapters.registry import TRANSLATOR_TYPES, build_registry, get_translator
from pil_adapters.translators.addigy import AddigyTranslator
from pil_adapters.translators.connectwise import ConnectWiseTranslator
from pil_adapters.translators.fleet import FleetTranslator
from pil_adapters.translators.legacy import LegacyTranslator
from pil_adapters.translators.sciencelogic import ScienceLogicTranslator
from pil_adapters.translators.sl1_healing import SL1HealingTranslator

__all__ = [
    "TRANSLATOR_TYPES",
    "AdapterConfig",
    "AddigyTranslator",
    "Clock",
    "ConnectWiseTranslator",
    "FleetTranslator",
    "FrozenClock",
    "LegacyTranslator",
    "SL1HealingTranslator",
    "ScienceLogicTranslator",
    "SystemClock",
    "Translation",
    "Translator",
    "build_registry",
    "get_translator",
]
