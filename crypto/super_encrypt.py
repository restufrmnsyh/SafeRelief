"""
SafeRelief - Super Encryption Module

Super enkripsi untuk chat: Vigenère (klasik) + Blowfish-CBC + HMAC (modern).

Proses Enkripsi:
1. Vigenère: plaintext → vigenere_ciphertext
2. Blowfish-CBC + HMAC: vigenere_ciphertext → final_ciphertext

Proses Dekripsi:
1. Verifikasi HMAC + Blowfish-CBC: final_ciphertext → vigenere_ciphertext
2. Vigenère: vigenere_ciphertext → plaintext

Kenapa super enkripsi:
- Demonstrasi kombinasi algoritma klasik + modern (requirement tugas)
- Vigenère: lapisan historis/demonstrasi
- Blowfish + HMAC: keamanan sebenarnya (authenticated encryption)
- Encrypt-then-MAC: HMAC dihitung atas ciphertext Blowfish

Note:
- Keamanan sebenarnya bergantung pada Blowfish + HMAC
- Vigenère hanya lapisan tambahan untuk demonstrasi
"""

from . import vigenere
from . import blowfish_module


def encrypt(plaintext: str, vigenere_key: str, blowfish_enc_key: bytes, 
            blowfish_mac_key: bytes) -> bytes:
    """
    Enkripsi teks dengan super enkripsi Vigenère + Blowfish + HMAC.
    
    Proses:
    1. Enkripsi plaintext dengan Vigenère → intermediate ciphertext (string)
    2. Convert ke bytes (UTF-8)
    3. Enkripsi dengan Blowfish-CBC + HMAC → final ciphertext (bytes)
    
    Args:
        plaintext: Teks asli (string)
        vigenere_key: Kunci Vigenère (string, minimal 1 karakter)
        blowfish_enc_key: Kunci enkripsi Blowfish (32 bytes)
        blowfish_mac_key: Kunci HMAC (32 bytes, HARUS berbeda dari enc_key)
    
    Returns:
        Ciphertext final (bytes): IV(8) + ciphertext + HMAC(32)
    
    Raises:
        ValueError: Jika key tidak valid atau plaintext kosong
    
    Example:
        >>> ciphertext = encrypt("Hello", "KEY", enc_key, mac_key)
        >>> isinstance(ciphertext, bytes)
        True
    """
    if not plaintext:
        raise ValueError("Plaintext tidak boleh kosong")
    
    # Lapisan 1: Vigenère (klasik)
    vigenere_ciphertext = vigenere.encrypt(plaintext, vigenere_key)
    
    # Convert ke bytes untuk Blowfish
    vigenere_bytes = vigenere_ciphertext.encode('utf-8')
    
    # Lapisan 2: Blowfish-CBC + HMAC (modern)
    final_ciphertext = blowfish_module.encrypt(
        vigenere_bytes, 
        blowfish_enc_key, 
        blowfish_mac_key
    )
    
    return final_ciphertext


def decrypt(ciphertext: bytes, vigenere_key: str, blowfish_enc_key: bytes, 
            blowfish_mac_key: bytes) -> str:
    """
    Dekripsi super enkripsi (kebalikan encrypt).
    
    Proses:
    1. Verifikasi HMAC dan dekripsi Blowfish → intermediate bytes
    2. Convert bytes ke string (UTF-8)
    3. Dekripsi Vigenère → plaintext asli
    
    Args:
        ciphertext: Output dari encrypt() (IV + ciphertext + HMAC)
        vigenere_key: Kunci Vigenère (harus sama dengan saat enkripsi)
        blowfish_enc_key: Kunci Blowfish (harus sama dengan saat enkripsi)
        blowfish_mac_key: Kunci HMAC (harus sama dengan saat enkripsi)
    
    Returns:
        Plaintext asli (string)
    
    Raises:
        ValueError: Jika HMAC tidak cocok, key salah, atau data corrupt
    
    Note:
        - Kunci Blowfish/HMAC salah → ValueError dengan pesan jelas
        - Kunci Vigenère salah → plaintext acak (BUKAN error)
          Ini sesuai sifat Vigenère cipher (tidak ada authentication)
    """
    # Lapisan 2: Dekripsi Blowfish-CBC + verifikasi HMAC
    # Jika key salah atau data tampered, akan raise ValueError di sini
    vigenere_bytes = blowfish_module.decrypt(
        ciphertext, 
        blowfish_enc_key, 
        blowfish_mac_key
    )
    
    # Convert bytes ke string
    try:
        vigenere_ciphertext = vigenere_bytes.decode('utf-8')
    except UnicodeDecodeError as e:
        raise ValueError("Gagal decode UTF-8: data corrupt atau key salah") from e
    
    # Lapisan 1: Dekripsi Vigenère
    # Jika kunci Vigenère salah, hasil adalah teks acak (bukan error)
    plaintext = vigenere.decrypt(vigenere_ciphertext, vigenere_key)
    
    return plaintext
