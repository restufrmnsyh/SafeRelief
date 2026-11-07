"""
SafeRelief - Secure Store (secure_store.py)

Satu-satunya tempat yang boleh mengenkripsi/mendekripsi data sebelum
disimpan atau setelah dibaca dari database.

Prinsip desain:
- db_key diterima sebagai PARAMETER — modul ini tidak mengimpor session
  dan tidak tahu cara mendapatkan kunci. Kunci dikirim dari lapisan atas
  (auth/session.py) saat dipanggil.
- Enkripsi kolom: AES-256-GCM via crypto.aes_module.
  BLOB format: nonce(12) + ciphertext + tag(16).
- Blockchain dikelola via crypto.blockchain.Blockchain; persistensi
  dilakukan lewat database.db. TIDAK pernah membuat genesis baru jika
  tabel blockchain sudah berisi baris.
- Pesan chat disimpan sebagai SATU BLOB utuh dari crypto.super_encrypt;
  modul ini hanya menyimpan/mengambil blob — enkripsi/dekripsi pesan
  dilakukan oleh pemanggil dengan super_encrypt.
"""

import sqlite3
from typing import Optional

from crypto import aes_module
from crypto.blockchain import Blockchain
from database import db


# ──────────────────────────────────────────────────────────────────────
# Helper enkripsi kolom
# ──────────────────────────────────────────────────────────────────────

def _enc(value: Optional[str], db_key: bytes) -> Optional[bytes]:
    """
    Enkripsi string ke BLOB AES-GCM.
    Kembalikan None jika value None (kolom opsional).
    """
    if value is None:
        return None
    return aes_module.encrypt(value.encode("utf-8"), db_key)


def _dec(blob: Optional[bytes], db_key: bytes) -> Optional[str]:
    """
    Dekripsi BLOB AES-GCM ke string.
    Kembalikan None jika blob None.
    """
    if blob is None:
        return None
    return aes_module.decrypt(bytes(blob), db_key).decode("utf-8")


# ──────────────────────────────────────────────────────────────────────
# Victims
# ──────────────────────────────────────────────────────────────────────

# Kolom yang dienkripsi untuk tabel victims
_VICTIM_ENC_COLS = [
    "nama_lengkap",
    "nik",
    "alamat_asal",
    "kondisi_medis",
    "kontak_keluarga",
    "catatan",
]


def add_victim(
    conn: sqlite3.Connection,
    db_key: bytes,
    data: dict,
) -> int:
    """
    Enkripsi kolom sensitif lalu simpan data korban ke DB.

    Args:
        conn  : Koneksi database.
        db_key: Kunci AES 32 byte (turunan dari master key, label b"db").
        data  : Dict dengan kolom victims. Kolom sensitif:
                nama_lengkap, nik, alamat_asal, kondisi_medis,
                kontak_keluarga, catatan (semuanya string atau None).

    Returns:
        id victim yang baru dibuat.
    """
    row: dict = {
        "kode_korban":  data["kode_korban"],
        "nama_panggilan": data.get("nama_panggilan"),
        "usia":         data.get("usia"),
        "gender":       data.get("gender"),
        "posko_id":     data.get("posko_id"),
        "status":       data.get("status", "tidak diketahui"),
        "created_by":   data.get("created_by"),
    }
    # Enkripsi tiap kolom sensitif
    for col in _VICTIM_ENC_COLS:
        row[f"{col}_enc"] = _enc(data.get(col), db_key)

    return db.insert_victim(conn, row)


def get_victim(
    conn: sqlite3.Connection,
    db_key: bytes,
    victim_id: int,
) -> Optional[dict]:
    """
    Ambil dan dekripsi data korban berdasarkan id.

    Returns:
        Dict dengan semua kolom (kolom sensitif sudah terdekripsi),
        atau None jika tidak ditemukan.
    """
    row = db.get_victim_by_id(conn, victim_id)
    if row is None:
        return None
    return _decrypt_victim_row(row, db_key)


def get_victim_by_kode(
    conn: sqlite3.Connection,
    db_key: bytes,
    kode: str,
) -> Optional[dict]:
    """Ambil dan dekripsi data korban berdasarkan kode_korban."""
    row = db.get_victim_by_kode(conn, kode)
    if row is None:
        return None
    return _decrypt_victim_row(row, db_key)


def update_victim(
    conn: sqlite3.Connection,
    db_key: bytes,
    victim_id: int,
    data: dict,
) -> None:
    """
    Enkripsi kolom sensitif yang ada di `data` lalu update victim.

    Hanya kolom yang disertakan di `data` yang diupdate.
    """
    update_row: dict = {}

    # Kolom plaintext yang boleh diupdate
    for col in ("nama_panggilan", "usia", "gender", "posko_id", "status"):
        if col in data:
            update_row[col] = data[col]

    # Kolom sensitif → enkripsi
    for col in _VICTIM_ENC_COLS:
        if col in data:
            update_row[f"{col}_enc"] = _enc(data[col], db_key)

    db.update_victim(conn, victim_id, update_row)


