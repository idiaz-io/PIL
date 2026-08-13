"""pil_contracts — the shapes every MERP message takes.

Definitions only. No I/O, no runtime, no dependencies — not on anything else in this
repo, and not on anything outside the standard library either. QUILL takes this
distribution without adapters; keeping it dependency-free makes that a physical fact
rather than a promise.
"""

from pil_contracts.canonical import (
    CanonicalisationError,
    canonical_hash,
    canonical_json,
    canonical_text,
)
from pil_contracts.envelope import (
    AlertBody,
    Envelope,
    MessageKind,
    TenantHint,
    format_timestamp,
)
from pil_contracts.redaction import (
    REDACTED,
    Classification,
    Redaction,
    classify_key,
    redact,
    redact_text,
)
from pil_contracts.versioning import (
    CURRENT_SCHEMA_VERSION,
    UNKNOWN_VERSION,
    SchemaVersion,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "REDACTED",
    "UNKNOWN_VERSION",
    "AlertBody",
    "CanonicalisationError",
    "Classification",
    "Envelope",
    "MessageKind",
    "Redaction",
    "SchemaVersion",
    "TenantHint",
    "canonical_hash",
    "canonical_json",
    "canonical_text",
    "classify_key",
    "format_timestamp",
    "redact",
    "redact_text",
]
