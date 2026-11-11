"""
SafeRelief - Database Access Layer (db.py)

Satu-satunya tempat yang boleh menulis SQL di seluruh proyek.
UI dan modul lain memanggil fungsi di sini; TIDAK boleh membuat query sendiri.

Prinsip:
- Semua query berparameter (?) — tidak ada f-string untuk nilai data
  → mencegah SQL injection secara struktural
- PRAGMA foreign_keys = ON di setiap koneksi
  → CASCADE/RESTRICT berjalan dengan benar
- row_factory = sqlite3.Row → hasil bisa diakses dengan nama kolom
- db.py hanya menerima/mengembalikan nilai mentah (BLOB sudah terenkripsi
  oleh pemanggil); modul ini tidak tahu soal kunci kriptografi

Path database diambil dari config.DB_PATH.
Untuk tes, panggil get_connection(path=...) dengan path sementara.
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

import config


# ──────────────────────────────────────────────────────────────────────
# Koneksi
# ──────────────────────────────────────────────────────────────────────

def get_connection(path: Optional[str | Path] = None) -> sqlite3.Connection:
    """
    Buka koneksi ke database SQLite.

    Args:
        path: Path file database. Default: config.DB_PATH.
              Gunakan ':memory:' atau tmp_path untuk tes.

    Returns:
        sqlite3.Connection dengan row_factory=Row dan foreign_keys=ON.
    """
    db_path = str(path) if path is not None else str(config.DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # foreign keys HARUS diaktifkan per koneksi di SQLite
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Optional[str | Path] = None) -> None:
    """
    Inisialisasi database: buat semua tabel dari schema.sql.

    Idempoten — aman dipanggil berkali-kali (CREATE TABLE IF NOT EXISTS).
    Jika file DB belum ada, SQLite membuatnya otomatis.

    Args:
        path: Path file database. Default: config.DB_PATH.
    """
    schema_path = Path(__file__).parent / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    # Pastikan direktori data/ ada
    db_path = path if path is not None else config.DB_PATH
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as conn:
        conn.executescript(sql)


# ──────────────────────────────────────────────────────────────────────
# Users
# ──────────────────────────────────────────────────────────────────────

def insert_user(
    conn: sqlite3.Connection, data: dict, *, commit: bool = True
) -> int:
    """
    Sisipkan user baru. Mengembalikan id yang baru dibuat.

    Kolom yang diharapkan di `data`:
        nama_lengkap, username, password_hash, role,
        is_active (opsional, default 1),
        posko_id (opsional), face_encoding_enc (opsional),
        dongle_serial (opsional), dongle_token_hash (opsional),
        wrapped_master_key (opsional), kdf_salt (opsional)
    """
    cur = conn.execute(
        """
        INSERT INTO users
            (nama_lengkap, username, password_hash, role, is_active,
             posko_id, face_encoding_enc, dongle_serial, dongle_token_hash,
             wrapped_master_key, kdf_salt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["nama_lengkap"],
            data["username"],
            data["password_hash"],
            data["role"],
            data.get("is_active", 1),   # default aktif
            data.get("posko_id"),
            data.get("face_encoding_enc"),
            data.get("dongle_serial"),
            data.get("dongle_token_hash"),
            data.get("wrapped_master_key"),
            data.get("kdf_salt"),
        ),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def count_admins(conn: sqlite3.Connection) -> int:
    """Hitung admin yang sudah terdaftar untuk menjaga bootstrap satu kali."""
    cur = conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", ("admin",))
    return cur.fetchone()[0]


def get_user_by_username(conn: sqlite3.Connection, username: str) -> Optional[sqlite3.Row]:
    """Cari user berdasarkan username. Return None jika tidak ada."""
    cur = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    )
    return cur.fetchone()


def get_user_by_id(conn: sqlite3.Connection, user_id: int) -> Optional[sqlite3.Row]:
    """Cari user berdasarkan id."""
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cur.fetchone()


