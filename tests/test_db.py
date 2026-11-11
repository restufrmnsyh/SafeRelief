"""
SafeRelief - Tes Database Layer (Tahap 3)

Semua tes menggunakan tmp_path dari pytest — tidak menyentuh data/ asli.

Kriteria lulus:
- Admin kedua ditolak oleh DB (partial unique index one_admin_only)
- dongle_serial duplikat ditolak (UNIQUE constraint)
- role atau status tidak valid ditolak (CHECK constraint)
- Korban tersimpan terenkripsi (kolom nik_enc bukan plaintext)
- Korban terbaca kembali dengan kunci benar
- Kunci salah gagal (InvalidTag)
- Foreign key aktif (hapus posko yang masih dipakai ditolak)
- Blockchain: simpan, muat ulang, is_valid True
- Muat ulang dua kali tidak membuat genesis kedua
- SQL injection: username berisi ' OR '1'='1 diperlakukan sebagai teks
"""

import json
import os
import sqlite3

import pytest
from cryptography.exceptions import InvalidTag

from database import db, secure_store


# ─────────────────────────────────────────────────────────────────────
# Fixture: database sementara + kunci test
# ─────────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    """DB di direktori sementara, sudah ter-init."""
    path = tmp_path / "test.db"
    db.init_db(path)
    return path


@pytest.fixture()
def conn(tmp_db):
    """Koneksi ke DB sementara; otomatis ditutup setelah tes."""
    with db.get_connection(tmp_db) as c:
        yield c


@pytest.fixture()
def db_key():
    """Kunci AES-256 acak untuk tes; berbeda tiap tes."""
    return os.urandom(32)


# ─────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────

def _make_user(conn, username="relawan1", role="relawan", dongle_serial=None):
    """Sisipkan user minimal untuk keperluan tes."""
    return db.insert_user(conn, {
        "nama_lengkap": f"User {username}",
        "username": username,
        "password_hash": "hash_dummy",
        "role": role,
        "dongle_serial": dongle_serial,
    })


def _make_posko(conn, nama="Posko A"):
    return db.insert_posko(conn, {"nama": nama, "lokasi": "Lokasi A", "kapasitas": 50})


# ─────────────────────────────────────────────────────────────────────
# Tes: Constraints DB
# ─────────────────────────────────────────────────────────────────────

