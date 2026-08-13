"""Where a translated message goes. IDI-195 D4.

D4 cut the bus and the capability catalogue — both had zero consumers — and replaced them
with one sentence: "For Phase A, a translated message goes to a simple sink behind an
interface — a table or an in-process handoff. Not a message broker."

This is that interface, and the deliberately boring implementations of it.

**What a sink is not.** Not a queue, not a broker, not a retry mechanism, not a place
messages accumulate. :meth:`Sink.emit` hands one envelope to whatever is next and returns.
If it raises, it raises to the caller — a sink that swallowed failures would turn a
delivery problem into silent data loss, and AXO already has a queue for the cases that
need one.

The reason this is an interface rather than a function is the same reason D4 gave for
cutting the bus: nobody knows yet what the second implementation is. An interface with two
trivial implementations costs nothing and means the third one is not a refactor.

**Redaction happens here, not in the translator.** This is the emit boundary, and it is
where :meth:`~pil_contracts.Envelope.redacted` belongs (D1). Doing it in ``translate()``
would break parity with AXO, which stores the vendor payload untouched, and would smuggle a
behaviour improvement into a migration — the thing I-10 forbids.

:class:`RedactingSink` therefore wraps another sink rather than being a mode of it. During
the migration nothing wraps anything and output stays byte-identical to AXO's; once the
cutover is done, wrapping the real sink is a one-line change at the call site rather than an
edit to any translator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from pil_contracts import Classification, Envelope

__all__ = ["CollectingSink", "NullSink", "RedactingSink", "Sink"]


class Sink(ABC):
    """Where a translated message goes next.

    Deliberately not ``async``. Phase A's implementations are an in-memory append and a
    no-op, and colouring the whole call graph for them would mean every caller becomes a
    coroutine to satisfy an interface that does no I/O. A sink that genuinely needs to
    await gets an async sibling and its own ADR.
    """

    @abstractmethod
    def emit(self, envelope: Envelope) -> None:
        """Hand one envelope onward.

        Raises on failure rather than swallowing. A sink that absorbed its own errors would
        convert a delivery failure into silent data loss, and the caller is the only code
        that knows whether the payload can be re-derived.
        """

    def emit_all(self, envelopes: Iterable[Envelope]) -> None:
        """Emit several, in order, stopping at the first failure.

        Not a transaction and not a batch: if the third of five fails, the first two have
        been emitted and the last two have not. Anything stronger is a store's job, and
        pretending otherwise here would be the beginning of the broker D4 cut.
        """
        for envelope in envelopes:
            self.emit(envelope)


class NullSink(Sink):
    """Discards everything. For tests, and for running a translator with nowhere to put
    the result.

    Named rather than anonymous so that a call site reads as a deliberate choice to throw
    the output away.
    """

    __slots__ = ()

    def emit(self, envelope: Envelope) -> None:
        return None

    def __repr__(self) -> str:
        return "NullSink()"


@dataclass(slots=True)
class CollectingSink(Sink):
    """Keeps every envelope in memory, in order. The in-process handoff D4 describes.

    Also the test double for anything that emits. Shipping it here is deliberate: the
    report-only section of IDI-195 warns that if PIL does not ship test doubles, each
    product writes its own and they drift, so tests pass while production fails.
    """

    envelopes: list[Envelope] = field(default_factory=list)

    def emit(self, envelope: Envelope) -> None:
        self.envelopes.append(envelope)

    def __len__(self) -> int:
        return len(self.envelopes)

    def for_tenant(self, tenant_id: str) -> Sequence[Envelope]:
        """Everything emitted for one tenant.

        Present because the assertion worth making in a multi-tenant test is usually "and
        nothing leaked into another tenant", which needs this to be easy to write.
        """
        return [e for e in self.envelopes if e.tenant_id == tenant_id]


@dataclass(slots=True)
class RedactingSink(Sink):
    """Strips credentials from each envelope before passing it to another sink.

    A wrapper rather than a flag on the others, so that "redacted" is visible at the call
    site that composes it:

        sink = RedactingSink(CollectingSink(), salt=capture_salt)

    ``salt`` additionally pseudonymises customer-identifying values, for a sink whose
    output leaves the tenant's own boundary — a fixture corpus, an export. A sink writing
    into a tenant-scoped store wants the real hostname and passes no salt.

    Credential stripping is not optional either way.
    """

    inner: Sink
    salt: bytes | None = None

    #: Paths at which a credential was found, accumulated across every emit. Worth
    #: keeping: a vendor payload carrying a credential usually means the integration is
    #: configured to send more than it should, and that is a finding rather than a nuisance.
    secrets_seen: list[str] = field(default_factory=list)

    def emit(self, envelope: Envelope) -> None:
        clean, result = envelope.redacted(salt=self.salt)
        self.secrets_seen.extend(
            path for path, mark in result.marks.items() if mark is Classification.SECRET
        )
        self.inner.emit(clean)

    @property
    def stripped_any_credentials(self) -> bool:
        return bool(self.secrets_seen)
