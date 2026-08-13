"""I-9: anything that will later be hashed or signed must serialise byte-identically.

These tests are the specification. If one of them has to change, every signature
written before the change is invalidated — so changing one is an ADR, not a fix.
"""

import pytest

from pil_contracts import CanonicalisationError, canonical_hash, canonical_json, canonical_text


def test_keys_are_sorted_regardless_of_insertion_order():
    a = canonical_json({"b": 1, "a": 2, "c": 3})
    b = canonical_json({"c": 3, "a": 2, "b": 1})
    assert a == b == b'{"a":2,"b":1,"c":3}'


def test_nested_keys_are_sorted_too():
    out = canonical_text({"z": {"b": 1, "a": 2}, "a": [{"y": 1, "x": 2}]})
    assert out == '{"a":[{"x":2,"y":1}],"z":{"a":2,"b":1}}'


def test_no_insignificant_whitespace():
    out = canonical_text({"a": 1, "b": [1, 2]})
    assert " " not in out


def test_non_ascii_is_emitted_literally_not_escaped():
    out = canonical_json({"name": "Ünïcodé — 日本語"})
    assert "\\u" not in out.decode("utf-8")
    assert "日本語".encode() in out


def test_output_is_utf8_bytes():
    assert isinstance(canonical_json({"a": "é"}), bytes)


def test_repeated_serialisation_is_byte_stable():
    payload = {"z": [3, 2, 1], "a": {"nested": {"deep": "é"}}, "n": 1.5, "t": True, "x": None}
    first = canonical_json(payload)
    for _ in range(50):
        assert canonical_json(payload) == first


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_rejected(value):
    with pytest.raises(CanonicalisationError, match="not representable"):
        canonical_json({"v": value})


def test_non_string_keys_are_rejected():
    """Python would coerce 1 and "1" to the same JSON key and silently drop one."""
    with pytest.raises(CanonicalisationError, match="must be strings"):
        canonical_json({1: "a", "1": "b"})


def test_unsupported_types_are_rejected_rather_than_stringified():
    from datetime import datetime

    with pytest.raises(CanonicalisationError, match="no canonical JSON form"):
        canonical_json({"when": datetime(2026, 1, 1)})


def test_error_message_points_at_the_offending_path():
    with pytest.raises(CanonicalisationError, match=r"\$\.a\[1\]\.b"):
        canonical_json({"a": [{}, {"b": float("nan")}]})


def test_bools_are_not_treated_as_ints():
    assert canonical_text({"a": True, "b": 1}) == '{"a":true,"b":1}'


def test_empty_and_null_are_distinct():
    assert canonical_json({"a": ""}) != canonical_json({"a": None})


def test_hash_is_stable_and_order_independent():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
