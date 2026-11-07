"""
SafeRelief - Dongle Authentication (4b)

Menangani deteksi, provisi, dan verifikasi dongle (flashdisk USB).

Dongle bukan sekadar "kunci fisik" — token yang tersimpan di dalamnya
adalah BAGIAN DARI KEK (Key-Encrypting Key). Tanpa token yang benar,
master key tidak bisa dibuka meski password benar.

Komponen dongle:
- Serial volume (dari Windows API): identitas hardware yang unik per flashdisk
- Token (32 byte acak, disimpan hex di .saferelief_key): faktor kriptografi
- SHA-256(token): disimpan di database untuk verifikasi tanpa menyimpan token

Keterbatasan yang diakui (untuk laporan):
- File .saferelief_key bisa disalin ke USB lain → tetap butuh password
- Serial volume berubah jika USB diformat
- Tidak ada enkripsi pada file token di USB (hanya hex plaintext)

Windows-only: GetVolumeInformationW hanya ada di Win32 API.
Untuk tes di CI/unit test, mock fungsi ini dengan pytest.monkeypatch.
"""

import ctypes
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Optional

import psutil

import config
from database import db


# ──────────────────────────────────────────────────────────────────────
# Deteksi drive
# ──────────────────────────────────────────────────────────────────────

def find_removable_drives() -> list[str]:
    """
    Cari semua drive removable (USB) yang sedang terpasang.

    Menggunakan psutil.disk_partitions() dan filter berdasarkan
    tipe media. Di Windows, drive USB biasanya bertipe 'removable'.

    Returns:
        List path drive, misal ['D:\\', 'E:\\'].
        List kosong jika tidak ada USB tercolok.
    """
    drives = []
    for part in psutil.disk_partitions(all=False):
        # 'removable' adalah tipe yang umum untuk USB di Windows
        # 'cdrom' diabaikan; 'fixed' adalah HDD/SSD
        if "removable" in part.opts.lower():
            drives.append(part.mountpoint)
    return drives


def get_volume_serial(drive: str) -> str:
    """
    Ambil serial number volume dari Windows API.

    Serial volume adalah angka 32-bit yang ditetapkan saat format.
    Unik per drive (dalam kondisi normal) dan tidak berubah kecuali
    drive diformat ulang.

    Args:
        drive: Path drive, misal 'D:\\' atau 'D:'.

    Returns:
        Serial volume dalam format hex 8 digit, misal 'A1B2C3D4'.

    Raises:
        OSError: Jika drive tidak bisa diakses atau tidak valid.

    Note:
        Fungsi ini hanya bekerja di Windows karena menggunakan
        GetVolumeInformationW dari kernel32.dll.
        Untuk tes: mock get_volume_serial di unit test.
    """
    # Pastikan path berakhir dengan backslash (diperlukan oleh API)
    drive_path = str(drive).rstrip("\\") + "\\"

    # Buffer untuk serial number (DWORD = unsigned int 32-bit)
    serial_buf = ctypes.c_ulong(0)

    result = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(drive_path),
        None,           # volume name buffer (tidak dipakai)
        0,              # ukuran buffer nama
        ctypes.byref(serial_buf),  # ← serial ditulis di sini
        None,           # max component length
        None,           # file system flags
        None,           # file system name buffer
        0,              # ukuran buffer nama filesystem
    )

    if not result:
        raise OSError(f"Tidak bisa membaca serial volume drive '{drive}'")

    # Format sebagai hex 8 digit uppercase
    return f"{serial_buf.value:08X}"


# ──────────────────────────────────────────────────────────────────────
# Token dongle
# ──────────────────────────────────────────────────────────────────────

def _token_path(drive: str) -> Path:
    """Path lengkap file token di drive."""
    return Path(drive) / config.DONGLE_KEY_FILE


def read_token(drive: str) -> bytes:
    """
    Baca token dari file .saferelief_key di drive.

    File berisi token 32 byte dalam encoding hex (64 karakter ASCII).

    Args:
        drive: Path drive, misal 'D:\\'.

    Returns:
        Token sebagai bytes (32 byte).

    Raises:
        FileNotFoundError: File .saferelief_key tidak ada di drive.
        ValueError: Isi file bukan hex valid atau panjang bukan 32 byte.
    """
    path = _token_path(drive)
    if not path.exists():
        raise FileNotFoundError(
            f"File token tidak ditemukan di '{drive}'. "
            "Dongle mungkin belum diprovisi."
        )

    raw = path.read_text(encoding="ascii").strip()

    try:
        token = bytes.fromhex(raw)
    except ValueError as e:
        raise ValueError(f"Isi file token bukan hex yang valid: {e}") from e

    if len(token) != config.DONGLE_TOKEN_LENGTH:
        raise ValueError(
            f"Panjang token tidak valid: "
            f"expected {config.DONGLE_TOKEN_LENGTH} byte, "
            f"got {len(token)} byte."
        )

    return token


def _hash_token(token: bytes) -> str:
    """SHA-256(token) dalam hex. Disimpan di DB, bukan token aslinya."""
    return hashlib.sha256(token).hexdigest()


# ──────────────────────────────────────────────────────────────────────
# Provisi dongle
# ──────────────────────────────────────────────────────────────────────

