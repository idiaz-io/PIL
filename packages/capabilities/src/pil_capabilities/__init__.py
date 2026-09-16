"""pil_capabilities — the closed vocabulary of what a product may do to an
external system through a connection.

Definitions only, dependency-free — not on anything else in this repo, and
not on anything outside the standard library. See
:mod:`pil_capabilities.capability` for why this is its own package rather
than a module inside `pil_contracts` or `pil_adapters`.
"""

from pil_capabilities.capability import (
    CAPABILITIES,
    CAPABILITY_COUNT,
    Capability,
    CapabilityDefinition,
    Risk,
)

__all__ = [
    "CAPABILITIES",
    "CAPABILITY_COUNT",
    "Capability",
    "CapabilityDefinition",
    "Risk",
]
