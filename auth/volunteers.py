"""Operasi manajemen relawan yang hanya boleh dijalankan admin aktif."""

import os
import sqlite3

import config
from auth import dongle, face_auth, session
from crypto import hashing, keys
from database import db, secure_store


def _require_admin() -> dict[str, object]:
    """Pastikan aksi relawan berasal dari sesi admin, bukan sekadar UI tersembunyi."""
    user = session.get_current_user()
    if user.get("role") != "admin":
        raise PermissionError("Hanya admin yang dapat mengelola relawan.")
    return user


def list_volunteers(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Ambil profil relawan tanpa hash atau kolom kunci."""
    _require_admin()
    return [
        dict(user)
        for user in db.list_users(conn)
        if user["role"] == "relawan"
    ]


def list_posko(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """Ambil daftar posko untuk pilihan pada formulir admin."""
    _require_admin()
    return [dict(posko) for posko in db.list_posko(conn)]


def _validate_profile(nama_lengkap: str, username: str) -> None:
    if not nama_lengkap.strip() or not username.strip():
        raise ValueError("Nama lengkap dan username wajib diisi.")


def create_volunteer(
    conn: sqlite3.Connection,
    *,
    nama_lengkap: str,
    username: str,
    password: str,
    posko_id: int | None,
    drive: str,
    encoding,
) -> int:
    """Daftarkan relawan, wajah, dongle, dan master key dalam satu transaksi."""
    _require_admin()
    _validate_profile(nama_lengkap, username)
    if len(password) < 8:
        raise ValueError("Password relawan minimal 8 karakter.")
    if db.get_user_by_username(conn, username.strip()) is not None:
        raise ValueError("Username tersebut sudah digunakan.")

    token_file = dongle._token_path(drive)
    if token_file.exists():
        raise FileExistsError(
            "Drive pilihan sudah berisi file kunci SafeRelief; pilih drive lain."
        )

    user_id: int | None = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Periksa ulang di dalam transaksi karena username bisa berubah bersamaan.
        if db.get_user_by_username(conn, username.strip()) is not None:
            raise ValueError("Username tersebut sudah digunakan.")

        user_id = db.insert_user(
            conn,
            {
                "nama_lengkap": nama_lengkap.strip(),
                "username": username.strip(),
                "password_hash": hashing.hash_password(password),
                "role": "relawan",
                "posko_id": posko_id,
                "is_active": 1,
            },
            commit=False,
        )

        token = dongle.provision_dongle(
            conn, drive, user_id, commit=False
        )
        master_key = session.get_master_key()
        salt = os.urandom(16)
        wrapped = keys.wrap_master_key(master_key, password, token, salt)
        user_row = db.get_user_by_id(conn, user_id)
        if user_row is None:
            raise RuntimeError("Data relawan baru tidak ditemukan.")
        db.update_user_dongle(
            conn,
            user_id,
            user_row["dongle_serial"],
            user_row["dongle_token_hash"],
            wrapped,
            salt,
            commit=False,
        )
        secure_store.save_face_encoding(
            conn,
            session.get_derived_key(config.HKDF_LABEL_DB),
            user_id,
            face_auth.encoding_to_bytes(encoding),
            commit=False,
        )
        db.log_activity(
            conn,
            "VOLUNTEER_CREATED",
            user_id=int(_require_admin()["id"]),
            detail=f"volunteer_id={user_id}",
            commit=False,
        )
        conn.commit()
        return user_id
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        if token_file.exists():
            token_file.unlink()
        raise


def update_volunteer(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    nama_lengkap: str,
    username: str,
    posko_id: int | None,
    new_password: str | None = None,
) -> None:
    """Edit profil relawan dan, bila diminta, reset password serta wrap key."""
    admin = _require_admin()
    _validate_profile(nama_lengkap, username)
    if new_password and len(new_password) < 8:
        raise ValueError("Password baru minimal 8 karakter.")

    try:
        conn.execute("BEGIN IMMEDIATE")
        row = db.get_user_by_id(conn, user_id)
        if row is None or row["role"] != "relawan":
            raise ValueError("Relawan tidak ditemukan.")
        existing = db.get_user_by_username(conn, username.strip())
        if existing is not None and existing["id"] != user_id:
            raise ValueError("Username tersebut sudah digunakan.")

        db.update_user_profile(
            conn,
            user_id,
            nama_lengkap.strip(),
            username.strip(),
            posko_id,
            commit=False,
        )
        if new_password:
            token = dongle.verify_dongle(row)
            salt = os.urandom(16)
            wrapped = keys.wrap_master_key(
                session.get_master_key(), new_password, token, salt
            )
            db.update_user_credentials(
                conn,
                user_id,
                hashing.hash_password(new_password),
                wrapped,
                salt,
                commit=False,
            )
        db.log_activity(
            conn,
            "VOLUNTEER_UPDATED",
            user_id=int(admin["id"]),
            detail=f"volunteer_id={user_id}",
            commit=False,
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def set_volunteer_active(
    conn: sqlite3.Connection, user_id: int, is_active: bool
) -> None:
    """Aktifkan atau blokir akun relawan dan catat aksinya."""
    admin = _require_admin()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = db.get_user_by_id(conn, user_id)
        if row is None or row["role"] != "relawan":
            raise ValueError("Relawan tidak ditemukan.")
        db.update_user_active(
            conn, user_id, int(is_active), commit=False
        )
        db.log_activity(
            conn,
            "VOLUNTEER_ACTIVATED" if is_active else "VOLUNTEER_BLOCKED",
            user_id=int(admin["id"]),
            detail=f"volunteer_id={user_id}",
            commit=False,
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise


def replace_volunteer_dongle(
    conn: sqlite3.Connection,
    user_id: int,
    drive: str,
    new_password: str,
) -> None:
    """Ganti dongle, set password baru, dan bungkus ulang master key."""
    admin = _require_admin()
    if len(new_password) < 8:
        raise ValueError(
            "Untuk mengganti dongle, password relawan baru minimal 8 karakter."
        )
    row = db.get_user_by_id(conn, user_id)
    if row is None or row["role"] != "relawan":
        raise ValueError("Relawan tidak ditemukan.")

    token_file = dongle._token_path(drive)
    serial = dongle.get_volume_serial(drive)
    same_registered_drive = serial == row["dongle_serial"]
    if token_file.exists() and not same_registered_drive:
        raise FileExistsError(
            "Drive pilihan sudah berisi file kunci SafeRelief; pilih drive lain."
        )
    previous_contents = token_file.read_bytes() if token_file.exists() else None

    try:
        conn.execute("BEGIN IMMEDIATE")
        token = dongle.provision_dongle(
            conn, drive, user_id, commit=False
        )
        salt = os.urandom(16)
        wrapped = keys.wrap_master_key(
            session.get_master_key(), new_password, token, salt
        )
        updated_row = db.get_user_by_id(conn, user_id)
        if updated_row is None:
            raise RuntimeError("Data relawan tidak ditemukan setelah dongle diganti.")
        db.update_user_dongle(
            conn,
            user_id,
            updated_row["dongle_serial"],
            updated_row["dongle_token_hash"],
            wrapped,
            salt,
            commit=False,
        )
        db.update_user_credentials(
            conn,
            user_id,
            hashing.hash_password(new_password),
            wrapped,
            salt,
            commit=False,
        )
        db.log_activity(
            conn,
            "DONGLE_REPLACED",
            user_id=int(admin["id"]),
            detail=f"volunteer_id={user_id}",
            commit=False,
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        if previous_contents is None:
            if token_file.exists():
                token_file.unlink()
        else:
            token_file.write_bytes(previous_contents)
        raise
