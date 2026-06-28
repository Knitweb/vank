"""
Encrypted local key-value store for FieldLedger.

NOTE: This module uses a SHA-256-based deterministic stream cipher (XOR keystream)
combined with HMAC-SHA256 for authentication and PBKDF2-HMAC-SHA256 for key
derivation. This is sufficient for LOCAL PRIVACY against casual access but is
NOT suitable for adversarial crypto contexts. For production deployments that
require proper authenticated encryption, install the `cryptography` package and
use `cryptography.fernet.Fernet` instead.

All crypto is implemented using Python 3.12+ stdlib only (hashlib, hmac, os,
json, base64 — no external dependencies).
"""

from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import os
import struct
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

__all__ = ["SecureStore", "VaultEntry"]

_PBKDF2_ITER = 480_000
_DK_LEN = 64  # 32 enc_key + 32 mac_key
_SALT_LEN = 16
_NONCE_LEN = 16


# ---------------------------------------------------------------------------
# Low-level primitives
# ---------------------------------------------------------------------------

def _derive_keys(password: str, salt: bytes) -> tuple[bytes, bytes]:
    """Derive enc_key (32 B) and mac_key (32 B) via PBKDF2-HMAC-SHA256."""
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt,
        _PBKDF2_ITER,
        dklen=_DK_LEN,
    )
    return dk[:32], dk[32:]


def _sha256_keystream(enc_key: bytes, nonce: bytes, length: int) -> bytes:
    """
    Produce `length` pseudo-random bytes using SHA-256 in counter mode.

    Each 32-byte block = SHA256(enc_key || nonce || block_index_4BE).
    """
    blocks = []
    n_blocks = (length + 31) // 32
    for i in range(n_blocks):
        counter = struct.pack(">I", i)
        blocks.append(hashlib.sha256(enc_key + nonce + counter).digest())
    return b"".join(blocks)[:length]


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _encrypt(enc_key: bytes, mac_key: bytes, salt: bytes, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt plaintext and return (nonce, ciphertext, hmac_tag).

    Encryption: XOR(plaintext, SHA256-keystream(enc_key, nonce))
    Authentication: HMAC-SHA256(mac_key, salt || nonce || ciphertext)
    """
    nonce = os.urandom(_NONCE_LEN)
    keystream = _sha256_keystream(enc_key, nonce, len(plaintext))
    ciphertext = _xor_bytes(plaintext, keystream)
    tag = _hmac.new(mac_key, salt + nonce + ciphertext, hashlib.sha256).digest()
    return nonce, ciphertext, tag


def _decrypt(enc_key: bytes, mac_key: bytes, salt: bytes,
             nonce: bytes, ciphertext: bytes, expected_tag: bytes) -> bytes:
    """
    Verify HMAC then decrypt. Raises ValueError on tag mismatch.
    """
    tag = _hmac.new(mac_key, salt + nonce + ciphertext, hashlib.sha256).digest()
    if not _hmac.compare_digest(tag, expected_tag):
        raise ValueError("HMAC verification failed — data may be corrupted or tampered")
    keystream = _sha256_keystream(enc_key, nonce, len(ciphertext))
    return _xor_bytes(ciphertext, keystream)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class VaultEntry:
    key: str
    ciphertext: str   # base64-encoded
    nonce: str        # base64-encoded
    salt: str         # base64-encoded (per-entry salt)
    hmac_tag: str     # base64-encoded
    metadata: dict = field(default_factory=dict)  # unencrypted — NO PII here

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VaultEntry":
        return cls(
            key=d["key"],
            ciphertext=d["ciphertext"],
            nonce=d["nonce"],
            salt=d["salt"],
            hmac_tag=d["hmac_tag"],
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# SecureStore
# ---------------------------------------------------------------------------

class SecureStore:
    """
    Encrypted local key-value store backed by a single JSON file.

    Keys are plain strings. Values are encrypted bytes. Each entry uses its
    own random salt, so the per-entry PBKDF2 cost is paid on every write.
    Reads re-derive keys per entry as well (lightweight for local use).

    Thread-safety: none — callers must synchronise externally if needed.
    """

    def __init__(self, path: str, password: str) -> None:
        """
        Parameters
        ----------
        path:
            Directory where ``store.json`` lives. Created if absent.
        password:
            User passphrase used for key derivation.
        """
        self._dir = Path(path)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._store_path = self._dir / "store.json"
        self._password = password
        self._entries: dict[str, VaultEntry] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._store_path.exists():
            return
        raw = self._store_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        self._entries = {
            k: VaultEntry.from_dict(v) for k, v in data.items()
        }

    def _save(self) -> None:
        data = {k: v.to_dict() for k, v in self._entries.items()}
        self._store_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def put(self, key: str, value: bytes, metadata: dict | None = None) -> None:
        """Encrypt and store *value* under *key*."""
        if not isinstance(value, bytes):
            raise TypeError(f"value must be bytes, got {type(value).__name__}")
        salt = os.urandom(_SALT_LEN)
        enc_key, mac_key = _derive_keys(self._password, salt)
        nonce, ciphertext, tag = _encrypt(enc_key, mac_key, salt, value)

        meta = {"stored_at": time.time()}
        if metadata:
            meta.update(metadata)

        self._entries[key] = VaultEntry(
            key=key,
            ciphertext=base64.b64encode(ciphertext).decode(),
            nonce=base64.b64encode(nonce).decode(),
            salt=base64.b64encode(salt).decode(),
            hmac_tag=base64.b64encode(tag).decode(),
            metadata=meta,
        )
        self._save()

    def get(self, key: str) -> bytes | None:
        """
        Decrypt and return the value for *key*, or ``None`` if not found.

        Raises ``ValueError`` if HMAC verification fails.
        """
        entry = self._entries.get(key)
        if entry is None:
            return None

        salt = base64.b64decode(entry.salt)
        nonce = base64.b64decode(entry.nonce)
        ciphertext = base64.b64decode(entry.ciphertext)
        tag = base64.b64decode(entry.hmac_tag)

        enc_key, mac_key = _derive_keys(self._password, salt)
        return _decrypt(enc_key, mac_key, salt, nonce, ciphertext, tag)

    def delete(self, key: str) -> bool:
        """Remove *key* from the store. Returns ``True`` if it existed."""
        if key not in self._entries:
            return False
        del self._entries[key]
        self._save()
        return True

    def keys(self) -> list[str]:
        """Return all stored keys (unencrypted key names)."""
        return list(self._entries.keys())

    def export_encrypted(self) -> dict:
        """
        Return the raw store dict with all values still encrypted.
        Safe to share or back up — no plaintext is exposed.
        """
        return {k: v.to_dict() for k, v in self._entries.items()}

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def put_json(self, key: str, obj: object, metadata: dict | None = None) -> None:
        """Serialise *obj* to JSON bytes, then encrypt and store."""
        value = json.dumps(obj, ensure_ascii=False).encode()
        self.put(key, value, metadata=metadata)

    def get_json(self, key: str) -> object | None:
        """Decrypt and deserialise the value for *key* as JSON, or ``None``."""
        raw = self.get(key)
        if raw is None:
            return None
        return json.loads(raw.decode())
