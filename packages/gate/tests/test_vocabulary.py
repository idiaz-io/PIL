"""Closed vocabularies — pinned counts, console CHECK strings byte-exact."""

from __future__ import annotations

import pytest

from pil_gate.vocabulary import DECISION_COUNT, TIER_COUNT, ActorKind, Decision, Tier


def test_decision_count_is_pinned() -> None:
    assert len(Decision) == DECISION_COUNT == 3


def test_tier_count_is_pinned() -> None:
    assert len(Tier) == TIER_COUNT == 4


def test_known_decision_accepted() -> None:
    assert Decision("allow") is Decision.ALLOW


def test_unknown_decision_rejected() -> None:
    with pytest.raises(ValueError, match="NotADecision"):
        Decision("NotADecision")


def test_unknown_tier_rejected() -> None:
    with pytest.raises(ValueError, match="not-a-tier"):
        Tier("not-a-tier")


def test_decision_strings_match_the_console_check_exactly() -> None:
    """0005_products_and_entitlement.sql: decision in ('allow', 'hold', 'deny')."""
    assert {member.value for member in Decision} == {"allow", "hold", "deny"}


def test_tier_strings_match_the_console_check_exactly() -> None:
    """0005 CHECK: observe-only | safe-auto-heal | approval-required | blocked-by-default."""
    assert [member.value for member in Tier] == [
        "observe-only",
        "safe-auto-heal",
        "approval-required",
        "blocked-by-default",
    ]


def test_actor_kind_is_human_or_service() -> None:
    assert {member.value for member in ActorKind} == {"human", "service"}