class TestConstraints:

    def test_admin_second_rejected(self, conn):
        """Admin kedua harus ditolak oleh partial unique index."""
        _make_user(conn, username="admin1", role="admin")
        with pytest.raises(sqlite3.IntegrityError):
            _make_user(conn, username="admin2", role="admin")

    def test_duplicate_username_rejected(self, conn):
        """Username duplikat harus ditolak (UNIQUE)."""
        _make_user(conn, username="user_sama")
        with pytest.raises(sqlite3.IntegrityError):
            _make_user(conn, username="user_sama")

    def test_duplicate_dongle_serial_rejected(self, conn):
        """dongle_serial duplikat harus ditolak (UNIQUE)."""
        _make_user(conn, username="r1", dongle_serial="SERIAL001")
        with pytest.raises(sqlite3.IntegrityError):
            _make_user(conn, username="r2", dongle_serial="SERIAL001")

    def test_null_dongle_serial_allowed_multiple(self, conn):
        """NULL pada dongle_serial boleh lebih dari satu (belum punya dongle)."""
        _make_user(conn, username="r1", dongle_serial=None)
        _make_user(conn, username="r2", dongle_serial=None)  # tidak boleh error

    def test_invalid_role_rejected(self, conn):
        """Role selain 'admin'/'relawan' harus ditolak (CHECK)."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_user(conn, {
                "nama_lengkap": "X",
                "username": "hacker",
                "password_hash": "h",
                "role": "superuser",     # tidak valid
            })

    def test_invalid_victim_status_rejected(self, conn):
        """Status korban di luar set yang diizinkan harus ditolak (CHECK)."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_victim(conn, {
                "kode_korban": "K001",
                "status": "alien",        # tidak valid
            })

    def test_invalid_is_active_rejected(self, conn):
        """is_active selain 0/1 harus ditolak (CHECK)."""
        uid = _make_user(conn, username="r_active")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE users SET is_active = 5 WHERE id = ?", (uid,)
            )
            conn.commit()

    def test_foreign_key_active(self, conn):
        """
        Hapus posko yang masih direferensikan users atau victims harus
        ditolak jika foreign key ON DELETE RESTRICT (bukan CASCADE/SET NULL).

        Schema pakai ON DELETE SET NULL untuk posko_id di users dan victims,
        jadi hapus posko tidak ditolak — tapi victim dengan posko yang dihapus
        memiliki posko_id = NULL.

        Tes ini memverifikasi bahwa foreign key AKTIF dengan cara berbeda:
        hapus user yang masih direferensikan messages (ON DELETE CASCADE di
        messages.sender_id) harus menghapus pesannya juga.
        """
        uid = _make_user(conn, username="pengirim")
        uid2 = _make_user(conn, username="penerima")
        db.insert_message(conn, {
            "sender_id": uid,
            "receiver_id": uid2,
            "ciphertext": b"blob",
        })
        # Hapus sender → pesan ikut terhapus (CASCADE)
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        msgs = db.get_messages_between(conn, uid, uid2)
        assert len(msgs) == 0

    def test_foreign_key_posko_set_null(self, conn):
        """
        Hapus posko mengubah posko_id user menjadi NULL (ON DELETE SET NULL).
        Ini membuktikan foreign key aktif dan bekerja sesuai schema.
        """
        posko_id = _make_posko(conn)
        uid = db.insert_user(conn, {
            "nama_lengkap": "R",
            "username": "r_posko",
            "password_hash": "h",
            "role": "relawan",
            "posko_id": posko_id,
        })
        # Hapus posko → posko_id user menjadi NULL
        db.delete_posko(conn, posko_id)
        row = db.get_user_by_id(conn, uid)
        assert row["posko_id"] is None

    def test_delete_victim_and_delete_user_removes_rows(self, conn):
        """Hapus korban dan user permanen harus menghapus baris dan data terkait."""
        posko_id = _make_posko(conn)
        admin_id = _make_user(conn, username="admin_del", role="admin")
        volunteer_id = _make_user(conn, username="staff_del", role="relawan")
        victim_id = db.insert_victim(conn, {
            "kode_korban": "K-DEL",
            "nama_panggilan": "Sari",
            "status": "selamat",
            "posko_id": posko_id,
            "created_by": volunteer_id,
        })
        db.insert_message(conn, {
            "sender_id": volunteer_id,
            "receiver_id": admin_id,
            "ciphertext": b"blob-message",
        })

        db.delete_victim(conn, victim_id)
        assert db.get_victim_by_id(conn, victim_id) is None

        db.delete_user(conn, volunteer_id)
        assert db.get_user_by_id(conn, volunteer_id) is None
        assert db.get_messages_between(conn, volunteer_id, admin_id) == []

    def test_delete_photo_and_file_removes_records(self, conn, tmp_path):
        """Hapus foto dan file harus menghapus record serta file yang terkait."""
        victim_id = db.insert_victim(conn, {
            "kode_korban": "K-IMG",
            "nama_panggilan": "Dina",
            "status": "selamat",
        })
        photo_id = db.insert_photo(conn, {
            "victim_id": victim_id,
            "posko_id": None,
            "image_path": "photo.png",
            "original_hash": "abc",
            "keterangan": "uji",
            "uploaded_by": None,
        })
        file_id = db.insert_file(conn, {
            "uploader_id": None,
            "nama_asli": "laporan.pdf",
            "path_enc": "report.enc",
            "ukuran": 123,
            "file_hash": "def",
        })

        db.delete_photo(conn, photo_id)
        assert db.get_photo_by_id(conn, photo_id) is None

        db.delete_file(conn, file_id)
        assert db.get_file_by_id(conn, file_id) is None


# ─────────────────────────────────────────────────────────────────────
# Tes: Enkripsi kolom victim
# ─────────────────────────────────────────────────────────────────────

