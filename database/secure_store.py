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
  inbox mengenkripsi/dekripsi di lapisan pemanggil, sementara helper
  panel demo memastikan izin sebelum menampilkan plaintext pesan.
"""

import sqlite3
from typing import Optional

from crypto import aes_module, super_encrypt
from crypto.blockchain import Blockchain
from database import db


def require_active_user(
    conn: sqlite3.Connection, user_id: int, role: str | None = None
) -> sqlite3.Row:
    """Re-check database account state before every authenticated action."""
    user = db.get_user_by_id(conn, user_id)
    if user is None or not user["is_active"]:
        raise PermissionError("Akun tidak ditemukan atau sudah diblokir.")
    if role is not None and user["role"] != role:
        raise PermissionError("Peran akun tidak diizinkan untuk tindakan ini.")
    return user


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
    *,
    commit: bool = True,
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

    return db.insert_victim(conn, row, commit=commit)


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
    sender = require_active_user(conn, sender_id)
    receiver = require_active_user(conn, receiver_id)
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
    sender = require_active_user(conn, user_a)
    partner = require_active_user(conn, user_b)
    if {sender["role"], partner["role"]} != {"admin", "relawan"}:
        raise PermissionError("Chat hanya tersedia antara admin dan relawan.")
    return db.get_messages_between(conn, user_a, user_b)


def list_chat_contacts(
    conn: sqlite3.Connection, user_id: int, role: str
) -> list[dict[str, object]]:
    """Kembalikan hanya kontak yang diizinkan untuk chat admin-relawan."""
    users = [dict(row) for row in db.list_users(conn)]
    current = dict(require_active_user(conn, user_id, role))
    if role == "admin":
        return [
            user for user in users
            if user["role"] == "relawan" and user["is_active"]
        ]
    if role == "relawan":
        admins = [
            user for user in users
            if user["role"] == "admin" and user["is_active"]
        ]
        if len(admins) != 1:
            raise ValueError("Akun admin belum tersedia.")
        return admins
    raise PermissionError("Peran ini tidak diizinkan menggunakan chat.")


def list_photos(
    conn: sqlite3.Connection, user_id: int, role: str
) -> list[sqlite3.Row]:
    """Admin melihat semua dokumentasi; relawan hanya melihat unggahannya."""
    user = require_active_user(conn, user_id, role)
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
    require_active_user(conn, user_id, "relawan")
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
    require_active_user(conn, user_id, role)
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
    require_active_user(conn, uploader_id, "relawan")
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
    require_active_user(conn, user_id, "admin")
    return db.get_file_by_id(conn, file_id)


def log_activity(
    conn: sqlite3.Connection,
    action: str,
    *,
    user_id: int,
    detail: str | None = None,
) -> None:
    """Catat event UI melalui API penyimpanan tanpa menulis SQL di halaman."""
    require_active_user(conn, user_id)
    db.log_activity(conn, action, user_id=user_id, detail=detail)


def list_activity_users(
    conn: sqlite3.Connection, requester_id: int
) -> list[dict[str, object]]:
    """Daftar user aman untuk filter log, hanya tersedia bagi admin."""
    require_active_user(conn, requester_id, "admin")
    return [
        dict(row)
        for row in db.list_users(conn)
    ]


def list_activity_actions(
    conn: sqlite3.Connection, requester_id: int
) -> list[str]:
    """Daftar opsi filter aksi, hanya tersedia bagi admin."""
    require_active_user(conn, requester_id, "admin")
    return db.list_activity_actions(conn)


def list_activity_log(
    conn: sqlite3.Connection,
    requester_id: int,
    *,
    user_id: int | None = None,
    action: str | None = None,
    limit: int = 500,
) -> list[sqlite3.Row]:
    """Ambil log terbaru dan filter server-side setelah otorisasi admin."""
    require_active_user(conn, requester_id, "admin")
    if user_id is not None:
        if db.get_user_by_id(conn, user_id) is None:
            raise ValueError("User filter tidak ditemukan.")
    return db.list_activity_log(
        conn, limit=limit, user_id=user_id, action=action
    )


def get_aid_chain(
    conn: sqlite3.Connection, user_id: int, role: str
) -> Blockchain:
    """Muat riwayat bantuan untuk admin dan relawan aktif."""
    require_active_user(conn, user_id, role)
    if role not in ("admin", "relawan"):
        raise PermissionError("Peran ini tidak diizinkan melihat riwayat bantuan.")
    return load_blockchain(conn)


def append_aid_block(
    conn: sqlite3.Connection,
    user_id: int,
    data: dict,
    *,
    commit: bool = True,
) -> None:
    """Catat distribusi bantuan hanya jika pemanggil adalah admin aktif."""
    require_active_user(conn, user_id, "admin")
    required = ("jenis", "jumlah", "dari", "ke", "petugas")
    if any(key not in data for key in required):
        raise ValueError("Data distribusi belum lengkap.")
    if not isinstance(data["jumlah"], int) or isinstance(data["jumlah"], bool):
        raise ValueError("Jumlah bantuan harus bilangan bulat.")
    if data["jumlah"] <= 0:
        raise ValueError("Jumlah bantuan harus lebih besar dari nol.")
    chain = get_or_create_chain(conn, commit=commit)
    if not chain.is_valid()[0]:
        raise ValueError("Chain tidak valid; distribusi baru tidak dapat dicatat.")
    append_block(conn, data, commit=commit)
    db.log_activity(
        conn,
        "AID_DISTRIBUTION_RECORDED",
        user_id=user_id,
        detail=f"jenis={data['jenis']}; jumlah={data['jumlah']}",
        commit=commit,
    )


def simulate_aid_tampering(
    conn: sqlite3.Connection, user_id: int, block_index: int
) -> int:
    """Ubah jumlah di block non-genesis tanpa hash untuk demo admin saja."""
    require_active_user(conn, user_id, "admin")
    if block_index <= 0:
        raise ValueError("Genesis block tidak boleh dipilih untuk simulasi.")
    chain = load_blockchain(conn)
    if block_index >= len(chain.chain):
        raise ValueError("Block yang dipilih tidak ditemukan.")
    block = chain.chain[block_index]
    amount = block.data.get("jumlah")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise ValueError("Block tidak memiliki jumlah numerik untuk diubah.")

    changed_data = dict(block.data)
    changed_data["jumlah"] = amount + 1
    db.update_block_data_for_demo(conn, block_index, changed_data)
    db.log_activity(
        conn,
        "DEMO_AID_TAMPERING",
        user_id=user_id,
        detail=f"block_index={block_index}",
    )
    return block_index


def list_demo_victims(
    conn: sqlite3.Connection, user_id: int
) -> list[sqlite3.Row]:
    """Daftar korban aman untuk demo ciphertext/plaintext bagi admin aktif."""
    require_active_user(conn, user_id, "admin")
    return db.list_victims_plaintext(conn)


def list_demo_messages(
    conn: sqlite3.Connection, user_id: int
) -> list[sqlite3.Row]:
    """Daftar pesan untuk panel demonstrasi admin aktif."""
    require_active_user(conn, user_id, "admin")
    return db.list_messages_for_user(conn, user_id)


def decrypt_demo_message(
    conn: sqlite3.Connection,
    user_id: int,
    message_id: int,
    *,
    vigenere_key: str,
    blowfish_enc_key: bytes,
    blowfish_mac_key: bytes,
) -> str:
    """Dekripsi hanya pesan milik percakapan admin-relawan yang requester ikuti."""
    requester = require_active_user(conn, user_id, "admin")
    message = db.get_message_by_id(conn, message_id)
    if message is None:
        raise ValueError("Pesan demonstrasi tidak ditemukan.")
    if user_id not in (message["sender_id"], message["receiver_id"]):
        raise PermissionError("Pesan bukan bagian dari percakapan user aktif.")
    sender = require_active_user(conn, int(message["sender_id"]))
    receiver = require_active_user(conn, int(message["receiver_id"]))
    if {sender["role"], receiver["role"]} != {"admin", "relawan"}:
        raise PermissionError("Chat hanya tersedia antara admin dan relawan.")
    return super_encrypt.decrypt(
        bytes(message["ciphertext"]),
        vigenere_key,
        blowfish_enc_key,
        blowfish_mac_key,
    )

# ──────────────────────────────────────────────────────────────────────
# Blockchain
# ──────────────────────────────────────────────────────────────────────

def get_or_create_chain(
    conn: sqlite3.Connection, *, commit: bool = True
) -> Blockchain:
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
        db.save_block(conn, bc.chain[0].to_dict(), commit=commit)
        return bc

    # Tabel sudah berisi → muat dari DB
    chain_data = db.load_chain(conn)
    return Blockchain.load_from_list(chain_data)


def append_block(
    conn: sqlite3.Connection, data: dict, *, commit: bool = True
) -> None:
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
    bc = get_or_create_chain(conn, commit=commit)
    new_block = bc.add_block(data)
    db.save_block(conn, new_block.to_dict(), commit=commit)


def load_blockchain(conn: sqlite3.Connection) -> Blockchain:
    """
    Muat blockchain dari DB untuk validasi atau tampilan riwayat.
    Alias publik dari get_or_create_chain().
    """
    return get_or_create_chain(conn)
