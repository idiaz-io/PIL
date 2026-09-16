"""The closed capability vocabulary — mirrors the count-pinning and
known/unknown-value tests `pil_graph.tests.test_vocabulary` already
establishes for the ITKG vocabulary (ADR-0011's own pattern), applied here
per ADR-0012.
"""

from __future__ import annotations

import dataclasses

import pytest

from pil_capabilities import CAPABILITIES, CAPABILITY_COUNT, Capability, Risk

#: (key, risk, requires_signature_default) — ported verbatim from
#: `0008_seeds.sql`'s `insert into public.capabilities`.
EXPECTED = [
    ("host.read", Risk.READ, False),
    ("host.list", Risk.READ, False),
    ("alert.subscribe", Risk.READ, False),
    ("repo.read", Risk.READ, False),
    ("llm.infer", Risk.READ, False),
    ("script.execute", Risk.WRITE, True),
    ("policy.enforce", Risk.WRITE, True),
    ("ticket.create", Risk.WRITE, True),
    ("notify.send", Risk.WRITE, True),
    ("repo.write", Risk.WRITE, True),
]


def test_capability_count_is_pinned() -> None:
    assert len(Capability) == CAPABILITY_COUNT == 10


def test_every_capability_has_exactly_one_definition() -> None:
    assert set(CAPABILITIES) == set(Capability)


def test_known_capability_accepted() -> None:
    assert Capability("host.read") is Capability.HOST_READ


def test_unknown_capability_rejected() -> None:
    with pytest.raises(ValueError, match="NotACapability"):
        Capability("NotACapability")


@pytest.mark.parametrize(("key", "risk", "requires_signature_default"), EXPECTED)
def test_capability_matches_the_console_seed_exactly(
    key: str, risk: Risk, requires_signature_default: bool
) -> None:
    definition = CAPABILITIES[Capability(key)]
    assert definition.risk == risk
    assert definition.requires_signature_default == requires_signature_default


def test_requires_signature_default_mirrors_risk_for_every_seeded_row() -> None:
    """True for all ten today (0008's own inference) — not asserted as a
    closed rule CAPABILITIES must always satisfy, just confirmed against
    the values actually ported."""
    for definition in CAPABILITIES.values():
        assert definition.requires_signature_default == (definition.risk is Risk.WRITE)


def test_capability_definition_is_frozen() -> None:
    definition = CAPABILITIES[Capability.HOST_READ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        definition.risk = Risk.WRITE  # type: ignore[misc]
