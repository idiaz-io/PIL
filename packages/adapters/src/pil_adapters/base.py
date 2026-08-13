"""The translator contract.

Phase A is translate-only (ADR-0005). A translator turns one vendor payload into one
:class:`~pil_contracts.Envelope`. It does not connect, execute, verify or retry.

The shape of this module is doing one job in particular: making I-5 impossible to break.
A subclass implements :meth:`Translator._translate` and returns a :class:`Translation`,
which **has no tenant field**. The base class assembles the envelope and is the only
place ``tenant_id`` is ever set, always from the adapter instance's own configuration.

A translator therefore cannot emit another tenant's identifier, because there is nowhere
for it to put one. That is stronger than a test — a test tells you afterwards, this does
not compile the mistake in the first place. The test in ``tests/test_invariants.py``
still exists, to catch anyone who bypasses the base class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from pil_adapters.clock import Clock, SystemClock
from pil_contracts import AlertBody, Envelope, TenantHint

__all__ = ["AdapterConfig", "Translation", "Translator"]


@dataclass(frozen=True, slots=True)
class AdapterConfig:
    """Configuration for one adapter instance.

    ``tenant_id`` is the authoritative tenant for everything this instance emits (I-5).
    For scheduled work there is no token to take it from, so it comes from here and
    nowhere else — never from a vendor payload.

    No credentials appear on this object. Phase A translates and nothing more, so there
    is nothing to authenticate to. When the connect surface arrives it brings a secret
    *handle* rather than a value (I-8), and its own ADR.
    """

    tenant_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.tenant_id.strip():
            raise ValueError(
                "AdapterConfig.tenant_id is required and may not be blank. I-5: an "
                "adapter instance may never emit a message for any tenant other than "
                "its configured one, so there is no sensible default."
            )


@dataclass(frozen=True, slots=True)
class Translation:
    """The vendor-specific part of a translation.

    Note what is *absent*: there is no tenant_id. That omission is the enforcement
    mechanism for I-5 and is not an oversight — do not add one.
    """

    event_id: str
    body: AlertBody
    occurred_at: datetime
    tenant_hint: TenantHint = field(default_factory=TenantHint)

    #: What to carry as ``raw_payload``, when it is not the payload as received.
    #:
    #: Exists for one reason: AXO's Fleet adapter rebinds ``raw`` to the first entry of
    #: ``failing_policies`` when unwrapping a batch, and then stores *that* as
    #: ``raw_payload`` rather than the envelope it arrived in
    #: (`fleet_healing_adapter.py:116-119,151`). Reproducing the migration faithfully
    #: means reproducing that, so the translator has to be able to say so.
    raw_payload_override: Mapping[str, Any] | None = None


class Translator(ABC):
    """Base for all translators.

    Subclasses set :attr:`source` and :attr:`adapter_version` and implement
    :meth:`_translate`.
    """

    #: Which vendor path this translates. Also the fixture directory name.
    source: ClassVar[str]

    #: Bumped when this translator's output changes for any input. Travels in the
    #: envelope so a consumer can tell which code produced a message.
    adapter_version: ClassVar[str]

    def __init__(self, config: AdapterConfig, clock: Clock | None = None) -> None:
        self._config = config
        self._clock: Clock = clock if clock is not None else SystemClock()

    @property
    def config(self) -> AdapterConfig:
        return self._config

    @property
    def tenant_id(self) -> str:
        return self._config.tenant_id

    def translate(self, raw: Mapping[str, Any]) -> Envelope:
        """Turn one vendor payload into an envelope.

        Deliberately not ``async``. AXO's ``normalize_alert`` methods are coroutines, but
        only because they sit on an interface whose other methods do I/O — the
        normalisation itself is pure. Translation in PIL does no I/O and should not
        pretend it might.
        """
        result = self._translate(raw)
        return Envelope(
            event_id=result.event_id,
            # The only assignment of tenant_id anywhere in this package.
            tenant_id=self._config.tenant_id,
            source=self.source,
            adapter_version=self.adapter_version,
            occurred_at=result.occurred_at,
            observed_at=self._clock.now(),
            body=result.body,
            tenant_hint=result.tenant_hint,
            raw_payload=dict(
                result.raw_payload_override if result.raw_payload_override is not None else raw
            ),
        )

    @abstractmethod
    def _translate(self, raw: Mapping[str, Any]) -> Translation:
        """Vendor-specific mapping. Must be pure and must not consult a clock directly.

        Use ``self._clock.now()`` where AXO's original reached for
        ``datetime.utcnow()`` — that is the only permitted source of the current time.
        """

    def __repr__(self) -> str:
        return f"{type(self).__name__}(source={self.source!r}, tenant_id={self.tenant_id!r})"