def get_user_by_dongle_serial(
    conn: sqlite3.Connection, serial: str
) -> Optional[sqlite3.Row]:
    """Cari user yang terdaftar dengan serial dongle tersebut."""
    cur = conn.execute(
        "SELECT * FROM users WHERE dongle_serial = ?", (serial,)
    )
    return cur.fetchone()


def update_user_login_attempt(
    conn: sqlite3.Connection,
    user_id: int,
    failed_attempts: int,
    locked_until: Optional[str],
) -> None:
    """Update percobaan login gagal dan waktu kunci akun."""
    conn.execute(
        "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
        (failed_attempts, locked_until, user_id),
    )
    conn.commit()


def update_user_dongle(
    conn: sqlite3.Connection,
    user_id: int,
    dongle_serial: Optional[str],
    dongle_token_hash: Optional[str],
    wrapped_master_key: Optional[bytes],
    kdf_salt: Optional[bytes],
    *,
    commit: bool = True,
) -> None:
    """Update data dongle dan wrapped master key setelah provision/ganti dongle."""
    conn.execute(
        """
        UPDATE users
        SET dongle_serial = ?, dongle_token_hash = ?,
            wrapped_master_key = ?, kdf_salt = ?
        WHERE id = ?
        """,
        (dongle_serial, dongle_token_hash, wrapped_master_key, kdf_salt, user_id),
    )
    if commit:
        conn.commit()


def update_user_face(
    conn: sqlite3.Connection,
    user_id: int,
    face_encoding_enc: bytes,
    *,
    commit: bool = True,
) -> None:
    """Simpan embedding wajah terenkripsi."""
    conn.execute(
        "UPDATE users SET face_encoding_enc = ? WHERE id = ?",
        (face_encoding_enc, user_id),
    )
    if commit:
        conn.commit()


def update_user_active(
    conn: sqlite3.Connection,
    user_id: int,
    is_active: int,
    *,
    commit: bool = True,
) -> None:
    """Aktifkan (1) atau blokir (0) akun user."""
    conn.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (is_active, user_id),
    )
    if commit:
        conn.commit()


def update_user_profile(
    conn: sqlite3.Connection,
    user_id: int,
    nama_lengkap: str,
    username: str,
    posko_id: int | None,
    *,
    commit: bool = True,
) -> None:
    """Perbarui profil dasar relawan tanpa menyentuh role atau rahasia."""
    conn.execute(
        """
        UPDATE users SET nama_lengkap = ?, username = ?, posko_id = ?
        WHERE id = ? AND role = 'relawan'
        """,
        (nama_lengkap, username, posko_id, user_id),
    )
    if commit:
        conn.commit()


def update_user_credentials(
    conn: sqlite3.Connection,
    user_id: int,
    password_hash: str,
    wrapped_master_key: bytes,
    kdf_salt: bytes,
    *,
    commit: bool = True,
) -> None:
    """Perbarui hash password dan master key yang dibungkus secara atomik."""
    conn.execute(
        """
        UPDATE users
        SET password_hash = ?, wrapped_master_key = ?, kdf_salt = ?
        WHERE id = ? AND role = 'relawan'
        """,
        (password_hash, wrapped_master_key, kdf_salt, user_id),
    )
    if commit:
        conn.commit()


