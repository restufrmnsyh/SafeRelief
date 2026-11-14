"""
SafeRelief - Login / Autentikasi Password (4a)

Modul ini menangani verifikasi username + password (faktor kedua dari
tiga faktor login). Faktor pertama (dongle) sudah diverifikasi sebelum
form login ditampilkan; faktor ketiga (wajah) diverifikasi setelah ini.

Keputusan desain keamanan:
- Pesan error SERAGAM: "Username atau password salah" untuk semua kasus
  (user tidak ada, password salah, akun nonaktif). Ini mencegah
  user enumeration — penyerang tidak bisa tahu apakah sebuah username
  terdaftar hanya dari pesan error.
- Lockout dicek SEBELUM verifikasi password. Ini mencegah serangan yang
  mencoba menghindari lockout dengan mengirim banyak request paralel.
- Argon2 dipanggil SETELAH cek lockout, bukan sebelumnya. Karena Argon2
  lambat (~100ms), tidak memanggilnya saat akun terkunci menghemat
  sumber daya.
- Password TIDAK PERNAH di-log dalam bentuk apapun.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import config
from crypto.hashing import verify_password
from database import db


# Pesan error tunggal untuk semua kasus kegagalan login
# (kecuali lockout yang memang perlu info waktu)
_GENERIC_ERROR = "Username atau password salah"


def authenticate(
    conn: sqlite3.Connection,
    username: str,
    password: str,
) -> dict:
    """
    Verifikasi username + password; hasilnya belum merupakan login tiga faktor.

    Urutan pemeriksaan (penting — jangan diubah):
    1. Cari user; jika tidak ada → error generik (tanpa info user tidak ada)
    2. Cek is_active; jika nonaktif → error generik (sama seperti salah password)
    3. Cek lockout; jika terkunci → error dengan sisa waktu (satu-satunya
       pesan berbeda karena user perlu tahu kapan bisa coba lagi)
    4. Verifikasi password Argon2
    5. Jika gagal: increment failed_attempts, kunci jika sudah 3x
    6. Password benar: reset counter, catat PASSWORD_VERIFIED

    Args:
        conn    : Koneksi database.
        username: Username yang diketik user.
        password: Password plaintext yang diketik user.

    Returns:
        dict user (semua kolom dari tabel users) jika password valid.

    Raises:
        ValueError: Login gagal dengan pesan yang sesuai:
                    - "Username atau password salah" (case 1, 2, 4)
                    - "Akun terkunci. Coba lagi dalam X menit Y detik." (case 3)
    """
    # --- 1. Cari user ---
    row = db.get_user_by_username(conn, username)
    if row is None:
        # Catat percobaan dengan user tidak diketahui
        db.log_activity(conn, "LOGIN_FAILED", detail=f"username_not_found")
        raise ValueError(_GENERIC_ERROR)

    user_id: int = row["id"]

    # --- 2. Cek is_active ---
    if row["is_active"] == 0:
        db.log_activity(conn, "LOGIN_FAILED", user_id=user_id,
                        detail="account_inactive")
        raise ValueError(_GENERIC_ERROR)

    # --- 3. Cek lockout ---
    failed_attempts = row["failed_attempts"] or 0
    locked_until_str: Optional[str] = row["locked_until"]
    if locked_until_str:
        locked_until = datetime.fromisoformat(locked_until_str)
        now = datetime.now()
        if now < locked_until:
            remaining = locked_until - now
            total_sec = int(remaining.total_seconds())
            minutes, seconds = divmod(total_sec, 60)
            db.log_activity(conn, "LOGIN_LOCKED", user_id=user_id,
                            detail=f"retry_in_{total_sec}s")
            raise ValueError(
                f"Akun terkunci. Coba lagi dalam {minutes} menit {seconds} detik."
            )
        # Lockout sudah lewat → reset otomatis
        db.update_user_login_attempt(conn, user_id, 0, None)
        # Row SQLite tetap berisi nilai lama meskipun database sudah direset.
        failed_attempts = 0

    # --- 4. Verifikasi password (Argon2) ---
    if not verify_password(password, row["password_hash"]):
        # Increment failed_attempts
        new_attempts = failed_attempts + 1

        if new_attempts >= config.MAX_LOGIN_ATTEMPTS:
            # Kunci akun
            lock_until = datetime.now() + timedelta(seconds=config.ACCOUNT_LOCK_DURATION)
            db.update_user_login_attempt(
                conn, user_id, new_attempts, lock_until.isoformat()
            )
            db.log_activity(conn, "LOGIN_FAILED", user_id=user_id,
                            detail=f"wrong_password_attempt_{new_attempts}_account_locked")
        else:
            db.update_user_login_attempt(conn, user_id, new_attempts, None)
            db.log_activity(conn, "LOGIN_FAILED", user_id=user_id,
                            detail=f"wrong_password_attempt_{new_attempts}")

        raise ValueError(_GENERIC_ERROR)

    # Wajah dan dongle masih harus diperiksa sebelum LOGIN_SUCCESS dicatat.
    db.update_user_login_attempt(conn, user_id, 0, None)
    db.log_activity(conn, "PASSWORD_VERIFIED", user_id=user_id)

    # Kembalikan dict (bukan sqlite3.Row) agar mudah dipakai di luar
    return dict(row)


def logout(conn: sqlite3.Connection, user_id: int, reason: str = "manual") -> None:
    """
    Catat event logout ke activity_log.

    Penghapusan master key dari memori dilakukan oleh auth/session.py,
    bukan di sini.

    Args:
        conn   : Koneksi database.
        user_id: ID user yang logout.
    """
    db.log_activity(conn, "LOGOUT", user_id=user_id, detail=reason)