def provision_dongle(
    conn: sqlite3.Connection,
    drive: str,
    user_id: int,
) -> bytes:
    """
    Provisi dongle untuk user: generate token, tulis ke drive, simpan ke DB.

    Proses:
    1. Generate token acak 32 byte
    2. Tulis token (hex) ke file .saferelief_key di drive
    3. Baca serial volume drive
    4. Simpan serial + SHA-256(token) ke DB

    Fungsi ini menolak jika serial drive sudah dipakai user lain —
    satu dongle hanya boleh untuk satu akun (UNIQUE constraint di DB).

    Args:
        conn   : Koneksi database.
        drive  : Path drive USB, misal 'D:\\'.
        user_id: ID user yang akan mendapat dongle ini.

    Returns:
        Token bytes (32 byte) — dikembalikan agar pemanggil bisa
        langsung derive KEK tanpa harus read_token lagi.

    Raises:
        ValueError: Serial sudah dipakai user lain, atau drive tidak valid.
        OSError   : Drive tidak bisa diakses.
    """
    # 1. Generate token acak
    token = os.urandom(config.DONGLE_TOKEN_LENGTH)

    # 2. Baca serial volume sebelum menulis token
    #    (lebih awal agar gagal cepat jika drive tidak valid)
    serial = get_volume_serial(drive)

    # 3. Cek apakah serial sudah dipakai user LAIN
    cur = conn.execute(
        "SELECT id FROM users WHERE dongle_serial = ?", (serial,)
    )
    existing = cur.fetchone()
    if existing and existing["id"] != user_id:
        raise ValueError(
            f"Serial dongle '{serial}' sudah dipakai akun lain. "
            "Gunakan dongle yang berbeda."
        )

    # 4. Tulis token ke file di drive
    _token_path(drive).write_text(token.hex(), encoding="ascii")

    # 5. Simpan serial + hash token ke DB
    token_hash = _hash_token(token)
    db.update_user_dongle(
        conn,
        user_id=user_id,
        dongle_serial=serial,
        dongle_token_hash=token_hash,
        wrapped_master_key=None,   # diisi oleh setup_admin / wrap ulang
        kdf_salt=None,
    )

    return token


# ──────────────────────────────────────────────────────────────────────
# Verifikasi dongle
# ──────────────────────────────────────────────────────────────────────

def verify_dongle(user_row: dict | sqlite3.Row) -> bytes:
    """
    Verifikasi bahwa dongle yang tercolok adalah milik user ini.

    Pemeriksaan (semua harus lolos):
    1. User punya dongle_serial terdaftar di DB
    2. Ada drive removable yang serial-nya cocok
    3. File .saferelief_key ada di drive tersebut
    4. SHA-256(token di file) == dongle_token_hash di DB

    Pesan error sengaja tidak menjelaskan MANA yang gagal — mencegah
    kebocoran informasi tentang dongle yang valid.

    Args:
        user_row: dict atau sqlite3.Row berisi kolom users
                  (minimal: dongle_serial, dongle_token_hash).

    Returns:
        Token bytes (32 byte) jika valid.
        Token ini langsung dipakai untuk derive KEK — tidak perlu
        read_token() lagi.

    Raises:
        ValueError: Dongle tidak valid, tidak cocok, atau file tidak ada.
    """
    expected_serial: Optional[str] = user_row["dongle_serial"]
    expected_hash: Optional[str]   = user_row["dongle_token_hash"]

    # User belum punya dongle terdaftar
    if not expected_serial or not expected_hash:
        raise ValueError("Akun ini belum memiliki dongle terdaftar.")

    # Cari drive yang serial-nya cocok
    for drive in find_removable_drives():
        try:
            serial = get_volume_serial(drive)
        except OSError:
            continue

        if serial != expected_serial:
            continue  # bukan dongle ini

        # Serial cocok — cek token
        try:
            token = read_token(drive)
        except (FileNotFoundError, ValueError):
            raise ValueError("Dongle tidak valid atau file kunci rusak.")

        # Verifikasi hash (timing-safe tidak diperlukan di sini karena
        # SHA-256 hex comparison, bukan HMAC; timing attack tidak
        # relevan di konteks ini)
        if _hash_token(token) != expected_hash:
            raise ValueError("Dongle tidak valid atau file kunci rusak.")

        return token  # sukses

    raise ValueError("Dongle yang terdaftar tidak ditemukan. Pastikan USB tercolok.")


# ──────────────────────────────────────────────────────────────────────
# Cek keberadaan dongle valid (untuk gerbang awal)
# ──────────────────────────────────────────────────────────────────────

def is_any_valid_dongle_present(conn: sqlite3.Connection) -> bool:
    """
    Cek apakah ada dongle valid milik siapa pun yang sedang tercolok.

    Dipakai oleh UI untuk menampilkan/menyembunyikan form login.
    Pesan ke user hanya "Dongle valid terdeteksi" — TIDAK menyebutkan
    pemilik dongle untuk mencegah kebocoran informasi.

    Proses:
    - Ambil semua drive removable
    - Untuk setiap drive, baca serial
    - Cek apakah serial ada di tabel users
    - Jika ada: cek hash token (verifikasi minimal)

    Args:
        conn: Koneksi database.

    Returns:
        True jika ada minimal satu dongle valid tercolok, False selainnya.
    """
    for drive in find_removable_drives():
        try:
            serial = get_volume_serial(drive)
        except OSError:
            continue

        # Cari user dengan serial ini
        cur = conn.execute(
            "SELECT dongle_token_hash FROM users WHERE dongle_serial = ?",
            (serial,)
        )
        row = cur.fetchone()
        if row is None:
            continue

        # Verifikasi token minimal
        try:
            token = read_token(drive)
            if _hash_token(token) == row["dongle_token_hash"]:
                return True
        except (FileNotFoundError, ValueError):
            continue

    return False
