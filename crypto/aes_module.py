"""
SafeRelief - AES-256-GCM Module

Modul untuk enkripsi/dekripsi dengan AES-256-GCM.
Digunakan untuk enkripsi kolom database sensitif dan payload steganografi.

Kenapa AES-256-GCM:
- Authenticated Encryption with Associated Data (AEAD)
- Otomatis verifikasi integritas (built-in MAC)
- Standar industri untuk data at-rest
- GCM mode lebih efisien dari CBC untuk random access

Format output: nonce(12 bytes) + ciphertext + tag(16 bytes)
Total overhead: 28 bytes per data terenkripsi
"""

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import os
import config


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Enkripsi data dengan AES-256-GCM.
    
    Proses:
    1. Generate nonce acak 12 bytes
    2. Enkripsi dengan AESGCM
    3. Return: nonce + ciphertext + tag (tag sudah include di output AESGCM)
    
    Args:
        plaintext: Data asli (bytes)
        key: Kunci AES 32 bytes (256-bit)
    
    Returns:
        nonce + ciphertext + tag (total: len(plaintext) + 28 bytes)
    
    Raises:
        ValueError: Jika key bukan 32 bytes
    """
    if len(key) != 32:
        raise ValueError("AES-256 memerlukan key 32 bytes")
    
    # Generate nonce acak
    nonce = os.urandom(config.AES_GCM_NONCE_LENGTH)  # 12 bytes
    
    # Enkripsi dengan AESGCM
    # AESGCM.encrypt() otomatis menambahkan tag 16 bytes di akhir ciphertext
    aesgcm = AESGCM(key)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, None)
    
    # Format: nonce + ciphertext + tag
    # (tag sudah termasuk dalam ciphertext_with_tag)
    return nonce + ciphertext_with_tag


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    Dekripsi data AES-256-GCM.
    
    Proses:
    1. Ekstrak nonce (12 bytes pertama)
    2. Ekstrak ciphertext + tag (sisanya)
    3. Dekripsi dan verifikasi tag otomatis
    
    Args:
        data: Output dari encrypt() (nonce + ciphertext + tag)
        key: Kunci AES 32 bytes yang sama dengan saat enkripsi
    
    Returns:
        Plaintext (bytes)
    
    Raises:
        ValueError: Jika key bukan 32 bytes atau data terlalu pendek
        cryptography.exceptions.InvalidTag: Jika data rusak atau key salah
    
    Note:
        InvalidTag berarti:
        - Data telah dimodifikasi (tampered)
        - Key salah
        - Nonce/ciphertext corrupt
    """
    if len(key) != 32:
        raise ValueError("AES-256 memerlukan key 32 bytes")
    
    # Minimal: nonce(12) + tag(16) = 28 bytes
    if len(data) < 28:
        raise ValueError("Data terlalu pendek untuk AES-GCM (minimal 28 bytes)")
    
    # Parse: nonce + ciphertext + tag
    nonce = data[:config.AES_GCM_NONCE_LENGTH]  # 12 bytes
    ciphertext_with_tag = data[config.AES_GCM_NONCE_LENGTH:]
    
    # Dekripsi dan verifikasi tag
    # Jika tag tidak cocok, akan raise InvalidTag
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    
    return plaintext
