# ✅ Tahap 0: Lingkungan - SELESAI

## Status: LULUS ✓

Tes kriteria lulus telah terpenuhi:
```bash
python -c "import PySide6, cryptography, argon2, Crypto, cv2, PIL, psutil; print('OK')"
```
**Output**: `OK`

## File yang Dibuat

### 1. Struktur Folder
```
SafeRelief/
├── crypto/          ✓ + __init__.py
├── auth/            ✓ + __init__.py
├── database/        ✓ + __init__.py
├── ui/              ✓ + __init__.py
├── models/          ✓ (untuk file ONNX)
├── data/            ✓ (untuk saferelief.db)
├── storage/         ✓ (untuk file .enc)
└── tests/           ✓ + __init__.py
```

### 2. File Konfigurasi

#### `requirements.txt` ✓
Berisi semua dependensi yang diperlukan:
- PySide6 >= 6.5.0 (UI Desktop)
- cryptography >= 41.0.0 (Enkripsi modern)
- argon2-cffi >= 23.1.0 (Hash password)
- pycryptodome >= 3.19.0 (Blowfish)
- opencv-python >= 4.8.0 (Face recognition)
- numpy >= 1.24.0 (Array processing)
- Pillow >= 10.0.0 (Image processing)
- psutil >= 5.9.0 (Dongle detection)
- pytest >= 7.4.0 (Testing)
- qt-material >= 2.14 (Optional UI theme)

**Status Instalasi**: ✓ Semua terinstall dengan sukses

#### `.gitignore` ✓
Melindungi data sensitif agar tidak ter-commit:
- `__pycache__/`, `*.pyc` (Python cache)
- `venv/`, `.venv` (Virtual environment)
- `data/`, `*.db` (Database)
- `storage/`, `*.enc` (File terenkripsi)
- `*.saferelief_key`, `recovery.key` (Kunci dongle dan recovery)
- File IDE dan OS

#### `config.py` ✓
Konfigurasi lengkap aplikasi:

**Path & Direktori:**
- `BASE_DIR`: Root proyek
- `DB_PATH`: data/saferelief.db
- `STORAGE_DIR`: storage/
- `MODELS_DIR`: models/ (YuNet & SFace)

**Parameter Blockchain:**
- `BLOCKCHAIN_DIFFICULTY`: 3 (leading zeros)

**Parameter Face Recognition:**
- `FACE_MATCH_THRESHOLD`: 0.363 (cosine similarity)
- `FACE_CAPTURE_FRAMES`: 5 frame

**Parameter Login Security:**
- `MAX_LOGIN_ATTEMPTS`: 3 kali
- `ACCOUNT_LOCK_DURATION`: 300 detik (5 menit)

**Parameter Dongle:**
- `DONGLE_CHECK_INTERVAL`: 2 detik
- `DONGLE_KEY_FILE`: .saferelief_key
- `DONGLE_TOKEN_LENGTH`: 32 bytes

**Parameter Enkripsi:**
- `MASTER_KEY_LENGTH`: 32 bytes
- `AES_GCM_NONCE_LENGTH`: 12 bytes
- `CHACHA20_NONCE_LENGTH`: 12 bytes
- `BLOWFISH_IV_LENGTH`: 8 bytes
- `HMAC_SHA256_LENGTH`: 32 bytes
- `VIGENERE_KEY_LENGTH`: 16 karakter

**Parameter Argon2:**
- `ARGON2_TIME_COST`: 2
- `ARGON2_MEMORY_COST`: 102400 (100 MB)
- `ARGON2_PARALLELISM`: 8

**Parameter Scrypt:**
- `SCRYPT_N`: 16384 (2^14)
- `SCRYPT_R`: 8
- `SCRYPT_P`: 1

**HKDF Labels** (untuk key derivation):
- `HKDF_LABEL_DB`: b"db"
- `HKDF_LABEL_CHAT_ENC`: b"chat-enc"
- `HKDF_LABEL_CHAT_MAC`: b"chat-mac"
- `HKDF_LABEL_FILE`: b"file"
- `HKDF_LABEL_STEGO`: b"stego"
- `HKDF_LABEL_VIGENERE`: b"vigenere"

**Fungsi:**
- `ensure_directories()`: Membuat folder data, storage, models jika belum ada

### 3. File Aplikasi

#### `app.py` ✓
Entry point utama aplikasi (placeholder untuk Tahap 5).
Saat ini hanya menampilkan status dan instruksi.

#### `setup_admin.py` ✓
Skrip setup admin awal (placeholder untuk Tahap 4).
Akan diimplementasi setelah modul autentikasi selesai.

