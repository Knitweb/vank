"""Ed25519 signing and content-address helpers for Vank mint events."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

__all__ = [
    "KeyPair",
    "canonical_json",
    "content_hash",
    "generate_keypair",
    "public_key_from_private",
    "sign_payload",
    "verify_payload",
]


@dataclass(frozen=True)
class KeyPair:
    private_key: str
    public_key: str


def _b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64d(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def canonical_json(payload: Any) -> bytes:
    """Return canonical UTF-8 JSON bytes for signatures and CIDs."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def content_hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(payload)).hexdigest()


def generate_keypair() -> KeyPair:
    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return KeyPair(private_key=_b64e(private_raw), public_key=_b64e(public_raw))


def public_key_from_private(private_key: str) -> str:
    private = Ed25519PrivateKey.from_private_bytes(_b64d(private_key))
    public_raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return _b64e(public_raw)


def sign_payload(private_key: str, payload: Any) -> str:
    private = Ed25519PrivateKey.from_private_bytes(_b64d(private_key))
    return _b64e(private.sign(canonical_json(payload)))


def verify_payload(public_key: str, payload: Any, signature: str) -> bool:
    try:
        public = Ed25519PublicKey.from_public_bytes(_b64d(public_key))
        public.verify(_b64d(signature), canonical_json(payload))
        return True
    except (InvalidSignature, ValueError, binascii.Error):
        return False
