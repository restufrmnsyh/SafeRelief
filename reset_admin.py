"""Pemulihan admin lewat recovery.key dan dongle pengganti di komputer server.

Rollback mengikuti pola setup_admin: transaksi SQLite disertai pemulihan token
fisik. Pemulihan file memerlukan drive tetap terhubung dan dapat ditulis; ini
bukan transaksi lintas perangkat yang tahan mati listrik atau penghentian paksa.
"""

import os
import sqlite3
from pathlib import Path

import config
from auth import dongle, masked_input
from crypto import hashing, keys
from database import db


def _get_admin(conn: sqlite3.Connection) -> sqlite3.Row:
    """Ambil admin yang sudah ada, tanpa membuat akun atau skema baru."""
    admins = [row for row in db.list_users(conn) if row["role"] == "admin"]
    if len(admins) != 1:
        raise ValueError("Pemulihan memerlukan tepat satu admin yang sudah terdaftar.")
    admin = db.get_user_by_id(conn, int(admins[0]["id"]))
    if admin is None:
        raise ValueError("Admin yang akan dipulihkan tidak ditemukan.")
    return admin


def _choose_drive() -> str:
    """Batasi pilihan ke daftar removable drive yang terdeteksi."""
    drives = dongle.find_removable_drives()
    if not drives:
        raise ValueError("Tidak ada removable USB yang terdeteksi.")
    print("Removable drives untuk dongle admin pengganti:")
    for index, drive in enumerate(drives, start=1):
        print(f"  {index}. {drive}")
    try:
        choice = int(input("Pilih nomor drive BARU: ").strip())
    except ValueError as exc:
        raise ValueError("Pilihan drive harus berupa nomor dalam daftar.") from exc
    if not 1 <= choice <= len(drives):
        raise ValueError("Nomor drive tidak ada dalam daftar.")
    return drives[choice - 1]


def _reset_admin(
    conn: sqlite3.Connection,
    *,
    master_key: bytes | bytearray,
    drive: str,
    new_password: str,
) -> None:
    """Ganti dongle dan password dalam satu transaksi, pulihkan token jika gagal."""
    if conn.in_transaction:
        raise ValueError("Selesaikan transaksi sebelumnya sebelum pemulihan.")
    if len(master_key) != config.MASTER_KEY_LENGTH:
        raise ValueError("Master key pemulihan tidak valid.")
    if len(new_password) < 8:
        raise ValueError("Password login baru minimal 8 karakter.")
    if drive not in dongle.find_removable_drives():
        raise ValueError("Drive pilihan sudah tidak terdeteksi sebagai removable USB.")

    token_path = dongle._token_path(drive)
    previous_token: bytes | None = None
    token_write_started = False
    try:
        # Kunci tulis menjaga pemeriksaan pemilik dongle dan perubahan akun tetap satu transaksi.
        conn.execute("BEGIN IMMEDIATE")
        admin = _get_admin(conn)
        serial = dongle.get_volume_serial(drive)
        if serial == admin["dongle_serial"]:
            raise ValueError("Gunakan drive baru yang berbeda dari dongle admin lama.")
        if db.get_user_by_dongle_serial(conn, serial) is not None:
            raise ValueError("Drive sudah terdaftar untuk akun lain. Pilih drive baru.")

        password_hash = hashing.hash_password(new_password)
        previous_token = token_path.read_bytes() if token_path.exists() else None
        # SQLite tidak dapat membatalkan tulisan file token ke flashdisk.
        token_write_started = True
        user_id = int(admin["id"])
        token = dongle.provision_dongle(conn, drive, user_id, commit=False)
        salt = os.urandom(16)
        wrapped = keys.wrap_master_key(bytes(master_key), new_password, token, salt)
        db.update_admin_recovery_credentials(
            conn, user_id, password_hash, wrapped, salt, commit=False
        )
        db.log_activity(conn, "RESET_ADMIN_DONGLE", user_id=user_id, commit=False)
        conn.commit()
    except BaseException:
        try:
            if conn.in_transaction:
                conn.rollback()
        finally:
            if token_write_started:
                try:
                    if previous_token is None:
                        token_path.unlink(missing_ok=True)
                    else:
                        token_path.write_bytes(previous_token)
                except OSError as exc:
                    raise RuntimeError(
                        "Pemulihan gagal dan rollback file token tidak berhasil. "
                        "Pastikan drive pengganti terhubung dan dapat ditulis sebelum mencoba lagi."
                    ) from exc
        raise


def main() -> int:
    """Buka recovery dahulu, lalu kumpulkan kredensial pengganti dan jalankan reset."""
    print("SafeRelief - Pemulihan Admin")
    print("Jalankan di komputer server dengan akses fisik. Tutup aplikasi SafeRelief dahulu.")
    master_key: bytearray | None = None
    conn: sqlite3.Connection | None = None
    try:
        recovery_input = input("Path ke recovery.key: ").strip()
        if not recovery_input:
            raise ValueError("Path recovery.key wajib diisi.")
        recovery_path = Path(recovery_input).expanduser()
        recovery_password = masked_input.read_masked_password("Password pemulihan: ")
        # Pemulihan yang gagal tidak boleh membuka transaksi atau menyentuh dongle.
        master_key = bytearray(keys.open_recovery_file(str(recovery_path), recovery_password))
        if not Path(config.DB_PATH).is_file():
            raise ValueError("Database SafeRelief tidak ditemukan. Gunakan database admin yang sudah ada.")
        conn = db.get_connection()
        _get_admin(conn)
        drive = _choose_drive()
        if recovery_path.resolve() == dongle._token_path(drive).resolve():
            raise ValueError("File pemulihan tidak boleh ditimpa sebagai file token dongle.")
        new_password = masked_input.read_masked_password("Password LOGIN baru (minimal 8 karakter): ")
        confirmation = masked_input.read_masked_password("Ulangi password login baru: ")
        if new_password != confirmation:
            raise ValueError("Konfirmasi password login baru tidak cocok.")
        if new_password == recovery_password:
            raise ValueError("Password login baru harus berbeda dari password pemulihan.")
        _reset_admin(conn, master_key=master_key, drive=drive, new_password=new_password)
    except (KeyboardInterrupt, EOFError):
        print("\nPemulihan dibatalkan oleh pengguna.")
        return 130
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"Pemulihan gagal: {exc}")
        return 1
    finally:
        if master_key is not None:
            master_key[:] = b"\x00" * len(master_key)
        if conn is not None:
            conn.close()

    print("Dongle dan password login admin berhasil diganti.")
    print("Login kembali memakai dongle pengganti, password baru, dan verifikasi wajah.")
    print("Jika diperlukan, buat recovery.key baru secara manual dan simpan offline.")
    print("File recovery yang digunakan tidak diubah oleh skrip ini.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