#### `README.md` ✓
Dokumentasi lengkap proyek:
- Deskripsi aplikasi
- Fitur-fitur
- Stack teknologi
- Cara instalasi dan penggunaan
- Struktur proyek
- Dokumentasi keamanan
- Keterbatasan yang diakui
- Peran pengguna (Admin vs Relawan)

### 4. File `__init__.py`
Dibuat di semua folder modul Python:
- `crypto/__init__.py` ✓
- `auth/__init__.py` ✓
- `database/__init__.py` ✓
- `ui/__init__.py` ✓
- `tests/__init__.py` ✓

Setiap file berisi docstring yang menjelaskan tujuan modul.

## Verifikasi

### 1. Tes Import Library ✓
```bash
python -c "import PySide6, cryptography, argon2, Crypto, cv2, PIL, psutil; print('OK')"
```
**Result**: OK ✓

### 2. Tes Config ✓
```bash
python config.py
```
**Result**: 
- Menampilkan semua konfigurasi
- Membuat folder data/, storage/, models/
- Exit code: 0 ✓

### 3. Struktur Folder ✓
Semua folder sesuai AGENTS.md bagian 8:
```
✓ crypto/
✓ auth/
✓ database/
✓ ui/
✓ models/
✓ data/
✓ storage/
✓ tests/
```

### 4. File Wajib ✓
```
✓ requirements.txt
✓ .gitignore
✓ config.py
✓ app.py
✓ setup_admin.py
✓ README.md
✓ AGENTS.md (sudah ada)
✓ TASKS.md (sudah ada)
```

## Hal yang Perlu Dipahami

### 1. Konfigurasi Terpusat
Semua parameter sistem berada di `config.py`. Tidak ada hardcoded values di kode lain.

### 2. Label HKDF
Label untuk key derivation (`b"db"`, `b"chat-enc"`, dll.) **TIDAK BOLEH DIUBAH** setelah ada data, karena akan membuat data tidak terbaca.

### 3. Keamanan Parameter
- Argon2: balance antara keamanan dan performa (2 iterasi, 100MB memory)
- Scrypt: parameter standar untuk KEK derivation
- Blockchain difficulty 3: cukup ringan untuk demo, bisa dinaikkan untuk produksi

### 4. Path Management
Semua path menggunakan `pathlib.Path` untuk kompatibilitas cross-platform (meski target adalah Windows).

### 5. Data Sensitif
`.gitignore` sudah dikonfigurasi untuk mencegah commit data sensitif:
- Database (`*.db`)
- File terenkripsi (`*.enc`)
- Token dongle (`*.saferelief_key`)
- Recovery key (`recovery.key`)

### 6. Dependensi Optional
`qt-material` bersifat opsional untuk styling UI. Aplikasi tetap berjalan tanpanya.

## Langkah Selanjutnya

Setelah Tahap 0 lulus, lanjutkan ke **Tahap 1: Modul Kripto Dasar**.

Tahap 1 akan mengimplementasi:
- `crypto/vigenere.py`
- `crypto/aes_module.py`
- `crypto/blowfish_module.py`
- `crypto/chacha_module.py`
- `crypto/hashing.py`
- `crypto/keys.py`
- `crypto/super_encrypt.py`
- `tests/test_crypto.py`

## Catatan untuk Presentasi

Saat menjelaskan ke dosen, sampaikan:

1. **Python 3.13.3** digunakan (sedikit lebih baru dari spec 3.11/3.12, tapi kompatibel)
2. Semua library berhasil terinstall dan bisa diimport
3. Konfigurasi terpusat di `config.py` memudahkan tuning parameter
4. Struktur folder mengikuti best practice Python (modul dengan `__init__.py`)
5. `.gitignore` melindungi data sensitif
6. `README.md` mendokumentasikan keterbatasan dengan jujur (requirement tugas)

## Pesan Commit yang Disarankan

```
feat: setup tahap 0 - struktur proyek dan konfigurasi

- Buat struktur folder (crypto, auth, database, ui, models, data, storage, tests)
- Tambahkan requirements.txt dengan semua dependensi
- Buat config.py dengan parameter terpusat
- Setup .gitignore untuk data sensitif
- Tambahkan app.py dan setup_admin.py (placeholder)
- Dokumentasi di README.md
- Tes: semua library berhasil diimport ✓
```

---

**Tahap 0**: ✅ SELESAI dan LULUS
**Tes kriteria**: ✅ LOLOS
**Siap lanjut**: Tahap 1 (setelah konfirmasi pengguna)