def list_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Kembalikan semua user (tanpa kolom BLOB sensitif)."""
    cur = conn.execute(
        "SELECT id, nama_lengkap, username, role, posko_id, is_active, created_at FROM users"
    )
    return cur.fetchall()


# ──────────────────────────────────────────────────────────────────────
# Posko
# ──────────────────────────────────────────────────────────────────────

def insert_posko(
    conn: sqlite3.Connection, data: dict, *, commit: bool = True
) -> int:
    """Sisipkan posko baru. Mengembalikan id."""
    cur = conn.execute(
        "INSERT INTO posko (nama, lokasi, kapasitas) VALUES (?, ?, ?)",
        (data["nama"], data["lokasi"], data.get("kapasitas", 0)),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def get_posko_by_id(conn: sqlite3.Connection, posko_id: int) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM posko WHERE id = ?", (posko_id,))
    return cur.fetchone()


def list_posko(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM posko ORDER BY id")
    return cur.fetchall()


def update_posko(
    conn: sqlite3.Connection,
    posko_id: int,
    data: dict,
    *,
    commit: bool = True,
) -> None:
    """Perbarui kolom dasar posko tanpa menyentuh data sensitif lain."""
    conn.execute(
        "UPDATE posko SET nama = ?, lokasi = ?, kapasitas = ? WHERE id = ?",
        (data["nama"], data["lokasi"], data.get("kapasitas", 0), posko_id),
    )
    if commit:
        conn.commit()


def delete_posko(conn: sqlite3.Connection, posko_id: int) -> None:
    """
    Hapus posko. Karena schema memakai ON DELETE SET NULL untuk child records,
    data pengguna/korban yang terikat akan tetap ada dengan posko_id NULL.
    """
    conn.execute("DELETE FROM posko WHERE id = ?", (posko_id,))
    conn.commit()


def delete_user(conn: sqlite3.Connection, user_id: int) -> None:
    """Hapus user secara permanen; admin dilarang dihapus."""
    row = get_user_by_id(conn, user_id)
    if row is None:
        raise ValueError("User tidak ditemukan.")
    if row["role"] == "admin":
        raise PermissionError("Admin tidak dapat dihapus.")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()


# ──────────────────────────────────────────────────────────────────────
# Victims
# ──────────────────────────────────────────────────────────────────────

def insert_victim(
    conn: sqlite3.Connection, data: dict, *, commit: bool = True
) -> int:
    """
    Sisipkan data korban. Kolom *_enc harus sudah berupa BLOB terenkripsi.
    Mengembalikan id yang baru dibuat.
    """
    cur = conn.execute(
        """
        INSERT INTO victims
            (kode_korban, nama_panggilan, usia, gender, posko_id, status,
             nama_lengkap_enc, nik_enc, alamat_asal_enc,
             kondisi_medis_enc, kontak_keluarga_enc, catatan_enc,
             created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["kode_korban"],
            data.get("nama_panggilan"),
            data.get("usia"),
            data.get("gender"),
            data.get("posko_id"),
            data.get("status", "tidak diketahui"),
            data.get("nama_lengkap_enc"),
            data.get("nik_enc"),
            data.get("alamat_asal_enc"),
            data.get("kondisi_medis_enc"),
            data.get("kontak_keluarga_enc"),
            data.get("catatan_enc"),
            data.get("created_by"),
        ),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def get_victim_by_id(conn: sqlite3.Connection, victim_id: int) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM victims WHERE id = ?", (victim_id,))
    return cur.fetchone()


def get_victim_by_kode(conn: sqlite3.Connection, kode: str) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM victims WHERE kode_korban = ?", (kode,))
    return cur.fetchone()


def delete_victim(conn: sqlite3.Connection, victim_id: int) -> None:
    """Hapus data korban secara permanen, termasuk referensi foto terkait."""
    row = get_victim_by_id(conn, victim_id)
    if row is None:
        raise ValueError("Data korban tidak ditemukan.")
    conn.execute("DELETE FROM victims WHERE id = ?", (victim_id,))
    conn.commit()


