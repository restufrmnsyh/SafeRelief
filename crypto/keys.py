"""
SafeRelief - Key Management Module

Modul manajemen kunci untuk SafeRelief.
Menangani derivasi kunci, wrapping/unwrapping master key, dan recovery.

Arsitektur Kunci:
1. Master Key (32 bytes): Kunci utama organisasi, TIDAK PERNAH disimpan polos
2. KEK (Key-Encrypting Key): Derived dari password + token dongle via Scrypt
3. Wrapped Master Key: Master key terenkripsi dengan KEK, disimpan di database
4. Derived Keys: Kunci turunan dari master key via HKDF untuk berbagai keperluan

Kenapa arsitektur ini:
- Master key tidak pernah ada dalam bentuk polos di storage
- Butuh 2 faktor untuk membuka master key: password (something you know) + 
  dongle (something you have)
- Satu master key bisa dibungkus untuk banyak user dengan KEK berbeda
- Key rotation mudah: cukup wrap ulang master key dengan KEK baru
"""

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import os
import config
from . import aes_module


def generate_master_key() -> bytes:
    """
    Generate master key organisasi (32 bytes acak).
    
    Dipanggil HANYA saat setup admin pertama kali.
    Master key ini akan di-wrap untuk setiap user.
    
    Returns:
        Master key 32 bytes
    """
    return os.urandom(config.MASTER_KEY_LENGTH)  # 32 bytes


def derive_kek(password: str, token: bytes, salt: bytes) -> bytes:
    """
    Derive KEK (Key-Encrypting Key) dari password + token dongle via Scrypt.
    
    Proses:
    1. Gabungkan password (UTF-8) + token (32 bytes)
    2. Derive key dengan Scrypt (memory-hard KDF)
    3. Return 32 bytes KEK
    
    Kenapa Scrypt:
    - Memory-hard: sulit untuk brute-force parallel (GPU/ASIC)
    - Parameter tunable dari config.py
    - Standar untuk key derivation dari password
    
    Kenapa password + token:
    - Password: something you know
    - Token: something you have (dari dongle)
    - Keduanya diperlukan untuk derive KEK yang benar
    - Token 32 bytes di akhir, tidak ambigu saat parsing
    
    Args:
        password: Password user (string)
        token: Token dari dongle (32 bytes)
        salt: Salt untuk Scrypt (16 bytes, disimpan di database)
    
    Returns:
        KEK 32 bytes
    
    Raises:
        ValueError: Jika token bukan 32 bytes atau salt bukan 16 bytes
    """
    if len(token) != config.DONGLE_TOKEN_LENGTH:
        raise ValueError(f"Token harus {config.DONGLE_TOKEN_LENGTH} bytes")
    
    if len(salt) != 16:
        raise ValueError("Salt harus 16 bytes")
    
    # Gabungkan password (bytes) + token (bytes)
    # Token di akhir, panjangnya tetap (32 bytes), jadi tidak ambigu
    password_bytes = password.encode('utf-8')
    combined = password_bytes + token
    
    # Derive KEK dengan Scrypt
    kdf = Scrypt(
        salt=salt,
        length=32,  # Output 32 bytes
        n=config.SCRYPT_N,  # CPU/memory cost (16384 = 2^14)
        r=config.SCRYPT_R,  # Block size (8)
        p=config.SCRYPT_P,  # Parallelization (1)
        backend=default_backend()
    )
    
    kek = kdf.derive(combined)
    return kek


def wrap_master_key(master_key: bytes, password: str, token: bytes, salt: bytes) -> bytes:
    """
    Wrap (enkripsi) master key dengan KEK.
    
    Proses:
    1. Derive KEK dari password + token + salt
    2. Enkripsi master key dengan AES-GCM menggunakan KEK
    3. Return wrapped master key (nonce + ciphertext + tag)
    
    Output disimpan di database kolom `wrapped_master_key`.
    Salt disimpan terpisah di kolom `kdf_salt`.
    
    Args:
        master_key: Master key organisasi (32 bytes)
        password: Password user
        token: Token dongle (32 bytes)
        salt: Salt untuk Scrypt (16 bytes)
    
    Returns:
        Wrapped master key (nonce(12) + ciphertext + tag(16) = 60 bytes)
    
    Raises:
        ValueError: Jika master_key bukan 32 bytes, token bukan 32 bytes, 
                    atau salt bukan 16 bytes
    """
    if len(master_key) != config.MASTER_KEY_LENGTH:
        raise ValueError(f"Master key harus {config.MASTER_KEY_LENGTH} bytes")
    
    # Derive KEK
    kek = derive_kek(password, token, salt)
    
    # Enkripsi master key dengan KEK (AES-256-GCM)
    wrapped = aes_module.encrypt(master_key, kek)
    
    return wrapped


