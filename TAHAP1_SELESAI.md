# ✅ Tahap 1: Modul Kripto Dasar - SELESAI

## Status: LULUS ✓

**Hasil Pytest:**
```
============================= test session starts =============================
tests/test_crypto.py::TestVigenere (5 tests) ✓
tests/test_crypto.py::TestAES (5 tests) ✓
tests/test_crypto.py::TestBlowfish (5 tests) ✓
tests/test_crypto.py::TestChaCha20 (4 tests) ✓
tests/test_crypto.py::TestHashing (5 tests) ✓
tests/test_crypto.py::TestKeys (10 tests) ✓
tests/test_crypto.py::TestSuperEncrypt (3 tests) ✓

============================= 37 passed in 7.60s ==============================
```

**Semua Kriteria Lulus Terpenuhi:**
- ✅ Round-trip tiap algoritma
- ✅ Kunci salah gagal
- ✅ Ubah 1 byte gagal (GCM, Poly1305, HMAC)
- ✅ Kunci Vigenère salah menghasilkan teks berbeda (bukan error)
- ✅ Hash password berbeda untuk password sama
- ✅ Unwrap master key dengan password salah gagal
- ✅ Unwrap dengan token dongle salah gagal
- ✅ Unwrap hanya berhasil jika password DAN token benar
- ✅ Kunci Vigenère turunan deterministik dan semua karakter ASCII 32-126
- ✅ File pemulihan bisa dibuka dengan password pemulihan yang benar saja

---

## File yang Dibuat

### 1. Modul Kriptografi

#### `crypto/vigenere.py` ✓
**Fungsi:**
- `encrypt(plaintext, key) -> str`
- `decrypt(ciphertext, key) -> str`

**Detail:**
- Bekerja pada ASCII 32-126 (95 karakter cetak)
- Karakter di luar rentang tidak dienkripsi
- Modulus 95 untuk shift
- Kunci salah menghasilkan teks berbeda (BUKAN error)

**Kenapa Vigenère:**
- Demonstrasi cipher klasik (requirement tugas)
- Lapisan pertama dalam super enkripsi
- Meski lemah kriptanalisis, ini untuk demo historis

---

#### `crypto/aes_module.py` ✓
**Fungsi:**
- `encrypt(plaintext: bytes, key: bytes) -> bytes`
- `decrypt(data: bytes, key: bytes) -> bytes`

**Detail:**
- AES-256-GCM (Authenticated Encryption)
- Key: 32 bytes (256-bit)
- Nonce: 12 bytes (acak per enkripsi)
- Tag: 16 bytes (otomatis oleh GCM)
- Format output: `nonce(12) + ciphertext + tag(16)`
- Overhead: 28 bytes

**Digunakan untuk:**
- Enkripsi kolom database sensitif
- Payload steganografi
- Wrapping master key

**Kenapa AES-GCM:**
- AEAD built-in (tidak perlu MAC terpisah)
- Standar industri
- Hardware acceleration di CPU modern
- Efisien untuk random access

---

#### `crypto/blowfish_module.py` ✓
**Fungsi:**
- `encrypt(plaintext: bytes, enc_key: bytes, mac_key: bytes) -> bytes`
- `decrypt(data: bytes, enc_key: bytes, mac_key: bytes) -> bytes`

**Detail:**
- Blowfish-CBC + HMAC-SHA256
- Encrypt-then-MAC pattern
- IV: 8 bytes (block size Blowfish)
- Padding: PKCS7
- HMAC: 32 bytes
- Format output: `IV(8) + ciphertext + HMAC(32)`
- Overhead: 40 bytes + padding

**Kenapa Blowfish + HMAC:**
- Blowfish cepat dan teruji
- CBC untuk stream data chat
- HMAC untuk authenticated encryption
- Encrypt-then-MAC lebih aman dari MAC-then-encrypt

**Keterbatasan:**
- Block size 64-bit (bukan 128-bit)
- Untuk data >4GB perlu rekey (tidak relevan untuk chat)

---

#### `crypto/chacha_module.py` ✓
**Fungsi:**
- `encrypt(plaintext: bytes, key: bytes) -> bytes`
- `decrypt(data: bytes, key: bytes) -> bytes`
- `encrypt_file(input_path, output_path, key)`
- `decrypt_file(input_path, output_path, key)`

**Detail:**
- ChaCha20-Poly1305 (AEAD)
- Key: 32 bytes
- Nonce: 12 bytes
- Tag: 16 bytes (Poly1305 MAC)
- Format output: `nonce(12) + ciphertext + tag(16)`

**Digunakan untuk:**
- Enkripsi file laporan

