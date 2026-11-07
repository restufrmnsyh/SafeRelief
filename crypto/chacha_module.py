"""
SafeRelief - ChaCha20-Poly1305 Module

Enkripsi file dengan ChaCha20-Poly1305 (AEAD cipher modern).
Digunakan untuk file laporan yang diunggah relawan.

Kenapa ChaCha20-Poly1305:
- AEAD (Authenticated Encryption with Associated Data)
- Lebih cepat dari AES di perangkat tanpa hardware AES acceleration
- Standar modern (TLS 1.3, WireGuard, Signal)
- Poly1305 MAC built-in untuk integritas
- Nonce 12 bytes seperti AES-GCM

Format output: nonce(12) + ciphertext + tag(16)
Sama dengan AES-GCM untuk konsistensi.
"""

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
import os
import config


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """
    Enkripsi data dengan ChaCha20-Poly1305.
    
    Proses:
    1. Generate nonce acak 12 bytes
    2. Enkripsi dengan ChaCha20Poly1305
    3. Return: nonce + ciphertext + tag
    
    Args:
        plaintext: Data asli (bytes)
        key: Kunci ChaCha20 32 bytes (256-bit)
    
    Returns:
        nonce(12) + ciphertext + tag(16)
    
    Raises:
        ValueError: Jika key bukan 32 bytes
    """
    if len(key) != 32:
        raise ValueError("ChaCha20-Poly1305 memerlukan key 32 bytes")
    
    # Generate nonce acak
    nonce = os.urandom(config.CHACHA20_NONCE_LENGTH)  # 12 bytes
    
    # Enkripsi dengan ChaCha20Poly1305
    # Tag 16 bytes otomatis ditambahkan di akhir ciphertext
    cipher = ChaCha20Poly1305(key)
    ciphertext_with_tag = cipher.encrypt(nonce, plaintext, None)
    
    # Format: nonce + ciphertext + tag
    return nonce + ciphertext_with_tag


def decrypt(data: bytes, key: bytes) -> bytes:
    """
    Dekripsi data ChaCha20-Poly1305.
    
    Proses:
    1. Ekstrak nonce (12 bytes pertama)
    2. Ekstrak ciphertext + tag (sisanya)
    3. Dekripsi dan verifikasi tag otomatis
    
    Args:
        data: Output dari encrypt() (nonce + ciphertext + tag)
        key: Kunci ChaCha20 32 bytes yang sama dengan saat enkripsi
    
    Returns:
        Plaintext (bytes)
    
    Raises:
        ValueError: Jika key bukan 32 bytes atau data terlalu pendek
        cryptography.exceptions.InvalidTag: Jika data rusak atau key salah
    """
    if len(key) != 32:
        raise ValueError("ChaCha20-Poly1305 memerlukan key 32 bytes")
    
    # Minimal: nonce(12) + tag(16) = 28 bytes
    if len(data) < 28:
        raise ValueError("Data terlalu pendek untuk ChaCha20-Poly1305 (minimal 28 bytes)")
    
    # Parse: nonce + ciphertext + tag
    nonce = data[:config.CHACHA20_NONCE_LENGTH]  # 12 bytes
    ciphertext_with_tag = data[config.CHACHA20_NONCE_LENGTH:]
    
    # Dekripsi dan verifikasi tag
    cipher = ChaCha20Poly1305(key)
    plaintext = cipher.decrypt(nonce, ciphertext_with_tag, None)
    
    return plaintext


def encrypt_file(input_path: str, output_path: str, key: bytes) -> None:
    """
    Enkripsi file ke file .enc.
    
    Proses:
    1. Baca file input
    2. Enkripsi dengan encrypt()
    3. Tulis ke output_path
    
    Args:
        input_path: Path file asli
        output_path: Path file terenkripsi (biasanya .enc)
        key: Kunci 32 bytes
    
    Raises:
        FileNotFoundError: Jika input_path tidak ada
        ValueError: Jika key tidak valid
    
    Note:
        Untuk file besar (>100MB), pertimbangkan streaming encryption.
        Implementasi ini membaca seluruh file ke memory (sederhana untuk demo).
    """
    with open(input_path, 'rb') as f:
        plaintext = f.read()
    
    ciphertext = encrypt(plaintext, key)
    
    with open(output_path, 'wb') as f:
        f.write(ciphertext)


def decrypt_file(input_path: str, output_path: str, key: bytes) -> None:
    """
    Dekripsi file .enc ke file asli.
    
    Proses:
    1. Baca file .enc
    2. Dekripsi dengan decrypt()
    3. Tulis ke output_path
    
    Args:
        input_path: Path file terenkripsi (.enc)
        output_path: Path file hasil dekripsi
        key: Kunci 32 bytes yang sama dengan saat enkripsi
    
    Raises:
        FileNotFoundError: Jika input_path tidak ada
        ValueError: Jika key tidak valid atau file corrupt
        cryptography.exceptions.InvalidTag: Jika file rusak atau key salah
    """
    with open(input_path, 'rb') as f:
        ciphertext = f.read()
    
    plaintext = decrypt(ciphertext, key)
    
    with open(output_path, 'wb') as f:
        f.write(plaintext)