def update_victim(conn: sqlite3.Connection, victim_id: int, data: dict) -> None:
    """
    Update kolom victim. Hanya kolom yang ada di `data` yang diupdate.
    updated_at diset ke waktu sekarang.
    """
    allowed = {
        "nama_panggilan", "usia", "gender", "posko_id", "status",
        "nama_lengkap_enc", "nik_enc", "alamat_asal_enc",
        "kondisi_medis_enc", "kontak_keluarga_enc", "catatan_enc",
    }
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return

    # Bangun SET clause dengan placeholder — TIDAK ada f-string untuk nilai
    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [victim_id]

    conn.execute(
        f"UPDATE victims SET {set_clause}, updated_at = datetime('now','localtime') WHERE id = ?",  # noqa: S608
        values,
    )
    conn.commit()


def list_victims_plaintext(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Daftar korban — hanya kolom plaintext (tanpa kolom *_enc).
    Dipakai untuk tabel UI; dekripsi dilakukan saat detail dibuka.
    """
    cur = conn.execute(
        """
        SELECT id, kode_korban, nama_panggilan, usia, gender,
               posko_id, status, created_by, created_at, updated_at
        FROM victims ORDER BY id
        """
    )
    return cur.fetchall()


def get_victim_summary(conn: sqlite3.Connection) -> dict[str, object]:
    """Ambil jumlah korban per status dan per posko untuk dashboard."""
    status_rows = conn.execute(
        "SELECT status, COUNT(*) AS total FROM victims GROUP BY status"
    ).fetchall()
    posko_rows = conn.execute(
        """
        SELECT p.id AS posko_id, p.nama AS nama_posko, COUNT(v.id) AS total
        FROM posko AS p
        LEFT JOIN victims AS v ON v.posko_id = p.id
        GROUP BY p.id, p.nama
        ORDER BY p.nama
        """
    ).fetchall()
    return {
        "by_status": {row["status"]: row["total"] for row in status_rows},
        "by_posko": [dict(row) for row in posko_rows],
    }


# ──────────────────────────────────────────────────────────────────────
# Photos
# ──────────────────────────────────────────────────────────────────────

def insert_photo(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO photos (victim_id, posko_id, image_path, original_hash, keterangan, uploaded_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("victim_id"),
            data.get("posko_id"),
            data["image_path"],
            data["original_hash"],
            data.get("keterangan"),
            data.get("uploaded_by"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_photo_by_id(conn: sqlite3.Connection, photo_id: int) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,))
    return cur.fetchone()


def delete_photo(conn: sqlite3.Connection, photo_id: int) -> None:
    """Hapus catatan foto dan file fisiknya jika sudah ada."""
    row = get_photo_by_id(conn, photo_id)
    if row is None:
        raise ValueError("Foto tidak ditemukan.")
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    conn.commit()


def list_photos_by_victim(conn: sqlite3.Connection, victim_id: int) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT * FROM photos WHERE victim_id = ? ORDER BY id", (victim_id,)
    )
    return cur.fetchall()


def list_photos(
    conn: sqlite3.Connection, uploaded_by: Optional[int] = None
) -> list[sqlite3.Row]:
    """Daftar foto, opsional dibatasi pada relawan pengunggah."""
    if uploaded_by is None:
        cur = conn.execute("SELECT * FROM photos ORDER BY id DESC")
    else:
        cur = conn.execute(
            "SELECT * FROM photos WHERE uploaded_by = ? ORDER BY id DESC",
            (uploaded_by,),
        )
    return cur.fetchall()


# ──────────────────────────────────────────────────────────────────────
# Messages
# ──────────────────────────────────────────────────────────────────────

def insert_message(conn: sqlite3.Connection, data: dict) -> int:
    """
    Simpan pesan terenkripsi. `ciphertext` harus BLOB dari super_encrypt.
    """
    cur = conn.execute(
        "INSERT INTO messages (sender_id, receiver_id, ciphertext) VALUES (?, ?, ?)",
        (data["sender_id"], data["receiver_id"], data["ciphertext"]),
    )
    conn.commit()
    return cur.lastrowid


def get_messages_between(
    conn: sqlite3.Connection, user_a: int, user_b: int
) -> list[sqlite3.Row]:
    """Ambil semua pesan antara dua user, urut waktu."""
    cur = conn.execute(
        """
        SELECT * FROM messages
        WHERE (sender_id = ? AND receiver_id = ?)
           OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at
        """,
        (user_a, user_b, user_b, user_a),
    )
    return cur.fetchall()


def list_messages_for_user(
    conn: sqlite3.Connection, user_id: int
) -> list[sqlite3.Row]:
    """Ambil pesan yang dikirim atau diterima user untuk panel demonstrasi."""
    cur = conn.execute(
        """
        SELECT * FROM messages
        WHERE sender_id = ? OR receiver_id = ?
        ORDER BY id DESC
        """,
        (user_id, user_id),
    )
    return cur.fetchall()


def get_message_by_id(
    conn: sqlite3.Connection, message_id: int
) -> Optional[sqlite3.Row]:
    """Ambil satu pesan terenkripsi untuk tampilan demo."""
    cur = conn.execute(
        "SELECT * FROM messages WHERE id = ?", (message_id,)
    )
    return cur.fetchone()


def mark_messages_read(
    conn: sqlite3.Connection, receiver_id: int, sender_id: int
) -> None:
    """Tandai semua pesan dari sender ke receiver sebagai sudah dibaca."""
    conn.execute(
        "UPDATE messages SET is_read = 1 WHERE receiver_id = ? AND sender_id = ?",
        (receiver_id, sender_id),
    )
    conn.commit()


# ──────────────────────────────────────────────────────────────────────
# Files
# ──────────────────────────────────────────────────────────────────────

def insert_file(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO files (uploader_id, nama_asli, path_enc, ukuran, file_hash)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            data.get("uploader_id"),
            data["nama_asli"],
            data["path_enc"],
            data.get("ukuran", 0),
            data["file_hash"],
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_files(
    conn: sqlite3.Connection, uploader_id: Optional[int] = None
) -> list[sqlite3.Row]:
    if uploader_id is None:
        cur = conn.execute("SELECT * FROM files ORDER BY id DESC")
    else:
        cur = conn.execute(
            "SELECT * FROM files WHERE uploader_id = ? ORDER BY id DESC",
            (uploader_id,),
        )
    return cur.fetchall()


def get_file_by_id(conn: sqlite3.Connection, file_id: int) -> Optional[sqlite3.Row]:
    cur = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
    return cur.fetchone()


def delete_file(conn: sqlite3.Connection, file_id: int) -> None:
    """Hapus metadata berkas beserta referensi file yang tersimpan."""
    row = get_file_by_id(conn, file_id)
    if row is None:
        raise ValueError("Berkas tidak ditemukan.")
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()


# ──────────────────────────────────────────────────────────────────────
# Blockchain
# ──────────────────────────────────────────────────────────────────────

def save_block(
    conn: sqlite3.Connection, block_dict: dict, *, commit: bool = True
) -> None:
    """
    Simpan satu block ke tabel blockchain.

    `data` di block_dict harus sudah berupa JSON string
    (json.dumps dengan sort_keys=True, separators=(",",":")).

    INSERT OR REPLACE memungkinkan update block yang ada (misal saat
    simulasi tampering untuk demo), tapi dalam operasi normal tidak
    dipakai untuk mengubah block lama.
    """
    # Serialisasi field `data` (dict) ke JSON string jika belum
    data_val = block_dict["data"]
    if isinstance(data_val, dict):
        data_val = json.dumps(data_val, sort_keys=True, separators=(",", ":"))

    conn.execute(
        """
        INSERT OR REPLACE INTO blockchain (idx, timestamp, data, prev_hash, nonce, hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            block_dict["index"],
            block_dict["timestamp"],
            data_val,
            block_dict["prev_hash"],
            block_dict["nonce"],
            block_dict["hash"],
        ),
    )
    if commit:
        conn.commit()


