"""Message versioning — invariant I-7.

"Message shapes are versioned from the first line of code. Every message carries its
schema version. A consumer built for v1 must not crash on a v2 message. Decide the
compatibility rule once and encode it in the library."

This module is that encoding. The rule (ADR-0002):

**Additive-only within a major version. Unknown fields are ignored, never rejected.**

Concretely:

* Adding an optional field is a **minor** bump and is always safe.
* Removing a field, renaming one, narrowing a type, or changing what a value means is
  a **major** bump.
* A consumer parsing a message from a *newer* version keeps the fields it understands
  and drops the rest. It does not raise. This is the "must not crash" half of I-7, and
  it is the half that gets forgotten, so :func:`parse_version` is total: any input it
  cannot understand becomes ``UNKNOWN`` rather than an exception.
* A consumer that needs to *act* differently on a newer major asks
  :meth:`SchemaVersion.is_newer_major_than` and decides for itself. The library never
  decides to drop a message on the floor.

A missing required field is a different thing entirely — that is a malformed message,
not a version mismatch, and it does raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = ["CURRENT_SCHEMA_VERSION", "UNKNOWN_VERSION", "SchemaVersion"]


@dataclass(frozen=True, slots=True, order=True)
class SchemaVersion:
    """A ``MAJOR.MINOR`` schema version."""

    major: int
    minor: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}"

    @classmethod
    def parse(cls, raw: object) -> SchemaVersion:
        """Parse a version. Total by design — never raises.

        Anything unparseable becomes :data:`UNKNOWN_VERSION`, because a consumer that
        blows up on a malformed version string is exactly the crash I-7 forbids.
        """
        if isinstance(raw, SchemaVersion):
            return raw
        if raw is None:
            return UNKNOWN_VERSION

        text = str(raw).strip()
        if not text:
            return UNKNOWN_VERSION

        major, _, minor = text.partition(".")
        try:
            major_value = int(major)
        except ValueError:
            return UNKNOWN_VERSION
        try:
            minor_value = int(minor) if minor else 0
        except ValueError:
            minor_value = 0

        if major_value < 0 or minor_value < 0:
            return UNKNOWN_VERSION
        return cls(major_value, minor_value)

    @property
    def is_known(self) -> bool:
        return self != UNKNOWN_VERSION

    def is_compatible_with(self, consumer: SchemaVersion) -> bool:
        """True when a consumer built for ``consumer`` can read this message.

        Same major means yes, in both directions: forward because additions are
        ignorable, backward because everything added since was optional.
        """
        return self.is_known and self.major == consumer.major

    def is_newer_major_than(self, consumer: SchemaVersion) -> bool:
        """True when this message comes from a later major than the consumer knows.

        The message is still parseable — the consumer decides whether to trust it.
        """
        return self.is_known and self.major > consumer.major


#: Sentinel for a version we could not parse. Deliberately sorts below every real
#: version so ``is_newer_major_than`` is False for it.
UNKNOWN_VERSION: Final = SchemaVersion(-1, -1)

#: The version this build of the library writes.
CURRENT_SCHEMA_VERSION: Final = SchemaVersion(1, 0)
