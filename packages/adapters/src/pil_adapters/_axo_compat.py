"""Helpers that reproduce AXO's behaviour exactly, including where it is wrong.

I-10: "the output must be identical. Not 'equivalent' — identical." Everything here
exists to keep a faithful port faithful, and each function documents the AXO behaviour it
mirrors so that a reader can tell deliberate bug-compatibility from an accident.

Where the reproduced behaviour is a defect, it is listed in ``docs/known-differences.md``
with a ticket. It gets fixed there, after the migration, not here during it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

__all__ = ["as_utc", "epoch_to_datetime", "iso_to_datetime"]


def as_utc(value: datetime) -> datetime:
    """Give a datetime a timezone without moving it in wall-clock terms.

    AXO produces naive datetimes throughout and treats them as UTC downstream. PIL
    requires aware datetimes (I-9 — an ambiguous instant has no canonical form). So a
    naive value is *labelled* UTC rather than converted, which reproduces exactly the
    numbers AXO renders. An already-aware value is converted normally.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def iso_to_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 string the way AXO does, or return None if it cannot.

    Mirrors `integrations/sciencelogic/normaliser.py:92`:
    ``datetime.fromisoformat(str(raw[field]).replace("Z", "+00:00"))``, including the
    blanket ``ValueError``/``TypeError`` swallow that turns a malformed timestamp into a
    silent fallback rather than an error.
    """
    try:
        return as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (ValueError, TypeError):
        return None


def epoch_to_datetime(value: Any) -> datetime | None:
    """Parse an epoch the way AXO does, or return None if it cannot.

    Mirrors `integrations/sciencelogic/normaliser.py:100`:
    ``datetime.fromtimestamp(float(raw[field]))``.

    That call is **local time** — AXO's output therefore depends on the host's timezone,
    and CI and a developer's laptop disagree about the same payload. Preserved defect 5
    in ``docs/known-differences.md``.

    The port reproduces the wall-clock numbers AXO produces: convert in local time, then
    label the result UTC, which is precisely what AXO's downstream does with its naive
    value. The parity harness additionally pins ``TZ=UTC`` on both sides so the
    comparison does not depend on where it runs.
    """
    try:
        return as_utc(datetime.fromtimestamp(float(value)))
    except (ValueError, TypeError, OSError, OverflowError):
        return None
