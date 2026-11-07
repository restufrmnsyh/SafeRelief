-- SafeRelief Database Schema
-- SQLite dengan PRAGMA foreign_keys = ON
-- Semua tabel dibuat dengan IF NOT EXISTS → init_db() idempoten

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel posko (dibuat duluan karena direferensikan users dan victims)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS posko (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nama        TEXT    NOT NULL,
    lokasi      TEXT    NOT NULL,
    kapasitas   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel users
--
-- dongle_serial: UNIQUE tapi boleh NULL (akun belum punya dongle).
--   SQLite memperbolehkan beberapa NULL pada kolom UNIQUE.
--
-- role: hanya 'admin' atau 'relawan' — dijaga dengan CHECK.
-- is_active: 0 atau 1 — dijaga dengan CHECK.
--
-- face_encoding_enc: embedding wajah dienkripsi AES-GCM (BLOB).
-- wrapped_master_key: master key terenkripsi dengan KEK (BLOB).
-- kdf_salt: salt untuk Scrypt saat derive KEK (BLOB, 16 byte).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    nama_lengkap        TEXT    NOT NULL,
    username            TEXT    NOT NULL UNIQUE,
    password_hash       TEXT    NOT NULL,
    role                TEXT    NOT NULL CHECK (role IN ('admin', 'relawan')),
    posko_id            INTEGER REFERENCES posko(id) ON DELETE SET NULL,
    face_encoding_enc   BLOB,
    dongle_serial       TEXT    UNIQUE,          -- NULL = belum didaftarkan
    dongle_token_hash   TEXT,                    -- SHA-256 hex dari token dongle
    wrapped_master_key  BLOB,
    kdf_salt            BLOB,
    failed_attempts     INTEGER NOT NULL DEFAULT 0,
    locked_until        TEXT,                    -- ISO datetime atau NULL
    is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Tepat satu admin di seluruh database.
-- Partial unique index: hanya baris dengan role='admin' yang dijaga.
CREATE UNIQUE INDEX IF NOT EXISTS one_admin_only
    ON users(role) WHERE role = 'admin';

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel victims (data korban bencana)
--
-- Kolom berakhiran _enc berisi BLOB: nonce(12) + ciphertext + tag(16).
-- Kolom plaintext: kode_korban, nama_panggilan, usia, gender, posko_id, status.
-- status: set nilai yang diperbolehkan dijaga dengan CHECK.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS victims (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    kode_korban         TEXT    NOT NULL UNIQUE,
    nama_panggilan      TEXT,
    usia                INTEGER,
    gender              TEXT    CHECK (gender IN ('L', 'P', NULL)),
    posko_id            INTEGER REFERENCES posko(id) ON DELETE SET NULL,
    status              TEXT    NOT NULL DEFAULT 'tidak diketahui'
                                CHECK (status IN (
                                    'selamat', 'luka ringan', 'luka berat',
                                    'meninggal', 'tidak diketahui'
                                )),
    -- Kolom sensitif — semua dienkripsi AES-GCM
    nama_lengkap_enc    BLOB,
    nik_enc             BLOB,
    alamat_asal_enc     BLOB,
    kondisi_medis_enc   BLOB,
    kontak_keluarga_enc BLOB,
    catatan_enc         BLOB,
    created_by          INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel photos (dokumentasi dengan steganografi)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    victim_id       INTEGER REFERENCES victims(id) ON DELETE CASCADE,
    posko_id        INTEGER REFERENCES posko(id)   ON DELETE SET NULL,
    image_path      TEXT    NOT NULL,              -- path relatif ke storage/
    original_hash   TEXT    NOT NULL,              -- SHA-256 hex foto asli
    keterangan      TEXT,
    uploaded_by     INTEGER REFERENCES users(id)   ON DELETE SET NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel messages (chat terenkripsi)
--
-- ciphertext: satu BLOB utuh dari super_encrypt (IV+ciphertext+HMAC).
-- Tidak ada kolom IV/nonce terpisah — semua sudah terkandung dalam blob.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ciphertext  BLOB    NOT NULL,                  -- super_encrypt output
    is_read     INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel files (laporan terenkripsi ChaCha20-Poly1305)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uploader_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    nama_asli   TEXT    NOT NULL,                  -- nama file sebelum enkripsi
    path_enc    TEXT    NOT NULL,                  -- path UUID di storage/
    ukuran      INTEGER NOT NULL DEFAULT 0,        -- ukuran file asli (byte)
    file_hash   TEXT    NOT NULL,                  -- SHA-256 hex file asli
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel blockchain (distribusi bantuan)
--
-- idx: PRIMARY KEY, nomor urut block (0 = genesis).
-- timestamp: integer milidetik (int(time.time()*1000)).
-- data: JSON string dengan sort_keys=True, separators=(",",":").
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blockchain (
    idx         INTEGER PRIMARY KEY,               -- nomor urut block, bukan AUTOINCREMENT
    timestamp   INTEGER NOT NULL,                  -- milidetik Unix
    data        TEXT    NOT NULL,                  -- JSON sort_keys=True, separators=(",",":")
    prev_hash   TEXT    NOT NULL,
    nonce       INTEGER NOT NULL DEFAULT 0,
    hash        TEXT    NOT NULL
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Tabel activity_log (audit trail)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    aksi        TEXT    NOT NULL,                  -- misal: LOGIN, LOGOUT, ADMIN_BOOTSTRAP
    detail      TEXT,                              -- JSON atau teks bebas
    created_at  TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);
