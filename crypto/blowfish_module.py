"""
SafeRelief - Blowfish-CBC + HMAC Module

Enkripsi chat dengan Blowfish-CBC + Encrypt-then-MAC (HMAC-SHA256).
Lapisan enkripsi modern (setelah Vigenère) dalam super enkripsi.

Kenapa Blowfish-CBC + HMAC:
- Blowfish cepat dan sudah teruji (meski block 64-bit)
- CBC mode untuk stream data chat
- HMAC-SHA256 untuk authenticated encryption (manual, bukan AEAD)
- Encrypt-then-MAC pattern: MAC dihitung atas ciphertext, lebih aman

Format output: IV(8) + ciphertext + HMAC(32)
Total overhead: 40 bytes + padding

Catatan keterbatasan: Blowfish block size 64-bit (bukan 128-bit seperti AES).
Untuk data >4GB dengan key sama, perlu rekey (tidak relevan untuk chat pendek).
"""

from Crypto.Cipher import Blowfish
from Crypto.Util.Padding import pad, unpad
import hmac
import hashlib
import os
import config


def encrypt(plaintext: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    """
    Enkripsi dengan Blowfish-CBC lalu tambahkan HMAC.
    
    Proses Encrypt-then-MAC:
    1. Generate IV acak 8 bytes (Blowfish block size)
    2. Pad plaintext dengan PKCS7 (block size 8)
    3. Enkripsi dengan Blowfish-CBC
    4. Hitung HMAC-SHA256 atas (IV + ciphertext)
    5. Return: IV + ciphertext + HMAC
    
    Args:
        plaintext: Data asli (bytes)
        enc_key: Kunci enkripsi Blowfish (32 bytes recommended)
        mac_key: Kunci HMAC (32 bytes recommended)
    
    Returns:
        IV(8) + ciphertext + HMAC(32)
    
    Raises:
        ValueError: Jika plaintext kosong atau key tidak valid
    
    Note:
        enc_key dan mac_key HARUS berbeda untuk keamanan.
        Gunakan HKDF dengan label berbeda untuk derive keduanya.
    """
    if not plaintext:
        raise ValueError("Plaintext tidak boleh kosong")
    
    if len(enc_key) < 4 or len(enc_key) > 56:
        raise ValueError("Blowfish key harus 4-56 bytes (recommended: 32)")
    
    if len(mac_key) < 16:
        raise ValueError("HMAC key minimal 16 bytes (recommended: 32)")
    
    # 1. Generate IV acak (8 bytes untuk Blowfish)
    iv = os.urandom(config.BLOWFISH_IV_LENGTH)  # 8 bytes
    
    # 2. Pad plaintext ke kelipatan 8 bytes (PKCS7)
    padded_plaintext = pad(plaintext, Blowfish.block_size)  # block_size = 8
    
    # 3. Enkripsi dengan Blowfish-CBC
    cipher = Blowfish.new(enc_key, Blowfish.MODE_CBC, iv)
    ciphertext = cipher.encrypt(padded_plaintext)
    
    # 4. Hitung HMAC atas (IV + ciphertext)
    # Kenapa IV di-MAC: mencegah IV manipulation attacks
    data_to_mac = iv + ciphertext
    mac = hmac.new(mac_key, data_to_mac, hashlib.sha256).digest()  # 32 bytes
    
    # 5. Return: IV + ciphertext + HMAC
    return iv + ciphertext + mac


def decrypt(data: bytes, enc_key: bytes, mac_key: bytes) -> bytes:
    """
    Verifikasi HMAC lalu dekripsi Blowfish-CBC.
    
    Proses (kebalikan encrypt):
    1. Parse: IV(8) + ciphertext + HMAC(32)
    2. Verifikasi HMAC (timing-safe comparison)
    3. Dekripsi dengan Blowfish-CBC
    4. Unpad PKCS7
    5. Return plaintext
    
    Args:
        data: Output dari encrypt() (IV + ciphertext + HMAC)
        enc_key: Kunci enkripsi (sama dengan saat encrypt)
        mac_key: Kunci HMAC (sama dengan saat encrypt)
    
    Returns:
        Plaintext (bytes)
    
    Raises:
        ValueError: Jika data terlalu pendek, HMAC tidak cocok, atau padding invalid
    
    Note:
        HMAC HARUS diverifikasi SEBELUM dekripsi (Encrypt-then-MAC).
        Ini mencegah padding oracle attacks.
    """
    if len(enc_key) < 4 or len(enc_key) > 56:
        raise ValueError("Blowfish key harus 4-56 bytes")
    
    if len(mac_key) < 16:
        raise ValueError("HMAC key minimal 16 bytes")
    
    # Minimal: IV(8) + block(8) + HMAC(32) = 48 bytes
    min_length = config.BLOWFISH_IV_LENGTH + Blowfish.block_size + config.HMAC_SHA256_LENGTH
    if len(data) < min_length:
        raise ValueError(f"Data terlalu pendek untuk Blowfish-CBC+HMAC (minimal {min_length} bytes)")
    
    # 1. Parse: IV + ciphertext + HMAC
    iv = data[:config.BLOWFISH_IV_LENGTH]  # 8 bytes
    mac_received = data[-config.HMAC_SHA256_LENGTH:]  # 32 bytes terakhir
    ciphertext = data[config.BLOWFISH_IV_LENGTH:-config.HMAC_SHA256_LENGTH]
    
    # 2. Verifikasi HMAC (timing-safe)
    data_to_mac = iv + ciphertext
    mac_calculated = hmac.new(mac_key, data_to_mac, hashlib.sha256).digest()
    
    if not hmac.compare_digest(mac_calculated, mac_received):
        raise ValueError("HMAC verification failed: data rusak atau key salah")
    
    # 3. Dekripsi Blowfish-CBC
    cipher = Blowfish.new(enc_key, Blowfish.MODE_CBC, iv)
    padded_plaintext = cipher.decrypt(ciphertext)
    
    # 4. Unpad PKCS7
    try:
        plaintext = unpad(padded_plaintext, Blowfish.block_size)
    except ValueError as e:
        raise ValueError(f"Padding invalid: {e}")
    
    return plaintext