def unwrap_master_key(wrapped_master_key: bytes, password: str, token: bytes, salt: bytes) -> bytes:
    """
    Unwrap (dekripsi) master key dari wrapped form.
    
    Proses:
    1. Derive KEK dari password + token + salt
    2. Dekripsi wrapped master key dengan KEK
    3. Return master key
    
    Fungsi ini HARUS raise error yang jelas jika:
    - Password salah: KEK salah → AES-GCM InvalidTag
    - Token salah: KEK salah → AES-GCM InvalidTag
    - Data corrupt: AES-GCM InvalidTag
    
    Args:
        wrapped_master_key: Output dari wrap_master_key()
        password: Password user (harus sama dengan saat wrap)
        token: Token dongle (harus sama dengan saat wrap)
        salt: Salt untuk Scrypt (dari database)
    
    Returns:
        Master key (32 bytes)
    
    Raises:
        ValueError: Jika password ATAU token salah, atau data corrupt
                   Pesan error: "Gagal membuka master key: password atau dongle salah"
    
    Note:
        Error dari password salah dan token salah TIDAK DIBEDAKAN untuk keamanan
        (mencegah information leakage tentang faktor mana yang salah).
    """
    try:
        # Derive KEK
        kek = derive_kek(password, token, salt)
        
        # Dekripsi wrapped master key
        master_key = aes_module.decrypt(wrapped_master_key, kek)
        
        # Verifikasi panjang (sanity check)
        if len(master_key) != config.MASTER_KEY_LENGTH:
            raise ValueError("Master key length invalid setelah unwrap")
        
        return master_key
        
    except Exception as e:
        # Semua error (InvalidTag, ValueError, dll) di-wrap jadi satu pesan
        # Tidak membedakan password salah vs token salah untuk mencegah
        # kebocoran informasi tentang faktor mana yang salah
        raise ValueError("Gagal membuka master key: password atau dongle salah") from e


def derive_key(master_key: bytes, info: bytes) -> bytes:
    """
    Derive kunci turunan dari master key dengan HKDF-SHA256.
    
    HKDF (HMAC-based Key Derivation Function) digunakan untuk menurunkan
    banyak kunci independen dari satu master key.
    
    Proses:
    1. HKDF dengan SHA-256
    2. Salt: None (master key sudah cukup acak)
    3. Info: label untuk membedakan kunci (dari config.py)
    
    Args:
        master_key: Master key organisasi (32 bytes)
        info: Label untuk jenis kunci (misal: b"db", b"chat-enc")
              Label dari config.HKDF_LABEL_*
    
    Returns:
        Kunci turunan 32 bytes
    
    Raises:
        ValueError: Jika master_key bukan 32 bytes
    
    Example:
        >>> db_key = derive_key(master_key, config.HKDF_LABEL_DB)
        >>> chat_enc_key = derive_key(master_key, config.HKDF_LABEL_CHAT_ENC)
    
    Note:
        JANGAN UBAH label setelah ada data! Data tidak akan terbaca.
    """
    if len(master_key) != config.MASTER_KEY_LENGTH:
        raise ValueError(f"Master key harus {config.MASTER_KEY_LENGTH} bytes")
    
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,  # Output 32 bytes
        salt=None,  # Master key sudah high-entropy, salt opsional
        info=info,
        backend=default_backend()
    )
    
    derived_key = hkdf.derive(master_key)
    return derived_key


def derive_vigenere_key(master_key: bytes) -> str:
    """
    Derive kunci Vigenère otomatis dari master key.
    
    Proses:
    1. Derive 16 bytes dengan HKDF (label: b"vigenere")
    2. Map tiap byte ke karakter ASCII cetak (32-126)
    3. Formula: chr(32 + (byte % 95))
    
    Kenapa otomatis:
    - User tidak perlu ketik kunci manual
    - Kunci tetap deterministik (master key sama → kunci Vigenère sama)
    - Kunci cukup panjang (16 karakter) dan acak
    
    Args:
        master_key: Master key organisasi (32 bytes)
    
    Returns:
        Kunci Vigenère (16 karakter ASCII cetak 32-126)
    
    Raises:
        ValueError: Jika master_key bukan 32 bytes
    
    Example:
        >>> key = derive_vigenere_key(master_key)
        >>> len(key)
        16
        >>> all(32 <= ord(c) <= 126 for c in key)
        True
    """
    if len(master_key) != config.MASTER_KEY_LENGTH:
        raise ValueError(f"Master key harus {config.MASTER_KEY_LENGTH} bytes")
    
    # Derive bytes untuk Vigenère key
    key_bytes = derive_key(master_key, config.HKDF_LABEL_VIGENERE)
    
    # Ambil 16 bytes pertama (cukup untuk kunci Vigenère)
    key_bytes = key_bytes[:config.VIGENERE_KEY_LENGTH]
    
    # Map tiap byte ke karakter ASCII 32-126 (95 karakter cetak)
    # Formula: 32 + (byte % 95)
    vigenere_key = ''.join(
        chr(32 + (byte % 95)) for byte in key_bytes
    )
    
    return vigenere_key


