"""Encryption at rest: AES-256-GCM with a separate key per dataset.

  master key (32 bytes, from GG_MASTER_KEY, base64)  --HKDF-SHA256(info=dataset_id)-->  dataset key

Every ciphertext is bound to its context through GCM "associated data" (dataset id + record id),
so a blob copied to another donor or dataset fails to decrypt instead of silently decrypting.
Layout of a stored blob: 12-byte random nonce || ciphertext+tag.

Honest limits: the master key lives in an environment variable here; a real deployment would hold
it in a KMS/HSM and rotate it. Encryption at rest protects a stolen database file or backup, not a
compromised application process (that is what the consent/risk/audit layers are for). TLS for data
in transit is provided by the hosting platform at deploy time, not by this module.
"""

from __future__ import annotations

import base64
import os
import warnings

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

NONCE_LEN = 12
_DEV_MARKER = b"genomeguard-INSECURE-dev-master-key"


class DecryptionError(Exception):
    """Wrong key, wrong context (dataset/record), or the ciphertext was modified."""


def load_master_key(value: str | None) -> bytes:
    """Decode a base64 32-byte master key. If none is configured, fall back to a fixed,
    publicly-known development key and warn loudly (never use that for real data)."""
    if not value:
        warnings.warn("GG_MASTER_KEY not set: using an INSECURE development key", stacklevel=2)
        return HKDF(hashes.SHA256(), 32, None, _DEV_MARKER).derive(_DEV_MARKER)
    key = base64.b64decode(value)
    if len(key) != 32:
        raise ValueError("GG_MASTER_KEY must decode to exactly 32 bytes (AES-256)")
    return key


def new_master_key() -> str:
    """Generate a fresh random master key, base64 encoded (for `export GG_MASTER_KEY=...`)."""
    return base64.b64encode(os.urandom(32)).decode()


def dataset_key(master: bytes, dataset_id: str) -> bytes:
    return HKDF(hashes.SHA256(), 32, None, b"genomeguard/dataset/" + dataset_id.encode()).derive(
        master
    )


def _aad(dataset_id: str, record_id: str | int) -> bytes:
    return f"{dataset_id}|{record_id}".encode()


def encrypt(master: bytes, dataset_id: str, record_id: str | int, plaintext: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    ct = AESGCM(dataset_key(master, dataset_id)).encrypt(
        nonce, plaintext, _aad(dataset_id, record_id)
    )
    return nonce + ct


def decrypt(master: bytes, dataset_id: str, record_id: str | int, blob: bytes) -> bytes:
    if len(blob) < NONCE_LEN + 16:
        raise DecryptionError("blob too short")
    nonce, ct = blob[:NONCE_LEN], blob[NONCE_LEN:]
    try:
        return AESGCM(dataset_key(master, dataset_id)).decrypt(
            nonce, ct, _aad(dataset_id, record_id)
        )
    except InvalidTag as e:
        raise DecryptionError("authentication failed") from e