class TestVictimEncryption:

    def test_nik_stored_as_ciphertext(self, conn, db_key):
        """
        Kolom nik_enc harus berisi data acak, BUKAN plaintext NIK asli.
        Verifikasi dengan membaca langsung lewat sqlite3 (bypass secure_store).
        """
        nik_asli = "3201234567890001"
        secure_store.add_victim(conn, db_key, {
            "kode_korban": "K001",
            "nik": nik_asli,
            "status": "selamat",
        })

        # Baca langsung dari DB — harus BLOB, bukan NIK asli
        cur = conn.execute("SELECT nik_enc FROM victims WHERE kode_korban = ?", ("K001",))
        nik_enc = cur.fetchone()["nik_enc"]

        assert nik_enc is not None
        assert isinstance(nik_enc, bytes)
        # Blob tidak boleh mengandung plaintext NIK
        assert nik_asli.encode() not in nik_enc

    def test_victim_roundtrip(self, conn, db_key):
        """Korban yang disimpan bisa dibaca kembali dengan kunci benar."""
        payload = {
            "kode_korban":    "K002",
            "nama_lengkap":   "Budi Santoso",
            "nik":            "3201234567890002",
            "alamat_asal":    "Jl. Merdeka 1",
            "kondisi_medis":  "luka ringan di kepala",
            "kontak_keluarga": "0812345678",
            "catatan":        "sudah diberi pertolongan pertama",
            "status":         "luka ringan",
            "nama_panggilan": "Budi",
        }
        secure_store.add_victim(conn, db_key, payload)
        result = secure_store.get_victim(conn, db_key, victim_id=1)

        assert result["nik"]            == payload["nik"]
        assert result["nama_lengkap"]   == payload["nama_lengkap"]
        assert result["kondisi_medis"]  == payload["kondisi_medis"]
        assert result["alamat_asal"]    == payload["alamat_asal"]

    def test_wrong_key_fails(self, conn, db_key):
        """Kunci salah harus menghasilkan InvalidTag."""
        secure_store.add_victim(conn, db_key, {
            "kode_korban": "K003",
            "nik": "1234567890",
        })
        wrong_key = os.urandom(32)
        with pytest.raises(InvalidTag):
            secure_store.get_victim(conn, wrong_key, victim_id=1)

    def test_list_victims_no_decryption(self, conn, db_key):
        """list_victims() mengembalikan baris tanpa kolom *_enc."""
        secure_store.add_victim(conn, db_key, {
            "kode_korban": "K004", "nik": "9999",
        })
        rows = secure_store.list_victims(conn)
        assert len(rows) == 1
        # Kolom *_enc tidak boleh ada di hasil
        row_keys = rows[0].keys()
        assert "nik_enc" not in row_keys
        assert "nama_lengkap_enc" not in row_keys

    def test_update_victim_reencrypts(self, conn, db_key):
        """update_victim mengenkripsi ulang kolom yang diperbarui."""
        vid = secure_store.add_victim(conn, db_key, {
            "kode_korban": "K005",
            "nik": "1111",
            "catatan": "awal",
        })
        secure_store.update_victim(conn, db_key, vid, {"catatan": "diperbarui"})
        result = secure_store.get_victim(conn, db_key, vid)
        assert result["catatan"] == "diperbarui"


# ─────────────────────────────────────────────────────────────────────
# Tes: Blockchain
# ─────────────────────────────────────────────────────────────────────