**Kenapa ChaCha20:**
- Lebih cepat dari AES tanpa hardware acceleration
- AEAD modern (TLS 1.3, WireGuard, Signal)
- Stream cipher (efisien untuk file besar)

---

#### `crypto/hashing.py` ✓
**Fungsi:**
- `hash_password(password: str) -> str`
- `verify_password(password: str, hash: str) -> bool`
- `rehash_needed(hash: str) -> bool`
- `sha256_hash(data: bytes) -> bytes`
- `sha256_hex(data: bytes) -> str`

**Detail Argon2:**
- Algorithm: Argon2id (hybrid)
- Time cost: 2 (dari config)
- Memory cost: 102400 KB = 100 MB
- Parallelism: 8 threads
- Salt: 16 bytes (auto-generated)
- Output: 32 bytes
- Format: `$argon2id$v=19$m=102400,t=2,p=8$salt$hash`

**Kenapa Argon2:**
- Pemenang Password Hashing Competition 2015
- Memory-hard (ASIC/GPU resistant)
- id variant: balance security vs DoS protection

**SHA-256:**
- Untuk hash token dongle
- Integritas file/foto
- Hash blockchain

---

#### `crypto/keys.py` ✓ (MODUL KUNCI)
**Fungsi:**
- `generate_master_key() -> bytes`
- `derive_kek(password, token, salt) -> bytes`
- `wrap_master_key(master_key, password, token, salt) -> bytes`
- `unwrap_master_key(wrapped, password, token, salt) -> bytes`
- `derive_key(master_key, info) -> bytes`
- `derive_vigenere_key(master_key) -> str`
- `create_recovery_file(master_key, recovery_password, path)`
- `open_recovery_file(path, recovery_password) -> bytes`

**Arsitektur Kunci:**

1. **Master Key** (32 bytes acak)
   - Kunci utama organisasi
   - TIDAK PERNAH disimpan polos
   - Generated saat setup admin pertama

2. **Token Dongle** (32 bytes hex di file)
   - Disimpan di `.saferelief_key` di flashdisk
   - Faktor "something you have"
   - Hash SHA-256 disimpan di database

3. **KEK (Key-Encrypting Key)**
   - Diturunkan dari: `Scrypt(password_bytes + token_bytes, salt)`
   - Password: something you know
   - Token: something you have
   - Gabungan tidak ambigu: password (variabel) + token (32 bytes tetap)

4. **Wrapped Master Key**
   - Master key terenkripsi dengan KEK
   - Algoritma: AES-256-GCM
   - Format: `nonce(12) + ciphertext(32) + tag(16)` = 60 bytes
   - Disimpan di database kolom `wrapped_master_key`

5. **Kunci Turunan (HKDF-SHA256)**
   - `b"db"` → AES-GCM database (32 bytes)
   - `b"chat-enc"` → Blowfish chat (32 bytes)
   - `b"chat-mac"` → HMAC chat (32 bytes)
   - `b"file"` → ChaCha20 file (32 bytes)
   - `b"stego"` → AES-GCM steganografi (32 bytes)
   - `b"vigenere"` → Kunci Vigenère (16 karakter ASCII 32-126)

6. **Recovery File**
   - Backup master key untuk disaster recovery
   - Wrapped dengan password pemulihan (beda dari login)
   - Format: `salt(16) + wrapped_master_key`
   - Disimpan OFFLINE oleh admin

**Proses Wrap/Unwrap (untuk dijelaskan ke dosen):**

**ENKRIPSI (Wrap):**
```
1. User punya: password + dongle (berisi token)
2. Gabungkan: password (UTF-8 bytes) + token (32 bytes)
   Contoh: b"Pass123" + b"\x1a\x2b..." = b"Pass123\x1a\x2b..."
3. Scrypt(gabungan, salt) → KEK (32 bytes)
   - Salt disimpan di database (kdf_salt)
   - Scrypt lambat (memory-hard) untuk melawan brute-force
4. AES-GCM(master_key, KEK) → wrapped master key
   - Nonce acak 12 bytes
   - Ciphertext 32 bytes (master key terenkripsi)
   - Tag 16 bytes (verifikasi integritas)
5. Simpan di database:
   - wrapped_master_key (60 bytes)
   - kdf_salt (16 bytes)
   - dongle_serial
   - dongle_token_hash (SHA-256 dari token)
```

**DEKRIPSI (Unwrap):**
```
1. User login dengan: password + dongle
2. Baca token dari dongle (file .saferelief_key)
3. Verifikasi: SHA-256(token) == dongle_token_hash di database
4. Baca kdf_salt dan wrapped_master_key dari database
5. Gabungkan password + token (sama dengan saat wrap)
6. Scrypt(gabungan, salt) → KEK
7. AES-GCM decrypt(wrapped_master_key, KEK)
   - Verifikasi tag otomatis
   - Jika password ATAU token salah → KEK salah → tag invalid → ERROR
8. Master key terbuka, simpan di memori sesi
9. Derive kunci turunan dengan HKDF saat dibutuhkan
```