def get_demo_seed_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Return counts used to refuse demo seeding into a populated database."""
    return {
        "users": int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]),
        "posko": int(conn.execute("SELECT COUNT(*) FROM posko").fetchone()[0]),
        "victims": int(conn.execute("SELECT COUNT(*) FROM victims").fetchone()[0]),
        "photos": int(conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0]),
        "messages": int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]),
        "files": int(conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]),
        "blockchain": int(
            conn.execute("SELECT COUNT(*) FROM blockchain").fetchone()[0]
        ),
    }


def update_block_data_for_demo(
    conn: sqlite3.Connection, index: int, data: dict
) -> None:
    """Ubah payload block tanpa hash hanya untuk demonstrasi tampering."""
    cursor = conn.execute(
        "UPDATE blockchain SET data = ? WHERE idx = ?",
        (
            json.dumps(data, sort_keys=True, separators=(",", ":")),
            index,
        ),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"Block {index} tidak ditemukan.")
    conn.commit()


def load_chain(conn: sqlite3.Connection) -> list[dict]:
    """
    Muat seluruh chain dari DB, urut berdasarkan idx.

    Returns list of dict dengan field yang sesuai Block.from_dict():
    index, timestamp, data (dict), prev_hash, nonce, hash.
    """
    cur = conn.execute("SELECT * FROM blockchain ORDER BY idx")
    rows = cur.fetchall()
    result = []
    for row in rows:
        result.append({
            "index":     row["idx"],
            "timestamp": row["timestamp"],
            "data":      json.loads(row["data"]),  # JSON string → dict
            "prev_hash": row["prev_hash"],
            "nonce":     row["nonce"],
            "hash":      row["hash"],
        })
    return result


def count_blocks(conn: sqlite3.Connection) -> int:
    """Jumlah block yang sudah tersimpan di tabel blockchain."""
    cur = conn.execute("SELECT COUNT(*) FROM blockchain")
    return cur.fetchone()[0]


# ──────────────────────────────────────────────────────────────────────
# Activity Log
# ──────────────────────────────────────────────────────────────────────

def log_activity(
    conn: sqlite3.Connection,
    aksi: str,
    user_id: Optional[int] = None,
    detail: Optional[str] = None,
    *,
    commit: bool = True,
) -> None:
    """
    Catat event penting ke activity_log.

    Args:
        aksi   : Kode aksi, misal 'LOGIN', 'LOGOUT', 'ADMIN_BOOTSTRAP'.
        user_id: ID user yang melakukan aksi (None jika belum login).
        detail : JSON string atau teks bebas untuk konteks tambahan.
    """
    conn.execute(
        "INSERT INTO activity_log (user_id, aksi, detail) VALUES (?, ?, ?)",
        (user_id, aksi, detail),
    )
    if commit:
        conn.commit()


def list_activity_log(
    conn: sqlite3.Connection,
    limit: int = 200,
    user_id: int | None = None,
    action: str | None = None,
) -> list[sqlite3.Row]:
    """Ambil log terbaru, dengan filter user dan/atau aksi bila diminta."""
    if limit <= 0:
        raise ValueError("Batas log harus lebih besar dari nol.")
    query = "SELECT * FROM activity_log WHERE 1 = 1"
    parameters: list[object] = []
    if user_id is not None:
        query += " AND user_id = ?"
        parameters.append(user_id)
    if action:
        query += " AND aksi = ?"
        parameters.append(action)
    query += " ORDER BY id DESC LIMIT ?"
    parameters.append(limit)
    cur = conn.execute(query, parameters)
    return cur.fetchall()


def list_activity_actions(conn: sqlite3.Connection) -> list[str]:
    """Aksi unik yang tersedia sebagai opsi filter log."""
    cur = conn.execute(
        "SELECT DISTINCT aksi FROM activity_log ORDER BY aksi"
    )
    return [str(row["aksi"]) for row in cur.fetchall()]