def create_recovery_file(master_key: bytes, recovery_password: str, output_path: str) -> None:
    """
    Buat file recovery untuk pemulihan master key.
    
    File recovery adalah backup master key yang dibungkus dengan password
    pemulihan (berbeda dari password login). File ini disimpan OFFLINE
    oleh admin untuk disaster recovery jika dongle hilang/rusak.
    
    Proses:
    1. Tolak jika output_path sudah ada (mencegah overwrite tidak sengaja)
    2. Generate salt acak
    3. Derive KEK dari recovery_password + salt dengan Scrypt (parameter berat)
    4. Enkripsi master key dengan AES-GCM
    5. Tulis: salt(16) + wrapped_master_key ke file
    
    Args:
        master_key: Master key organisasi (32 bytes)
        recovery_password: Password khusus untuk recovery (minimal 12 karakter)
        output_path: Path file recovery (misal: recovery.key)
    
    Raises:
        FileExistsError: Jika output_path sudah ada
        ValueError: Jika master_key tidak valid atau password terlalu pendek
    
    Note:
        Recovery password HARUS berbeda dari password login.
        File ini HARUS disimpan di lokasi aman offline (USB terpisah, dll).
        Parameter Scrypt lebih berat (N=2^17) karena file ini tidak butuh dongle,
        sehingga perlu perlindungan ekstra dari brute-force.
    """
    if len(master_key) != config.MASTER_KEY_LENGTH:
        raise ValueError(f"Master key harus {config.MASTER_KEY_LENGTH} bytes")
    
    if len(recovery_password) < 12:
        raise ValueError("Recovery password minimal 12 karakter")
    
    # Tolak jika file sudah ada — jangan overwrite recovery file secara diam-diam
    import os as _os
    if _os.path.exists(output_path):
        raise FileExistsError(f"File recovery sudah ada: {output_path}")
    
    # Generate salt untuk recovery
    salt = os.urandom(16)
    
    # Derive KEK dari recovery password
    # Pakai parameter lebih berat dari login (RECOVERY_SCRYPT_N = 2^17)
    # karena file ini tidak punya faktor dongle sebagai perlindungan tambahan
    password_bytes = recovery_password.encode('utf-8')
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=config.RECOVERY_SCRYPT_N,
        r=config.RECOVERY_SCRYPT_R,
        p=config.RECOVERY_SCRYPT_P,
        backend=default_backend()
    )
    recovery_kek = kdf.derive(password_bytes)
    
    # Enkripsi master key
    wrapped = aes_module.encrypt(master_key, recovery_kek)
    
    # Tulis: salt + wrapped master key
    with open(output_path, 'wb') as f:
        f.write(salt + wrapped)


def open_recovery_file(recovery_path: str, recovery_password: str) -> bytes:
    """
    Buka file recovery dan ekstrak master key.
    
    Digunakan oleh reset_admin.py untuk recovery jika dongle admin hilang.
    
    Proses:
    1. Baca file: salt(16) + wrapped_master_key
    2. Derive KEK dari recovery_password + salt (parameter Scrypt sama dengan create)
    3. Dekripsi wrapped master key
    4. Return master key
    
    Args:
        recovery_path: Path ke file recovery.key
        recovery_password: Password yang digunakan saat create_recovery_file()
    
    Returns:
        Master key (32 bytes)
    
    Raises:
        FileNotFoundError: Jika file tidak ada
        ValueError: Jika password salah atau file corrupt
    
    Note:
        Parameter Scrypt (RECOVERY_SCRYPT_N) HARUS sama dengan create_recovery_file.
        Setelah recovery, master key perlu di-wrap ulang untuk admin dengan
        password baru dan dongle baru.
    """
    with open(recovery_path, 'rb') as f:
        data = f.read()
    
    # Parse: salt(16) + wrapped_master_key
    if len(data) < 16 + 28:  # salt + minimal wrapped (nonce+tag)
        raise ValueError("File recovery corrupt atau tidak valid")
    
    salt = data[:16]
    wrapped_master_key = data[16:]
    
    # Derive KEK dari recovery password
    # Pakai parameter yang SAMA dengan create_recovery_file (RECOVERY_SCRYPT_N)
    password_bytes = recovery_password.encode('utf-8')
    kdf = Scrypt(
        salt=salt,
        length=32,
        n=config.RECOVERY_SCRYPT_N,
        r=config.RECOVERY_SCRYPT_R,
        p=config.RECOVERY_SCRYPT_P,
        backend=default_backend()
    )
    
    try:
        recovery_kek = kdf.derive(password_bytes)
        master_key = aes_module.decrypt(wrapped_master_key, recovery_kek)
        
        # Verifikasi panjang
        if len(master_key) != config.MASTER_KEY_LENGTH:
            raise ValueError("Master key length invalid")
        
        return master_key
        
    except Exception as e:
        raise ValueError("Recovery password salah atau file corrupt") from e
