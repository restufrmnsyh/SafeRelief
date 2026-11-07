"""
SafeRelief - Hashing Module

Modul untuk hashing password dan data integrity.

Algoritma:
- Argon2id: Hash password pengguna (memory-hard, ASIC-resistant)
- SHA-256: Hash untuk blockchain dan integritas file

Kenapa Argon2:
- Pemenang Password Hashing Competition 2015
- Resistant terhadap GPU/ASIC cracking (memory-hard)
- id variant: hybrid Argon2d (data-dependent) dan Argon2i (independent)
- Parameter tunable untuk balance keamanan vs performa
"""

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import hashlib
import config


# Argon2 hasher dengan parameter dari config
# time_cost: jumlah iterasi
# memory_cost: KB memory yang digunakan
# parallelism: jumlah thread parallel
_argon2_hasher = PasswordHasher(
    time_cost=config.ARGON2_TIME_COST,
    memory_cost=config.ARGON2_MEMORY_COST,
    parallelism=config.ARGON2_PARALLELISM,
    hash_len=32,  # 32 bytes output (256-bit)
    salt_len=16,  # 16 bytes salt (default)
)


def hash_password(password: str) -> str:
    """
    Hash password dengan Argon2id.
    
    Output format: $argon2id$v=19$m=102400,t=2,p=8$salt$hash
    Format ini self-describing (termasuk parameter dan salt).
    
    Args:
        password: Password plaintext
    
    Returns:
        Hash string dalam format Argon2
    
    Raises:
        ValueError: Jika password kosong
    
    Note:
        Hash yang dihasilkan berbeda setiap kali (salt acak),
        tapi verify_password() tetap bisa memverifikasi.
    """
    if not password:
        raise ValueError("Password tidak boleh kosong")
    
    # PasswordHasher.hash() otomatis generate salt acak
    return _argon2_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifikasi password terhadap hash Argon2.
    
    Proses:
    1. Parse parameter dan salt dari password_hash
    2. Hash password dengan parameter dan salt yang sama
    3. Compare hasil dengan hash yang tersimpan (timing-safe)
    
    Args:
        password: Password plaintext yang akan diverifikasi
        password_hash: Hash dari hash_password()
    
    Returns:
        True jika password cocok, False jika tidak
    
    Note:
        Fungsi ini aman dari timing attacks (constant-time comparison).
    """
    try:
        _argon2_hasher.verify(password_hash, password)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        # Hash format invalid atau corrupt
        return False


def rehash_needed(password_hash: str) -> bool:
    """
    Cek apakah password perlu di-rehash dengan parameter baru.
    
    Berguna jika parameter Argon2 di config.py diubah untuk
    meningkatkan keamanan di masa depan.
    
    Args:
        password_hash: Hash dari hash_password()
    
    Returns:
        True jika perlu rehash (parameter berbeda dengan config saat ini)
    
    Note:
        Jika True, saat user login, hash ulang password mereka dengan
        parameter baru dan update database.
    """
    try:
        return _argon2_hasher.check_needs_rehash(password_hash)
    except Exception:
        # Hash invalid, perlu rehash
        return True


def sha256_hash(data: bytes) -> bytes:
    """
    Hash data dengan SHA-256.
    
    Digunakan untuk:
    - Hash token dongle (sebelum simpan di database)
    - Hash block blockchain
    - Hash integritas file/foto
    
    Args:
        data: Data yang akan di-hash (bytes)
    
    Returns:
        Hash SHA-256 (32 bytes)
    
    Example:
        >>> sha256_hash(b"hello")
        b'\\x2c\\xf2\\x4d\\xba...'  # 32 bytes
    """
    return hashlib.sha256(data).digest()


def sha256_hex(data: bytes) -> str:
    """
    Hash data dengan SHA-256, return dalam format hexadecimal.
    
    Lebih readable untuk logging atau display (bukan untuk storage).
    
    Args:
        data: Data yang akan di-hash (bytes)
    
    Returns:
        Hash SHA-256 dalam format hex (64 karakter)
    
    Example:
        >>> sha256_hex(b"hello")
        '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'
    """
    return hashlib.sha256(data).hexdigest()
