"""Super encryption for chat: Vigenere followed by Vernam and HMAC.

Encryption applies Vigenere to the text, then authenticates and encrypts the
UTF-8 bytes with the HKDF-backed Vernam module. Decryption reverses that order.
The Vernam layer is a pseudo-random keystream construction, not a pure OTP.
"""

from . import vernam_module, vigenere


def encrypt(
    plaintext: str,
    vigenere_key: str,
    vernam_enc_key: bytes,
    vernam_mac_key: bytes,
) -> bytes:
    """Encrypt text with Vigenere then Vernam+HMAC."""
    if not plaintext:
        raise ValueError("Plaintext tidak boleh kosong")

    vigenere_ciphertext = vigenere.encrypt(plaintext, vigenere_key)
    vigenere_bytes = vigenere_ciphertext.encode("utf-8")
    return vernam_module.encrypt(
        vigenere_bytes, vernam_enc_key, vernam_mac_key
    )


def decrypt(
    ciphertext: bytes,
    vigenere_key: str,
    vernam_enc_key: bytes,
    vernam_mac_key: bytes,
) -> str:
    """Verify/decrypt Vernam ciphertext, then decrypt the Vigenere layer."""
    vigenere_bytes = vernam_module.decrypt(
        ciphertext, vernam_enc_key, vernam_mac_key
    )
    try:
        vigenere_ciphertext = vigenere_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Gagal decode UTF-8: data corrupt atau key salah"
        ) from exc
    return vigenere.decrypt(vigenere_ciphertext, vigenere_key)