**Kenapa Arsitektur Ini:**
- **2-Factor**: Butuh password (know) + dongle (have)
- **Key Separation**: Master key tidak pernah di storage polos
- **Multi-User**: Master key sama bisa di-wrap untuk banyak user dengan KEK berbeda
- **Key Rotation**: Ganti password/dongle = wrap ulang master key (master key tetap)
- **Recovery**: File recovery untuk jika dongle hilang

---

#### `crypto/super_encrypt.py` ✓
**Fungsi:**
- `encrypt(plaintext: str, vig_key, enc_key, mac_key) -> bytes`
- `decrypt(ciphertext: bytes, vig_key, enc_key, mac_key) -> str`

**Alur Enkripsi:**
```
Plaintext (string)
    ↓ Vigenère
Vigenere Ciphertext (string)
    ↓ UTF-8 encode
Bytes
    ↓ Blowfish-CBC + HMAC
Final Ciphertext (bytes)
```

**Alur Dekripsi:**
```
Final Ciphertext (bytes)
    ↓ Verifikasi HMAC + Blowfish
Bytes
    ↓ UTF-8 decode
Vigenere Ciphertext (string)
    ↓ Vigenère decrypt
Plaintext (string)
```

**Kenapa Super Enkripsi:**
- Demonstrasi kombinasi klasik + modern
- Vigenère: lapisan historis
- Blowfish + HMAC: keamanan sebenarnya
- Keamanan bergantung pada layer Blowfish

---

### 2. File Tes

#### `tests/test_crypto.py` ✓
**37 tes total:**
- TestVigenere: 5 tes ✓
- TestAES: 5 tes ✓
- TestBlowfish: 5 tes ✓
- TestChaCha20: 4 tes ✓
- TestHashing: 5 tes ✓
- TestKeys: 10 tes ✓
- TestSuperEncrypt: 3 tes ✓

**Coverage:**
- ✅ Round-trip semua algoritma
- ✅ Key salah gagal (InvalidTag, ValueError)
- ✅ Data tampered gagal (1 byte flip)
- ✅ Format output benar
- ✅ Edge cases (empty input, invalid length)
- ✅ File encryption/decryption
- ✅ Password hashing variability
- ✅ Key derivation deterministic
- ✅ Vigenère key ASCII range
- ✅ Recovery file

---

## Cara Menjalankan Tes

```bash
# Semua tes
pytest tests/test_crypto.py -v

# Tes spesifik
pytest tests/test_crypto.py::TestKeys -v
pytest tests/test_crypto.py::TestVigenere::test_roundtrip -v

# Dengan output detail
pytest tests/test_crypto.py -vv

# Dengan coverage (jika terinstall)
pytest tests/test_crypto.py --cov=crypto
```

---

## Penjelasan untuk Dosen: Alur Wrap/Unwrap

### Analogi Sederhana:

Bayangkan **master key** adalah kunci brankas organisasi yang menyimpan semua data penting.

**Masalah:** Kita tidak bisa simpan kunci brankas begitu saja di database (tidak aman).

**Solusi:** Bungkus kunci brankas dengan "kotak gembok" yang hanya bisa dibuka dengan:
1. **Password** (yang kamu tahu)
2. **Token dari flashdisk** (yang kamu punya)

### Proses Lengkap:

#### 🔐 **Saat Membuat Admin (Wrap):**

1. **Generate master key** (32 bytes acak)
   - Ini kunci brankas utama

2. **Siapkan 2 faktor:**
   - Password: user ketik saat setup
   - Token: tulis 32 bytes acak ke flashdisk

3. **Buat "gembok" (KEK):**
   - Gabungkan password + token
   - Proses dengan Scrypt (lambat, sulit di-brute force)
   - Hasil: KEK (kunci untuk mengunci master key)

4. **Bungkus master key:**
   - Enkripsi master key dengan KEK menggunakan AES-GCM
   - Hasil: wrapped master key (terlihat acak)

5. **Simpan:**
   - Database: wrapped master key + salt
   - Flashdisk: token (dalam file .saferelief_key)
   - Hash token disimpan di database (untuk verifikasi)

#### 🔓 **Saat Login (Unwrap):**

1. **User datang dengan:**
   - Password (diketik)
   - Flashdisk tercolok (berisi token)

2. **Verifikasi dongle:**
   - Baca token dari flashdisk
   - Hash token, bandingkan dengan database
   - Jika tidak cocok → dongle salah → TOLAK

