"""Collision-safe identity keys for nodes derived from a translated Envelope.

:func:`pil_graph.operations.uid` MERGEs on a key scoped only by tenant — correct for a
node id already known to be unique within that tenant, which a raw vendor ``device_id`` or
``alert_id`` is not. Five of PIL's six translators fall back to a literal missing-value
sentinel (mostly the bare string ``"unknown"``) when the vendor payload doesn't identify a
device or alert, and three of those five (``sciencelogic``, ``connectwise``, ``legacy``)
use exactly the same bare spelling with no source prefix at all — so two different
translators' unidentified alerts would otherwise MERGE onto the very same graph node.

:func:`node_id_for` closes this the structural way: every raw id is unconditionally scoped
by its envelope's own ``source`` before it ever reaches :func:`~pil_graph.operations.uid`
— ``f"{source}:{raw_id}"``, no inspection of what ``raw_id`` looks like, no attempt to
detect whether a translator already added its own prefix. Two different ``source`` values
can never collide for the same ``raw_id``, because ``source`` is always the string's own
first colon-delimited segment.

This is strictly stronger than checking ``raw_id.startswith(f"{source}:")`` and skipping
the prefix when it matches. That check is fooled the moment a translator that does *not*
normally self-prefix (``sciencelogic``, ``connectwise``, ``legacy``) happens to receive a
vendor payload whose raw id coincidentally already looks like ``"<that same source>:
something"``: the "already prefixed" check leaves it alone, while a genuinely different raw
id from the same source, once prefixed, collides with it. Concretely: ``sciencelogic``
device ids ``"sciencelogic:foo"`` (an ordinary, if odd, vendor value — nothing prevents it)
and ``"foo"`` would both resolve to the node-id input ``"sciencelogic:foo"`` under a
strip-if-prefixed rule, silently merging two different devices. Unconditional prefixing
never has this failure mode — see ``test_identity.py`` for the constructed case.

The cost is cosmetic, not a correctness one: a translator that already self-prefixes
(``fleet``, ``addigy``, ``sl1``) ends up double-scoped, e.g. ``"fleet:fleet:abc123"``. An
ugly string, not a bug — still unconditionally unique, still unconditionally deterministic,
still reads back the same way on every MERGE.

**What this does not do**: correlate the same physical device across different vendors.
Nothing here decides that Fleet's ``host_uuid`` and ConnectWise's ``deviceId`` name the
same laptop — that's a separate, unbuilt identity-resolution component. ``external_ids`` on
the node (see ``project.py``) is where the raw per-source id is preserved as evidence, so
that resolution has something to work from later; this module only guarantees today's
writes don't collide with each other in the meantime.
"""

from __future__ import annotations

__all__ = ["MISSING_ALERT_ID_SENTINELS", "is_missing_alert_id", "node_id_for"]


def node_id_for(source: str, raw_id: str) -> str:
    """The collision-safe input to :func:`~pil_graph.operations.uid`'s ``node_id``.

    Unconditional: always ``f"{source}:{raw_id}"``. See the module docstring for why this
    must never try to detect or strip an existing prefix.
    """
    return f"{source}:{raw_id}"


#: Literal fallback values PIL's translators emit for ``AlertBody.alert_id`` when the
#: vendor payload carries nothing to identify the alert itself — confirmed directly
#: against every translator's source. Five of six fall back to the bare string
#: ``"unknown"``; Fleet's ``alert_id`` is always constructed from real components
#: (policy id/name, host uuid) and never reaches it.
#:
#: Not derivable structurally: nothing in ``Envelope``/``AlertBody`` records whether a
#: field was defaulted, so recognising "this alert has no real identity" means
#: recognising the literal sentinel a translator happens to emit today. A translator
#: changing its fallback spelling, or a future translator choosing a different one, needs
#: this set updated in the same reviewed change — the same category of coupling as the
#: closed ITKG vocabulary itself, not a one-time fix.
MISSING_ALERT_ID_SENTINELS = frozenset({"unknown"})


def is_missing_alert_id(alert_id: str) -> bool:
    """Whether ``alert_id`` is one of PIL's translators' known missing-value sentinels.

    Used to decide whether a Finding can be written at all (see ``project.py``) — unlike
    an unidentified *device*, where collapsing onto one per-source node is an accepted
    imprecision, two different *alerts* colliding onto one Finding node is data loss: the
    second ``MERGE`` silently overwrites the first. There is no synthetic identity (a
    timestamp, a content hash) that closes this without trading one correctness problem
    for another — a timestamp treats every re-poll of a still-failing condition as a new
    Finding; a content hash treats two genuinely different alerts with coincidentally
    identical text as the same one. Refusing to write is the only option that never
    fabricates a merge.
    """
    return alert_id in MISSING_ALERT_ID_SENTINELS
