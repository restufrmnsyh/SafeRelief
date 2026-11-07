"""Seed fictional demo records only; never run this against a real database.

The script requires an active admin login and explicit confirmation. Demo
volunteer accounts are inactive and have no registered dongle or face.
"""

import getpass
import secrets
import sqlite3

import config
from auth import dongle, login
from crypto import hashing, keys
from database import db, secure_store


_CONFIRMATION = "SEED DEMO DATA"


def seed_demo_data(
    conn: sqlite3.Connection,
    admin: dict[str, object],
    master_key: bytes,
) -> None:
    """Atomically add fictional demo records to a clean, single-admin DB."""
    admin_id = int(admin["id"])
    secure_store.require_active_user(conn, admin_id, "admin")
    if conn.in_transaction:
        raise RuntimeError("Seed demo memerlukan koneksi tanpa transaksi aktif.")

    conn.execute("BEGIN IMMEDIATE")
    db_key: bytearray | None = None
    try:
        secure_store.require_active_user(conn, admin_id, "admin")
        counts = db.get_demo_seed_counts(conn)
        if counts != {
            "users": 1,
            "posko": 0,
            "victims": 0,
            "photos": 0,
            "messages": 0,
            "files": 0,
            "blockchain": 0,
        } or db.count_admins(conn) != 1:
            raise ValueError(
                "Database tidak kosong atau bukan database demo baru; seed dibatalkan."
            )

        posko_ids = []
        for name, location, capacity in (
            ("Posko Demo Utara", "Wilayah fiktif Utara", 40),
            ("Posko Demo Selatan", "Wilayah fiktif Selatan", 35),
        ):
            posko_ids.append(
                db.insert_posko(
                    conn,
                    {"nama": name, "lokasi": location, "kapasitas": capacity},
                    commit=False,
                )
            )

        # Akun contoh tidak dapat login: sengaja tidak diberi dongle/wajah.
        for number in (1, 2):
            db.insert_user(
                conn,
                {
                    "nama_lengkap": f"Relawan Fiktif {number}",
                    "username": f"demo_relawan_{number:02d}",
                    "password_hash": hashing.hash_password(
                        secrets.token_urlsafe(32)
                    ),
                    "role": "relawan",
                    "is_active": 0,
                    "posko_id": posko_ids[number - 1],
                },
                commit=False,
            )

        db_key = bytearray(
            keys.derive_key(master_key, config.HKDF_LABEL_DB)
        )
        statuses = ("selamat", "luka ringan", "luka berat", "tidak diketahui")
        for number in range(1, 11):
            secure_store.add_victim(
                conn,
                bytes(db_key),
                {
                    "kode_korban": f"DEMO-{number:03d}",
                    "nama_panggilan": f"Korban Demo {number:02d}",
                    "nama_lengkap": f"Nama Fiktif {number:02d}",
                    "nik": f"DEMO-NIK-{number:03d}",
                    "alamat_asal": f"Alamat fiktif {number:02d}",
                    "kondisi_medis": "Data simulasi, bukan kondisi nyata",
                    "kontak_keluarga": "Kontak fiktif",
                    "catatan": "Data fiktif untuk demonstrasi SafeRelief",
                    "usia": 18 + number,
                    "gender": "tidak diketahui",
                    "posko_id": posko_ids[(number - 1) % len(posko_ids)],
                    "status": statuses[(number - 1) % len(statuses)],
                    "created_by": admin_id,
                },
                commit=False,
            )

        for number in range(1, 6):
            secure_store.append_aid_block(
                conn,
                admin_id,
                {
                    "jenis": f"Bantuan simulasi {number}",
                    "jumlah": number * 10,
                    "dari": "Gudang fiktif",
                    "ke": f"Posko Demo {'Utara' if number % 2 else 'Selatan'}",
                    "petugas": "Admin demo",
                },
                commit=False,
            )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        if db_key is not None:
            db_key[:] = b"\x00" * len(db_key)


def main() -> int:
    """Authenticate the admin, then require a typed demo-only confirmation."""
    print(
        "\nPERINGATAN: seed_demo.py hanya untuk database demo baru berisi satu "
        "admin.\nSemua data relawan dan korban di sini fiktif. Jangan gunakan "
        "pada database sungguhan."
    )
    if input(f'Ketik "{_CONFIRMATION}" untuk lanjut: ').strip() != _CONFIRMATION:
        print("Dibatalkan; tidak ada data demo yang ditambahkan.")
        return 1

    config.ensure_directories()
    db.init_db()
    conn = db.get_connection()
    master_key: bytearray | None = None
    try:
        username = input("Username admin: ").strip()
        password = getpass.getpass("Password admin: ")
        admin = login.authenticate(conn, username, password)
        token = dongle.verify_dongle(admin)
        wrapped = admin.get("wrapped_master_key")
        salt = admin.get("kdf_salt")
        if wrapped is None or salt is None:
            raise ValueError("Master key admin tidak tersedia.")
        master_key = bytearray(
            keys.unwrap_master_key(
                bytes(wrapped), password, token, bytes(salt)
            )
        )
        seed_demo_data(conn, admin, bytes(master_key))
        print("Seed demo berhasil: 2 relawan nonaktif, 10 korban, 5 block bantuan.")
        return 0
    except (OSError, ValueError, sqlite3.Error, PermissionError) as exc:
        print(f"Seed demo gagal: {exc}")
        return 1
    finally:
        if master_key is not None:
            master_key[:] = secrets.token_bytes(len(master_key))
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
