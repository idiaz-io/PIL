"""Deterministic serialisation — invariant I-9.

Anything that will later be hashed or signed must serialise byte-identically every time.
Ordering, whitespace and number formatting all matter. Retrofitting this invalidates
every signature written before the fix, which is why it lands before anything else.

The rules, all of which are asserted by tests:

* **Key order** is lexicographic by Unicode code point, at every level of nesting.
* **Whitespace** is absent. ``,`` and ``:`` carry no padding.
* **Encoding** is UTF-8, with non-ASCII characters emitted literally rather than as
  ``\\uXXXX`` escapes, so the same text is always the same bytes.
* **Floats** must be finite. ``NaN``, ``Infinity`` and ``-Infinity`` are not JSON and
  are rejected rather than emitted as bare tokens that no other parser accepts.
* **Keys** must be strings. Python would happily coerce ``1`` and ``"1"`` to the same
  JSON key and silently drop one; that is a data-loss bug, so it is rejected.
* **Types** are restricted to the JSON set. Anything else — a ``datetime``, a
  ``Decimal``, a dataclass — must be converted by the caller, deliberately, so that no
  implicit ``str()`` ever decides what our bytes look like.

Deliberately *not* done: Unicode normalisation. NFC-normalising would change the
payload we were given, and a parity harness comparing two implementations of the same
translation needs both sides to see the input unaltered. Normalising could also mask a
real difference between them.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

__all__ = ["CanonicalisationError", "canonical_hash", "canonical_json", "canonical_text"]


class CanonicalisationError(ValueError):
    """A value cannot be serialised deterministically."""


_ALLOWED_SCALARS = (str, bool, int, float, type(None))


def _check(value: Any, path: str = "$") -> None:
    """Reject anything that cannot be rendered deterministically, with a usable path."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalisationError(
                f"{path}: {value!r} is not representable in JSON. "
                "Non-finite floats have no canonical form."
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalisationError(
                    f"{path}: object keys must be strings, got {type(key).__name__} "
                    f"({key!r}). Non-string keys collide once coerced."
                )
            _check(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return

    raise CanonicalisationError(
        f"{path}: {type(value).__name__} has no canonical JSON form. "
        "Convert it explicitly before serialising."
    )


def canonical_text(value: Any) -> str:
    """Canonical JSON as ``str``. Prefer :func:`canonical_json` for hashing."""
    _check(value)
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def canonical_json(value: Any) -> bytes:
    """Canonical JSON as UTF-8 bytes. This is the form that gets hashed or signed."""
    return canonical_text(value).encode("utf-8")


def canonical_hash(value: Any) -> str:
    """SHA-256 of the canonical form, hex encoded."""
    return hashlib.sha256(canonical_json(value)).hexdigest()