class TestBlockchainDB:

    def test_get_or_create_chain_creates_genesis(self, conn):
        """Tabel kosong → get_or_create_chain membuat genesis dan menyimpannya."""
        bc = secure_store.get_or_create_chain(conn)
        assert bc.height == 1
        assert db.count_blocks(conn) == 1

    def test_get_or_create_chain_idempotent(self, conn):
        """Memanggil get_or_create_chain dua kali tidak membuat genesis kedua."""
        bc1 = secure_store.get_or_create_chain(conn)
        bc2 = secure_store.get_or_create_chain(conn)
        # Chain kedua dimuat dari DB, bukan baru
        assert bc1.height == bc2.height
        assert db.count_blocks(conn) == 1   # tetap 1, bukan 2

    def test_append_block_saved_to_db(self, conn):
        """append_block menambah block ke DB."""
        secure_store.append_block(conn, {
            "jenis": "beras", "jumlah": 50,
            "dari": "Posko A", "ke": "Posko B", "petugas": "Budi",
        })
        assert db.count_blocks(conn) == 2   # genesis + 1

    def test_load_reload_valid(self, conn):
        """Simpan, muat ulang, is_valid() harus True."""
        secure_store.append_block(conn, {
            "jenis": "air", "jumlah": 100,
            "dari": "Gudang", "ke": "Posko C", "petugas": "Ani",
        })
        bc_reloaded = secure_store.load_blockchain(conn)
        valid, broken = bc_reloaded.is_valid()
        assert valid is True
        assert broken is None

    def test_multiple_blocks_then_reload(self, conn):
        """Beberapa block → muat ulang → chain valid dan panjang benar."""
        for i in range(3):
            secure_store.append_block(conn, {
                "jenis": "selimut", "jumlah": i + 1,
                "dari": "Donatur", "ke": f"Posko {i}", "petugas": f"r{i}",
            })
        bc = secure_store.load_blockchain(conn)
        assert bc.height == 4       # genesis + 3
        valid, _ = bc.is_valid()
        assert valid is True

    def test_reload_does_not_create_new_genesis(self, conn):
        """
        Setelah ada data, load_blockchain tidak pernah membuat genesis baru.
        Memastikan tidak ada duplikasi genesis meski dipanggil berkali-kali.
        """
        secure_store.append_block(conn, {"jenis": "tenda", "jumlah": 5,
                                          "dari": "A", "ke": "B", "petugas": "x"})
        n_before = db.count_blocks(conn)
        secure_store.load_blockchain(conn)
        secure_store.load_blockchain(conn)
        assert db.count_blocks(conn) == n_before  # tidak bertambah


# ─────────────────────────────────────────────────────────────────────
# Tes: SQL Injection
# ─────────────────────────────────────────────────────────────────────

class TestSQLInjection:

    def test_malicious_username_treated_as_text(self, conn):
        """
        Username berisi SQL injection diperlakukan sebagai teks biasa.
        Query berparameter (?) mencegah injeksi secara struktural.
        """
        malicious = "' OR '1'='1"
        uid = _make_user(conn, username=malicious)

        # Lookup dengan username yang sama harus menemukan user tersebut
        row = db.get_user_by_username(conn, malicious)
        assert row is not None
        assert row["id"] == uid
        assert row["username"] == malicious

    def test_injection_in_kode_korban(self, conn, db_key):
        """Kode korban yang berisi karakter SQL khusus disimpan dan dibaca aman."""
        evil_kode = "'; DROP TABLE victims; --"
        secure_store.add_victim(conn, db_key, {
            "kode_korban": evil_kode,
            "status": "selamat",
        })
        result = secure_store.get_victim_by_kode(conn, db_key, evil_kode)
        assert result is not None
        assert result["kode_korban"] == evil_kode

        # Tabel victims masih ada
        rows = secure_store.list_victims(conn)
        assert len(rows) == 1

    def test_injection_in_search_username(self, conn):
        """
        get_user_by_username dengan string injeksi tidak mengembalikan
        baris yang tidak seharusnya ditemukan.
        """
        _make_user(conn, username="legitimate_user")
        # Injeksi: coba dapatkan semua user
        result = db.get_user_by_username(conn, "' OR '1'='1")
        assert result is None  # tidak ada user dengan username itu


# ─────────────────────────────────────────────────────────────────────
# Tes: init_db idempoten
# ─────────────────────────────────────────────────────────────────────

class TestInitDB:

    def test_init_db_idempotent(self, tmp_db):
        """Memanggil init_db berkali-kali tidak error dan tidak menghapus data."""
        with db.get_connection(tmp_db) as c:
            _make_user(c, username="user_tetap")

        # Init ulang — data tidak boleh hilang
        db.init_db(tmp_db)

        with db.get_connection(tmp_db) as c:
            row = db.get_user_by_username(c, "user_tetap")
        assert row is not None

    def test_row_factory_allows_column_access(self, conn):
        """row_factory=Row memungkinkan akses kolom dengan nama."""
        _make_user(conn, username="nama_test")
        row = db.get_user_by_username(conn, "nama_test")
        # Akses via nama kolom, bukan index
        assert row["username"] == "nama_test"
        assert row["role"] == "relawan"
