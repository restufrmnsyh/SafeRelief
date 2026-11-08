"""Vernam XOR encryption with an HKDF-SHA256 keystream and HMAC-SHA256.

This is not a pure one-time pad and does not provide perfect secrecy: the
keystream is derived from a key with HKDF rather than being truly random and
pre-shared. A fresh nonce is mandatory for each message because reusing a
keystream enables a two-time-pad attack. HMAC is also mandatory because
unauthenticated XOR ciphertext can be modified by flipping selected bits.
The maximum message size is 8160 bytes, HKDF-SHA256's 255 * 32-byte limit.

Blob format: nonce(16) + ciphertext(same size as plaintext) + HMAC(32).
"""

import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import config


def _validate_keys(enc_key: bytes, mac_key: bytes) -> None:
    """Require 32-byte keys for keystream derivation and authentication."""
    if len(enc_key) != 32:
        raise ValueError("Vernam encryption key harus 32 bytes.")
    if len(mac_key) != 32:
        raise ValueError("HMAC key harus 32 bytes.")


def encrypt(plaintext: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    """XOR plaintext with a fresh HKDF keystream and authenticate the result."""
    _validate_keys(enc_key, mac_key)
    if not plaintext:
        raise ValueError("Plaintext tidak boleh kosong.")
    if len(plaintext) > config.VERNAM_MAX_MESSAGE_BYTES:
        raise ValueError(
            "Plaintext melebihi batas 8160 byte dari HKDF-SHA256 "
            "(255 * 32 byte)."
        )

    nonce = os.urandom(config.VERNAM_NONCE_LENGTH)
    keystream = HKDF(
        algorithm=hashes.SHA256(),
        length=len(plaintext),
        salt=nonce,
        info=b"vernam",
    ).derive(enc_key)
    ciphertext = bytes(p ^ k for p, k in zip(plaintext, keystream))
    mac = hmac.new(mac_key, nonce + ciphertext, hashlib.sha256).digest()
    return nonce + ciphertext + mac


def decrypt(data: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    """Authenticate a Vernam blob before deriving its keystream and decrypting."""
    _validate_keys(enc_key, mac_key)
    minimum_length = (
        config.VERNAM_NONCE_LENGTH + config.HMAC_SHA256_LENGTH
    )
    if len(data) < minimum_length:
        raise ValueError(
            "Data Vernam terlalu pendek (minimal 48 byte: nonce + HMAC)."
        )

    nonce = data[:config.VERNAM_NONCE_LENGTH]
    ciphertext = data[
        config.VERNAM_NONCE_LENGTH:-config.HMAC_SHA256_LENGTH
    ]
    mac_received = data[-config.HMAC_SHA256_LENGTH:]
    mac_calculated = hmac.new(
        mac_key, nonce + ciphertext, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(mac_calculated, mac_received):
        raise ValueError("HMAC verification failed")

    if len(ciphertext) > config.VERNAM_MAX_MESSAGE_BYTES:
        raise ValueError(
            "Ciphertext melebihi batas 8160 byte dari HKDF-SHA256 "
            "(255 * 32 byte)."
        )

    keystream = HKDF(
        algorithm=hashes.SHA256(),
        length=len(ciphertext),
        salt=nonce,
        info=b"vernam",
    ).derive(enc_key)
    return bytes(c ^ k for c, k in zip(ciphertext, keystream))
