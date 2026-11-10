"""Bootstrap admin pertama SafeRelief dengan perubahan database atomik."""

import getpass
import os
import sqlite3
from pathlib import Path

import cv2

import config
from auth import dongle, face_auth
from crypto import aes_module, hashing, keys
from database import db


def _prompt_confirmed_secret(label: str, minimum_length: int) -> str:
    """Minta rahasia dua kali agar typo tidak menjadi kredensial permanen."""
    secret = getpass.getpass(f"{label}: ")
    confirmation = getpass.getpass(f"Ulangi {label.lower()}: ")
    if secret != confirmation:
        raise ValueError(f"{label} tidak cocok.")
    if len(secret) < minimum_length:
        raise ValueError(f"{label} minimal {minimum_length} karakter.")
    return secret


def _choose_drive() -> str:
    """Tampilkan removable drive dan minta pilihan yang valid."""
    drives = dongle.find_removable_drives()
    if not drives:
        raise ValueError("Tidak ada removable USB yang terdeteksi.")

    print("Removable drives yang terdeteksi:")
    for index, drive in enumerate(drives, start=1):
        print(f"  {index}. {drive}")

    choice = input("Pilih nomor drive untuk dongle admin: ").strip()
    try:
        selected = int(choice)
    except ValueError as exc:
        raise ValueError("Pilihan drive harus berupa nomor dalam daftar.") from exc
    if not 1 <= selected <= len(drives):
        raise ValueError("Nomor drive tidak ada dalam daftar.")
    return drives[selected - 1]


def _bootstrap_admin(
    conn: sqlite3.Connection,
    *,
    full_name: str,
    username: str,
    password: str,
    recovery_password: str,
    recovery_path: Path,
    drive: str,
) -> None:
    """Buat akun, dongle, embedding dan recovery dalam satu transaksi DB."""
    if recovery_path.exists():
        raise FileExistsError(f"File recovery sudah ada: {recovery_path}")

    recovery_write_started = False
    try:
        # Kunci tulis dan cek ulang mencegah dua bootstrap berjalan bersamaan.
        conn.execute("BEGIN IMMEDIATE")
        if db.count_admins(conn):
            raise ValueError("Admin sudah terdaftar; setup_admin hanya sekali.")
        if db.get_user_by_username(conn, username) is not None:
            raise ValueError("Username tersebut sudah digunakan.")

        master_key = keys.generate_master_key()
        user_id = db.insert_user(
            conn,
            {
                "nama_lengkap": full_name,
                "username": username,
                "password_hash": hashing.hash_password(password),
                "role": "admin",
                "is_active": 1,
            },
            commit=False,
        )

        token = dongle.provision_dongle(conn, drive, user_id, commit=False)
        salt = os.urandom(16)
        wrapped_master_key = keys.wrap_master_key(
            master_key, password, token, salt
        )
        user_row = db.get_user_by_id(conn, user_id)
        if user_row is None:
            raise RuntimeError("Admin sementara tidak ditemukan di database.")
        db.update_user_dongle(
            conn,
            user_id,
            dongle_serial=user_row["dongle_serial"],
            dongle_token_hash=user_row["dongle_token_hash"],
            wrapped_master_key=wrapped_master_key,
            kdf_salt=salt,
            commit=False,
        )

        if recovery_path.exists():
            raise FileExistsError(f"File recovery sudah ada: {recovery_path}")
        recovery_write_started = True
        keys.create_recovery_file(
            master_key, recovery_password, str(recovery_path)
        )
        db.log_activity(
            conn, "ADMIN_BOOTSTRAP", user_id=user_id, commit=False
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        # Do not leave a newly-created recovery file behind on a failed setup.
        if recovery_write_started and recovery_path.exists():
            recovery_path.unlink()
        raise


def main() -> int:
    """Collect bootstrap inputs, create the first admin, and report status."""
    print("SafeRelief - Setup Admin Awal")
    print("=" * 50)

    db.init_db()
    conn = db.get_connection()
    try:
        if db.count_admins(conn):
            print("Setup ditolak: admin sudah terdaftar.")
            return 1

        try:
            drive = _choose_drive()
            full_name = input("Nama lengkap admin: ").strip()
            username = input("Username admin: ").strip()
            if not full_name or not username:
                raise ValueError("Nama lengkap dan username wajib diisi.")

            password = _prompt_confirmed_secret("Password admin", 8)
            recovery_password = _prompt_confirmed_secret(
                "Password pemulihan", 12
            )
            if recovery_password == password:
                raise ValueError(
                    "Password pemulihan harus berbeda dari password admin."
                )

            recovery_input = input(
                "Path untuk recovery.key (simpan offline): "
            ).strip()
            if not recovery_input:
                raise ValueError("Path recovery.key wajib diisi.")
            recovery_path = Path(recovery_input).expanduser()
            if recovery_path.exists():
                raise FileExistsError(
                    f"File recovery sudah ada: {recovery_path}"
                )
            if db.get_user_by_username(conn, username) is not None:
                raise ValueError("Username tersebut sudah digunakan.")

            _bootstrap_admin(
                conn,
                full_name=full_name,
                username=username,
                password=password,
                recovery_password=recovery_password,
                recovery_path=recovery_path,
                drive=drive,
            )
        except (ValueError, OSError, sqlite3.Error, cv2.error) as exc:
            print(f"Setup gagal: {exc}")
            return 1

        print(f"Admin '{username}' berhasil dibuat.")
        print("Pendaftaran wajah akan dilakukan saat login pertama di aplikasi.")
        print(f"Simpan file recovery secara offline: {recovery_path}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
