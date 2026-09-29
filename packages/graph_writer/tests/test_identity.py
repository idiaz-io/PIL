"""node_id_for's collision-safety, checked structurally -- not against today's six
translator names, but against arbitrary source strings, so a seventh translator with a
different prefixing convention can't quietly reintroduce the bug this module exists to
close.
"""

from __future__ import annotations

import pytest

from pil_graph_writer.identity import is_missing_alert_id, node_id_for

#: Deliberately not pil_adapters.TRANSLATOR_TYPES. The property under test must hold for
#: any source string, including ones that don't exist yet -- pinning it to today's
#: registry would only prove it holds for translators already known to behave.
SOURCES = ["fleet", "connectwise", "sciencelogic", "sl1", "addigy", "legacy", "some-future-source"]

#: Raw ids designed to be adversarial against a "strip the prefix if already present"
#: rule specifically -- each one is crafted to look like it was already scoped for some
#: OTHER source, or for its own.
RAW_IDS = [
    "abc123",
    "unknown",
    "",
    "fleet:abc123",
    "connectwise:abc123",
    "sciencelogic:foo",
    "some-future-source:bar",
]


@pytest.mark.parametrize("raw_id", RAW_IDS)
def test_no_two_distinct_sources_collide_on_the_same_raw_id(raw_id):
    """The property addition asked for, checked exhaustively over all source pairs."""
    computed = {source: node_id_for(source, raw_id) for source in SOURCES}
    assert len(set(computed.values())) == len(SOURCES), (
        f"raw_id={raw_id!r} collided across sources: {computed}"
    )


def test_the_specific_collision_a_strip_the_prefix_rule_would_miss():
    """sciencelogic does not self-prefix its own device ids (unlike fleet/addigy/sl1). A
    'strip an existing prefix' rule would treat 'sciencelogic:foo' as already-scoped and
    leave it alone, while 'foo' from the same source gets prefixed to the exact same
    string -- two different raw ids from ONE source silently colliding. Unconditional
    prefixing has no such failure mode: the two stay distinct because they're already
    different strings before the source is ever prepended.
    """
    assert node_id_for("sciencelogic", "sciencelogic:foo") != node_id_for("sciencelogic", "foo")


def test_same_source_same_raw_id_is_stable():
    """The whole point of a MERGE key: the same input always produces the same output."""
    assert node_id_for("fleet", "abc123") == node_id_for("fleet", "abc123")


def test_source_already_self_prefixing_is_double_scoped_not_specially_handled():
    """fleet already prefixes its own device_id ("fleet:uuid"). node_id_for does not
    detect or strip this -- the result is cosmetically redundant, not incorrect."""
    assert node_id_for("fleet", "fleet:abc123") == "fleet:fleet:abc123"


@pytest.mark.parametrize("sentinel", ["unknown"])
def test_known_missing_alert_id_sentinels_are_recognised(sentinel):
    assert is_missing_alert_id(sentinel) is True


@pytest.mark.parametrize("real_id", ["12345", "fleet-policy-x-abcd1234", "e-9", "a1"])
def test_a_real_alert_id_is_not_mistaken_for_missing(real_id):
    assert is_missing_alert_id(real_id) is False