3. **Coba buka gembok:**
   - Gabungkan password + token (dari flashdisk)
   - Proses dengan Scrypt + salt (dari database)
   - Hasil: KEK

4. **Coba bungkus master key:**
   - Dekripsi wrapped master key dengan KEK
   - AES-GCM akan verifikasi tag otomatis
   - **Jika berhasil:** master key terbuka ✅
   - **Jika gagal:** password ATAU token salah ❌

5. **Master key di memori:**
   - Master key hanya ada di RAM (session)
   - Dipakai untuk derive kunci lainnya (HKDF)
   - Saat logout/dongle dicabut → HAPUS dari memori

### Keamanan:

1. **Master key tidak pernah disimpan polos** (selalu wrapped)
2. **Butuh 2 faktor** untuk unwrap (password + dongle)
3. **Password salah ATAU dongle salah → gagal** (tidak bisa dibedakan, untuk keamanan)
4. **Scrypt lambat** → sulit brute-force meski database bocor
5. **Salt unik per user** → rainbow table tidak berguna
6. **Recovery file** → backup offline jika dongle hilang

### Sifat Penting:

- **Deterministik:** Password + token + salt sama → KEK sama → master key terbuka
- **One-way (hampir):** Wrapped master key tanpa password + token = data acak yang tidak berguna
- **Separasi:** Setiap user punya wrapped master key sendiri (dengan password dan dongle berbeda), tapi master key organisasi sama

---

## Yang Perlu Dipahami untuk Presentasi

### 1. Vigenère
- Cipher klasik substitusi polyalphabetic
- Modulus 95 (ASCII cetak)
- Kunci salah = teks acak (tidak ada error, tidak ada MAC)
- Lemah terhadap frequency analysis dan Kasiski test

### 2. AES-GCM
- AEAD (Authenticated Encryption with Associated Data)
- Tag 16 bytes untuk integritas
- Nonce 12 bytes HARUS unik per enkripsi
- Gagal verifikasi tag = data rusak atau key salah

### 3. Blowfish-CBC + HMAC
- CBC butuh IV acak
- Padding PKCS7
- **Encrypt-then-MAC** (MAC atas ciphertext, lebih aman)
- HMAC dihitung atas IV + ciphertext
- Verifikasi HMAC SEBELUM dekripsi (mencegah padding oracle)

### 4. ChaCha20-Poly1305
- Stream cipher (vs block cipher AES)
- Poly1305 MAC built-in
- Lebih cepat di perangkat tanpa AES-NI
- Standar TLS 1.3

### 5. Argon2
- Memory-hard (butuh banyak RAM)
- Sulit di-paralelkan (GPU/ASIC resistant)
- Parameter tunable (time, memory, parallelism)
- Salt otomatis per password

### 6. HKDF
- Key Derivation Function berbasis HMAC
- Dari 1 master key → banyak kunci independen
- Info (label) untuk domain separation
- Deterministik (input sama → output sama)

### 7. Scrypt
- Key Derivation Function memory-hard
- Untuk derive KEK dari password + token
- Parameter n, r, p dari config
- Lebih lambat = lebih aman (vs brute-force)

---

## Keterbatasan (Jujur untuk Laporan)

1. **Vigenère**: Lemah kriptanalisis, hanya untuk demo
2. **Blowfish**: Block 64-bit (vs AES 128-bit)
3. **File encryption**: Load seluruh file ke memory (tidak streaming)
4. **Error messages**: Tidak membedakan password salah vs token salah (by design untuk keamanan, tapi user bingung)
5. **Key rotation**: Belum ada mekanisme otomatis
6. **Hardware Security Module**: Tidak digunakan (master key di RAM)

---

## Pesan Commit yang Disarankan

```
feat: implement tahap 1 - modul kripto dasar

Modul:
- crypto/vigenere.py (klasik, ASCII 32-126)
- crypto/aes_module.py (AES-256-GCM)
- crypto/blowfish_module.py (CBC + HMAC)
- crypto/chacha_module.py (ChaCha20-Poly1305)
- crypto/hashing.py (Argon2, SHA-256)
- crypto/keys.py (wrap/unwrap, HKDF, recovery)
- crypto/super_encrypt.py (Vigenère + Blowfish)

Tes:
- tests/test_crypto.py (37 tes, semua hijau)
- Coverage: round-trip, key salah, tamper detection, 
  wrap/unwrap 2-factor, derivation, recovery

Tes lulus: 37/37 dalam 7.60 detik ✓
```

---

**Tahap 1**: ✅ **SELESAI dan LULUS**  
**Pytest**: ✅ **37/37 passed**  
**Siap lanjut**: Menunggu konfirmasi untuk Tahap 2 (Steganografi & Blockchain)