def list_victims(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """
    Daftar korban — hanya kolom plaintext.
    Kolom *_enc tidak dikembalikan; dekripsi dilakukan saat detail dibuka.
    """
    return db.list_victims_plaintext(conn)


def get_dashboard_summary(conn: sqlite3.Connection) -> dict[str, object]:
    """Ambil ringkasan dashboard lewat lapisan penyimpanan aplikasi."""
    return db.get_victim_summary(conn)


def list_posko(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Ambil daftar posko untuk tampilan aplikasi."""
    return db.list_posko(conn)


def _decrypt_victim_row(row: sqlite3.Row, db_key: bytes) -> dict:
    """
    Konversi Row ke dict dengan kolom *_enc terdekripsi menjadi string.
    """
    d = dict(row)
    for col in _VICTIM_ENC_COLS:
        blob = d.pop(f"{col}_enc", None)
        d[col] = _dec(blob, db_key)
    return d


# ──────────────────────────────────────────────────────────────────────
# Face encoding (users.face_encoding_enc)
# ──────────────────────────────────────────────────────────────────────

def save_face_encoding(
    conn: sqlite3.Connection,
    db_key: bytes,
    user_id: int,
    encoding: bytes,
    *,
    commit: bool = True,
) -> None:
    """
    Enkripsi face embedding lalu simpan ke kolom face_encoding_enc.

    Args:
        encoding: numpy array yang sudah di-serialize ke bytes
                  (misal: array.tobytes() atau pickle).
    """
    encrypted = aes_module.encrypt(encoding, db_key)
    db.update_user_face(conn, user_id, encrypted, commit=commit)


def load_face_encoding(
    conn: sqlite3.Connection,
    db_key: bytes,
    user_id: int,
) -> Optional[bytes]:
    """
    Ambil dan dekripsi face embedding.

    Returns:
        Bytes embedding, atau None jika belum terdaftar.
    """
    row = db.get_user_by_id(conn, user_id)
    if row is None or row["face_encoding_enc"] is None:
        return None
    return aes_module.decrypt(bytes(row["face_encoding_enc"]), db_key)


# ──────────────────────────────────────────────────────────────────────
# Messages (chat)
# ──────────────────────────────────────────────────────────────────────

def save_message(
    conn: sqlite3.Connection,
    sender_id: int,
    receiver_id: int,
    ciphertext_blob: bytes,
) -> int:
    """
    Simpan pesan chat. ciphertext_blob adalah output langsung dari
    crypto.super_encrypt.encrypt() — satu BLOB utuh (IV + ct + HMAC).

    Enkripsi/dekripsi dilakukan di lapisan pemanggil; modul ini hanya
    menyimpan blob mentah.

    Returns:
        id pesan baru.
    """
    sender = db.get_user_by_id(conn, sender_id)
    receiver = db.get_user_by_id(conn, receiver_id)
    if sender is None or receiver is None:
        raise ValueError("Akun percakapan tidak ditemukan.")
    if {sender["role"], receiver["role"]} != {"admin", "relawan"}:
        raise PermissionError("Chat hanya tersedia antara admin dan relawan.")
    if not sender["is_active"] or not receiver["is_active"]:
        raise PermissionError("Akun percakapan tidak aktif.")
    return db.insert_message(conn, {
        "sender_id":   sender_id,
        "receiver_id": receiver_id,
        "ciphertext":  ciphertext_blob,
    })


def get_messages(
    conn: sqlite3.Connection,
    user_a: int,
    user_b: int,
) -> list[sqlite3.Row]:
    """
    Ambil semua pesan antara dua user. Blob belum didekripsi.
    Dekripsi dilakukan di UI dengan super_encrypt.decrypt().
    """
    sender = db.get_user_by_id(conn, user_a)
    partner = db.get_user_by_id(conn, user_b)
    if sender is None or partner is None:
        raise ValueError("Akun percakapan tidak ditemukan.")
    if {sender["role"], partner["role"]} != {"admin", "relawan"}:
        raise PermissionError("Chat hanya tersedia antara admin dan relawan.")
    return db.get_messages_between(conn, user_a, user_b)


def list_chat_contacts(
    conn: sqlite3.Connection, user_id: int, role: str
) -> list[dict[str, object]]:
    """Kembalikan hanya kontak yang diizinkan untuk chat admin-relawan."""
    users = [dict(row) for row in db.list_users(conn)]
    current = next((user for user in users if user["id"] == user_id), None)
    if current is None or current["role"] != role:
        raise PermissionError("Identitas sesi tidak cocok dengan akun database.")
    if role == "admin":
        return [
            user for user in users
            if user["role"] == "relawan"
        ]
    if role == "relawan":
        admins = [user for user in users if user["role"] == "admin"]
        if len(admins) != 1:
            raise ValueError("Akun admin belum tersedia.")
        return admins
    raise PermissionError("Peran ini tidak diizinkan menggunakan chat.")


def list_photos(
    conn: sqlite3.Connection, user_id: int, role: str
) -> list[sqlite3.Row]:
    """Admin melihat semua dokumentasi; relawan hanya melihat unggahannya."""
    user = db.get_user_by_id(conn, user_id)
    if user is None or user["role"] != role:
        raise PermissionError("Identitas sesi tidak cocok dengan akun database.")
    if role == "admin":
        return db.list_photos(conn)
    if role == "relawan":
        return db.list_photos(conn, uploaded_by=user_id)
    raise PermissionError("Peran ini tidak diizinkan melihat dokumentasi foto.")


def save_photo(
    conn: sqlite3.Connection,
    *,
    user_id: int,
    victim_id: int | None,
    posko_id: int | None,
    image_path: str,
    original_hash: str,
    keterangan: str,
) -> int:
    """Simpan metadata foto setelah memastikan pengunggah adalah relawan."""
    user = db.get_user_by_id(conn, user_id)
    if user is None or user["role"] != "relawan":
        raise PermissionError("Hanya relawan yang dapat mengunggah foto.")
    return db.insert_photo(conn, {
        "victim_id": victim_id,
        "posko_id": posko_id,
        "image_path": image_path,
        "original_hash": original_hash,
        "keterangan": keterangan,
        "uploaded_by": user_id,
    })


def list_files(
    conn: sqlite3.Connection, user_id: int, role: str
) -> list[sqlite3.Row]:
    """Admin melihat semua berkas; relawan hanya melihat unggahannya."""
    user = db.get_user_by_id(conn, user_id)
    if user is None or user["role"] != role:
        raise PermissionError("Identitas sesi tidak cocok dengan akun database.")
    if role == "admin":
        return db.list_files(conn)
    if role == "relawan":
        return db.list_files(conn, uploader_id=user_id)
    raise PermissionError("Peran ini tidak diizinkan melihat berkas.")


def save_file(
    conn: sqlite3.Connection,
    *,
    uploader_id: int,
    nama_asli: str,
    path_enc: str,
    ukuran: int,
    file_hash: str,
) -> int:
    """Simpan metadata berkas; enkripsi file dilakukan oleh lapisan UI."""
    user = db.get_user_by_id(conn, uploader_id)
    if user is None or user["role"] != "relawan":
        raise PermissionError("Hanya relawan yang dapat mengunggah berkas.")
    return db.insert_file(conn, {
        "uploader_id": uploader_id,
        "nama_asli": nama_asli,
        "path_enc": path_enc,
        "ukuran": ukuran,
        "file_hash": file_hash,
    })


def get_file_for_admin(
    conn: sqlite3.Connection, user_id: int, file_id: int
) -> Optional[sqlite3.Row]:
    """Hanya admin boleh memperoleh metadata berkas untuk proses dekripsi."""
    user = db.get_user_by_id(conn, user_id)
    if user is None or user["role"] != "admin":
        raise PermissionError("Hanya admin yang dapat mengunduh berkas.")
    return db.get_file_by_id(conn, file_id)


def log_activity(
    conn: sqlite3.Connection,
    action: str,
    *,
    user_id: int,
    detail: str | None = None,
) -> None:
    """Catat event UI melalui API penyimpanan tanpa menulis SQL di halaman."""
    db.log_activity(conn, action, user_id=user_id, detail=detail)


# ──────────────────────────────────────────────────────────────────────
# Blockchain
# ──────────────────────────────────────────────────────────────────────

def get_or_create_chain(conn: sqlite3.Connection) -> Blockchain:
    """
    Muat chain dari DB, atau buat baru jika tabel kosong.

    Aturan penting:
    - Jika tabel blockchain KOSONG → buat Blockchain() baru (genesis
      dibuat otomatis) dan langsung simpan genesis ke DB.
    - Jika tabel blockchain BERISI BARIS → muat dengan
      Blockchain.load_from_list(). TIDAK membuat genesis baru.

    Pemisahan ini mencegah genesis ganda jika dipanggil berkali-kali.

    Returns:
        Blockchain yang siap dipakai.
    """
    if db.count_blocks(conn) == 0:
        # Tabel kosong → chain baru, genesis otomatis terbuat
        bc = Blockchain()
        # Simpan genesis ke DB sekarang
        db.save_block(conn, bc.chain[0].to_dict())
        return bc

    # Tabel sudah berisi → muat dari DB
    chain_data = db.load_chain(conn)
    return Blockchain.load_from_list(chain_data)


def append_block(conn: sqlite3.Connection, data: dict) -> None:
    """
    Tambah block distribusi bantuan ke chain dan simpan ke DB.

    Proses:
    1. Muat chain dari DB
    2. add_block(data) — validasi + PoW
    3. Simpan block baru ke DB

    Args:
        data: Dict distribusi (jenis, jumlah, dari, ke, petugas).
              Semua key harus str.
    """
    bc = get_or_create_chain(conn)
    new_block = bc.add_block(data)
    db.save_block(conn, new_block.to_dict())


def load_blockchain(conn: sqlite3.Connection) -> Blockchain:
    """
    Muat blockchain dari DB untuk validasi atau tampilan riwayat.
    Alias publik dari get_or_create_chain().
    """
    return get_or_create_chain(conn)
