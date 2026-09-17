"""HMAC-SHA256 interim signer. Secret never appears in ``repr`` (I-8)."""

from __future__ import annotations

import hmac
from hashlib import sha256

__all__ = ["HmacSigner"]


class HmacSigner:
    """Per-tenant HMAC key. Console 0019's ``hmac_secret``, injected, not stored."""

    __slots__ = ("_secret", "key_id")

    def __init__(self, key_id: str, secret: bytes) -> None:
        if not key_id or not key_id.strip():
            raise ValueError("key_id is required and may not be blank")
        if len(secret) < 32:
            raise ValueError("HMAC secret must be at least 32 bytes")
        self.key_id = key_id
        self._secret = secret

    def sign(self, entry_hash: str) -> str:
        return hmac.new(self._secret, entry_hash.encode("utf-8"), sha256).hexdigest()

    def verify_signature(self, entry_hash: str, signature: str) -> bool:
        expected = self.sign(entry_hash)
        return hmac.compare_digest(expected, signature)

    def __repr__(self) -> str:
        return f"HmacSigner(key_id={self.key_id!r})"
