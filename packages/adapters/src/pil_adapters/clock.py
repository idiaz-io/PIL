"""Time, injected.

Every translator needs a clock because AXO's normalisers reach for the current time
whenever a payload does not carry a usable one — ``datetime.utcnow()`` appears as a
fallback in `integrations/sciencelogic/normaliser.py:104` and unconditionally in the
Fleet, SL1 and Addigy adapters.

That makes their output non-deterministic: the same payload produces a different result
on every run. Parity against a saved fixture is impossible unless both implementations
read the same clock, so the clock is a parameter rather than a global.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "FrozenClock", "SystemClock"]


@runtime_checkable
class Clock(Protocol):
    """Source of the current instant. Must return a timezone-aware datetime."""

    def now(self) -> datetime: ...


class SystemClock:
    """The real clock. Always UTC, always aware."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def __repr__(self) -> str:
        return "SystemClock()"


@dataclass(frozen=True, slots=True)
class FrozenClock:
    """A clock that does not move. Used by tests and by the parity harness.

    AXO produces naive datetimes; PIL requires aware ones. Defaulting the timezone to
    UTC here matches what AXO's ``utcnow()`` actually meant, while making it explicit.
    """

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None:
            object.__setattr__(self, "instant", self.instant.replace(tzinfo=UTC))

    def now(self) -> datetime:
        return self.instant
