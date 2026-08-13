"""I-7: a consumer built for v1 must not crash on a v2 message."""

import pytest

from pil_contracts import CURRENT_SCHEMA_VERSION, UNKNOWN_VERSION, SchemaVersion


def test_current_version_is_known():
    assert CURRENT_SCHEMA_VERSION.is_known
    assert str(CURRENT_SCHEMA_VERSION) == "1.0"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", SchemaVersion(1, 0)),
        ("1.0", SchemaVersion(1, 0)),
        ("2.7", SchemaVersion(2, 7)),
        (" 1.2 ", SchemaVersion(1, 2)),
        (1, SchemaVersion(1, 0)),
    ],
)
def test_parse_accepts_reasonable_forms(raw, expected):
    assert SchemaVersion.parse(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "  ", "banana", "x.y", "-1", {}, [], "1.x.y.z"])
def test_parse_is_total_and_never_raises(raw):
    """A consumer that blows up on a malformed version string is the crash I-7 forbids."""
    result = SchemaVersion.parse(raw)
    assert isinstance(result, SchemaVersion)


def test_unparseable_becomes_unknown_not_an_exception():
    assert SchemaVersion.parse("banana") == UNKNOWN_VERSION
    assert not SchemaVersion.parse("banana").is_known


def test_partial_parse_keeps_the_major_it_could_read():
    assert SchemaVersion.parse("1.x") == SchemaVersion(1, 0)


def test_same_major_is_compatible_in_both_directions():
    old, new = SchemaVersion(1, 0), SchemaVersion(1, 9)
    assert new.is_compatible_with(old), "additions within a major must be ignorable"
    assert old.is_compatible_with(new), "everything added since was optional"


def test_different_major_is_not_compatible():
    assert not SchemaVersion(2, 0).is_compatible_with(SchemaVersion(1, 0))


def test_newer_major_is_reported_not_rejected():
    """The library flags it; the consumer decides. PIL never drops a message itself."""
    assert SchemaVersion(2, 0).is_newer_major_than(SchemaVersion(1, 0))
    assert not SchemaVersion(1, 0).is_newer_major_than(SchemaVersion(1, 0))
    assert not SchemaVersion(1, 0).is_newer_major_than(SchemaVersion(2, 0))


def test_unknown_version_is_never_newer():
    assert not UNKNOWN_VERSION.is_newer_major_than(CURRENT_SCHEMA_VERSION)
    assert not UNKNOWN_VERSION.is_compatible_with(CURRENT_SCHEMA_VERSION)
