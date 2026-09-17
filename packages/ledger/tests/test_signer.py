"""HmacSigner — length floor, compare_digest, secret stays out of repr."""

from __future__ import annotations

import pytest

from pil_ledger.signer import HmacSigner


def test_secret_shorter_than_32_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="32"):
        HmacSigner("k", b"too-short")


def test_blank_key_id_rejected() -> None:
    with pytest.raises(ValueError, match="key_id"):
        HmacSigner("  ", b"a" * 32)


def test_repr_does_not_contain_the_secret() -> None:
    secret = b"super-secret-bytes-not-in-repr!!"
    signer = HmacSigner("tenant-hmac-1", secret)
    text = repr(signer)
    assert "tenant-hmac-1" in text
    assert "super-secret" not in text
    assert secret.decode("ascii") not in text


def test_verify_signature_rejects_a_bit_flip() -> None:
    signer = HmacSigner("k", b"a" * 32)
    sig = signer.sign("abc")
    flipped = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert not signer.verify_signature("abc", flipped)
    assert signer.verify_signature("abc", sig)
