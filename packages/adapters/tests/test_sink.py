"""The sink — IDI-195 D4.

D4 cut the bus and the capability catalogue and replaced them with "a translated message
goes to a simple sink behind an interface — a table or an in-process handoff. Not a message
broker."

So the tests that matter are the ones asserting it is *not* a broker
(:func:`test_a_failing_sink_raises_rather_than_swallowing`,
:func:`test_emit_all_is_not_a_transaction`) and that redaction happens here rather than in
the translator (:func:`test_translation_is_unredacted_until_a_sink_redacts_it`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pil_adapters import (
    AdapterConfig,
    CollectingSink,
    FrozenClock,
    NullSink,
    RedactingSink,
    Sink,
    get_translator,
)
from pil_contracts import REDACTED, AlertBody, Envelope

CLOCK = FrozenClock(datetime(2026, 3, 14, 15, 9, 26, 535897, tzinfo=UTC))


def envelope(tenant="tenant-acme", raw=None):
    return Envelope(
        event_id="e-1",
        tenant_id=tenant,
        source="sciencelogic",
        adapter_version="1.0.0",
        occurred_at=datetime(2026, 3, 14, tzinfo=UTC),
        observed_at=datetime(2026, 3, 14, tzinfo=UTC),
        body=AlertBody("a-1", "d-1", "db01", "P1", "service", "stopped"),
        raw_payload=raw or {},
    )


# ----------------------------------------------------------------------------------
# It is an interface, and it is not a broker
# ----------------------------------------------------------------------------------


def test_sink_is_an_interface():
    """D4 says "behind an interface". A single concrete class would not be one."""
    import inspect

    assert inspect.isabstract(Sink)
    with pytest.raises(TypeError):
        Sink()  # type: ignore[abstract]


def test_a_failing_sink_raises_rather_than_swallowing():
    """A sink that absorbed its own errors would turn delivery failure into data loss.

    Only the caller knows whether the payload can be re-derived, so only the caller can
    decide what to do about it.
    """

    class Broken(Sink):
        def emit(self, env):
            raise RuntimeError("downstream is down")

    with pytest.raises(RuntimeError, match="downstream is down"):
        Broken().emit(envelope())


def test_emit_all_is_not_a_transaction():
    """If the third of five fails, the first two are already emitted.

    Asserted explicitly because the tempting next step is to make it atomic, and that is
    the beginning of the broker D4 cut. Anything stronger belongs to a store.
    """
    collected = CollectingSink()

    class FailsOnThird(Sink):
        def __init__(self):
            self.count = 0

        def emit(self, env):
            self.count += 1
            if self.count == 3:
                raise RuntimeError("third one fails")
            collected.emit(env)

    with pytest.raises(RuntimeError):
        FailsOnThird().emit_all([envelope() for _ in range(5)])

    assert len(collected) == 2, "the two before the failure stay emitted"


def test_there_is_no_queue_or_retry_surface():
    """A sink has one method plus a convenience. Anything else is the bus coming back.

    D4: "Revisit when something actually needs a shared one." Until then, an `ack`,
    `retry`, `enqueue` or `subscribe` appearing here is the thing to catch in review.
    """
    surface = {name for name in dir(Sink) if not name.startswith("_")}
    assert surface == {"emit", "emit_all"}


def test_order_is_preserved():
    sink = CollectingSink()
    sink.emit_all([envelope() for _ in range(3)])
    assert len(sink) == 3


# ----------------------------------------------------------------------------------
# Implementations
# ----------------------------------------------------------------------------------


def test_null_sink_discards():
    NullSink().emit(envelope())  # no exception, nothing kept


def test_collecting_sink_can_be_asked_per_tenant():
    """The assertion worth making in a multi-tenant test is "nothing leaked"."""
    sink = CollectingSink()
    sink.emit(envelope(tenant="tenant-acme"))
    sink.emit(envelope(tenant="tenant-other"))

    assert len(sink.for_tenant("tenant-acme")) == 1
    assert len(sink.for_tenant("tenant-other")) == 1
    assert len(sink.for_tenant("tenant-absent")) == 0


# ----------------------------------------------------------------------------------
# Redaction at the emit boundary, not in the translator (D1 + D4)
# ----------------------------------------------------------------------------------


def test_redacting_sink_strips_before_passing_on():
    inner = CollectingSink()
    sink = RedactingSink(inner)

    sink.emit(envelope(raw={"password": "hunter2", "severity": "4"}))

    assert inner.envelopes[0].raw_payload == {"password": REDACTED, "severity": "4"}
    assert sink.stripped_any_credentials
    assert sink.secrets_seen == ["$.password"]


def test_redacting_sink_is_a_wrapper_not_a_mode():
    """ "Redacted" should be visible at the call site that composes it."""
    assert isinstance(RedactingSink(NullSink()), Sink)
    assert RedactingSink(NullSink()).inner.__class__ is NullSink


def test_a_salt_additionally_pseudonymises():
    """For a sink whose output leaves the tenant's boundary — a corpus, an export."""
    inner = CollectingSink()
    RedactingSink(inner, salt=b"a-salt").emit(envelope(raw={"hostname": "prod-db-01"}))
    assert inner.envelopes[0].raw_payload["hostname"].startswith("host-")


def test_without_a_salt_identifiers_survive_but_credentials_do_not():
    """A sink writing into a tenant-scoped store wants the real hostname.

    Credential stripping is not optional either way — that is the half that cannot be
    left to a caller's judgement.
    """
    inner = CollectingSink()
    RedactingSink(inner).emit(envelope(raw={"hostname": "prod-db-01", "token": "abc"}))

    assert inner.envelopes[0].raw_payload["hostname"] == "prod-db-01"
    assert inner.envelopes[0].raw_payload["token"] == REDACTED


def test_translation_is_unredacted_until_a_sink_redacts_it():
    """The guarantee that keeps parity honest.

    AXO stores raw_payload untouched. If translate() redacted, PIL would differ from AXO on
    every payload holding a credential — parity would fail, and it would look like a porting
    bug rather than the deliberate improvement it is. I-10.
    """
    translator = get_translator("sciencelogic", AdapterConfig(tenant_id="tenant-acme"), CLOCK)
    result = translator.translate({"id": "1", "message": "disk full", "password": "hunter2"})

    assert result.raw_payload["password"] == "hunter2", (
        "translate() must not redact — parity with AXO depends on it"
    )

    inner = CollectingSink()
    RedactingSink(inner).emit(result)
    assert inner.envelopes[0].raw_payload["password"] == REDACTED
