# 🔐 Penjelasan Wrap/Unwrap Master Key

> Panduan untuk menjelaskan arsitektur kunci ke dosen dengan bahasa sederhana

---

## 📚 Analogi Kehidupan Nyata

### Brankas Bank

Bayangkan **master key** adalah kunci brankas bank yang menyimpan uang semua nasabah.

**Masalah:**
- Tidak bisa simpan kunci brankas di brankas itu sendiri
- Tidak bisa simpan kunci brankas di database (bisa dicuri hacker)

**Solusi:**
- Kunci brankas dibungkus dalam "kotak terkunci" yang butuh 2 kunci untuk membuka:
  1. **Password** = kunci fisik yang kamu bawa
  2. **Token Dongle** = kartu akses yang kamu punya

Tanpa **KEDUANYA**, kotak tidak bisa dibuka, dan kunci brankas tetap aman.

---

## 🔄 Alur Teknis Sederhana

### 1️⃣ SETUP ADMIN (Wrap - Kunci Pertama Kali)

```
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Generate Master Key (32 bytes acak)                │
│  ┌──────────────────────────────────────────────┐           │
│  │  Master Key = 0x1a2b3c4d... (32 bytes)       │           │
│  │  Ini kunci UTAMA organisasi                   │           │
│  └──────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Siapkan 2 Faktor                                   │
│  ┌───────────────────────────────────────┐                  │
│  │  A. Password: "Admin123"               │  User ketik     │
│  │     → bytes: b"Admin123"               │                 │
│  │                                         │                 │
│  │  B. Token: 32 bytes acak                │  Tulis ke       │
│  │     → 0xaa..bb (32 bytes)              │  flashdisk      │
│  └───────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Gabungkan Password + Token                         │
│  ┌───────────────────────────────────────┐                  │
│  │  Combined = password_bytes + token     │                 │
│  │           = b"Admin123" + 32 bytes     │                 │
│  │           = 39 bytes total              │                 │
│  └───────────────────────────────────────┘                  │
│                                                               │
│  💡 Token 32 bytes tetap di akhir → tidak ambigu             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 4: Derive KEK (Key-Encrypting Key) dengan Scrypt      │
│  ┌───────────────────────────────────────┐                  │
│  │  Input:                                │                 │
│  │  - Combined (password + token)         │                 │
│  │  - Salt (16 bytes acak)                │                 │
│  │  - Parameter: n=16384, r=8, p=1        │                 │
│  │                                         │                 │
│  │  Scrypt() → KEK (32 bytes)             │                 │
│  └───────────────────────────────────────┘                  │
│                                                               │
│  💡 Scrypt LAMBAT (100MB memory, 2 detik) → sulit brute force│
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 5: Wrap Master Key dengan KEK (AES-256-GCM)           │
│  ┌───────────────────────────────────────┐                  │
│  │  AES-GCM Encrypt:                      │                 │
│  │  - Plaintext: Master Key (32 bytes)    │                 │
│  │  - Key: KEK (32 bytes)                 │                 │
│  │  - Nonce: 12 bytes acak                │                 │
│  │                                         │                 │
│  │  Output:                                │                 │
│  │  nonce(12) + ciphertext(32) + tag(16)  │                 │
│  │  = Wrapped Master Key (60 bytes)       │                 │
│  └───────────────────────────────────────┘                  │
│                                                               │
│  💡 Tag verifikasi integritas (rusak/salah → gagal)          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 6: Simpan                                              │
│  ┌────────────────────────────────────────┐                 │
│  │  DATABASE (SQLite):                     │                │
│  │  - wrapped_master_key (60 bytes) ✓     │                │
│  │  - kdf_salt (16 bytes) ✓               │                │
│  │  - dongle_serial (cth: "E4A2B31F")     │                │
│  │  - dongle_token_hash (SHA-256 token)   │                │
│  │                                         │                │
│  │  FLASHDISK:                             │                │
│  │  - .saferelief_key (token 32 bytes hex)│                │
│  └────────────────────────────────────────┘                 │
│                                                               │
│  💡 Master key TIDAK ADA dalam bentuk polos!                 │
└─────────────────────────────────────────────────────────────┘
```

---

### 2️⃣ LOGIN (Unwrap - Buka Kunci)

```
┌─────────────────────────────────────────────────────────────┐
│  USER DATANG DENGAN:                                         │
│  ✓ Password: "Admin123" (ketik di form login)               │
│  ✓ Flashdisk tercolok (berisi token)                        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 1: Verifikasi Dongle                                   │
│  ┌────────────────────────────────────────┐                 │
│  │  1. Baca token dari .saferelief_key     │                │
│  │  2. Hash token dengan SHA-256           │                │
│  │  3. Bandingkan dengan dongle_token_hash │                │
│  │     di database                          │                │
│  │                                          │                │
│  │  Jika TIDAK COCOK → TOLAK LOGIN         │                │
│  └────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
                          ↓ (dongle valid)
┌─────────────────────────────────────────────────────────────┐
│  STEP 2: Coba Derive KEK (sama seperti saat wrap)           │
│  ┌────────────────────────────────────────┐                 │
│  │  Combined = password_bytes + token      │                │
│  │           = b"Admin123" + token_dari_dongle             │
│  │                                          │                │
│  │  Scrypt(combined, salt_dari_database)   │                │
│  │  → KEK (32 bytes)                       │                │
│  └────────────────────────────────────────┘                 │
│                                                               │
│  💡 Salt dibaca dari database (kolom kdf_salt)               │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  STEP 3: Coba Unwrap (Dekripsi AES-GCM)                     │
│  ┌────────────────────────────────────────┐                 │
│  │  AES-GCM Decrypt:                       │                │
│  │  - Ciphertext: wrapped_master_key       │                │
│  │  - Key: KEK (yang baru di-derive)      │                │
│  │                                          │                │
│  │  AES-GCM akan:                           │                │
│  │  1. Ekstrak nonce, ciphertext, tag      │                │
│  │  2. Dekripsi ciphertext                 │                │
│  │  3. VERIFIKASI TAG                      │                │
│  └────────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  HASIL: 2 Kemungkinan                                        │
│                                                               │
│  ✅ SUCCESS:                                                 │
│  ┌────────────────────────────────────────┐                 │
│  │  Tag valid ✓                            │                │
│  │  → Password + Token BENAR               │                │
│  │  → Master Key terbuka (32 bytes)        │                │
│  │  → Simpan di MEMORI SESSION             │                │
│  │  → Derive kunci lainnya saat butuh      │                │
│  └────────────────────────────────────────┘                 │
│                                                               │
│  ❌ FAIL (InvalidTag):                                       │
│  ┌────────────────────────────────────────┐                 │
│  │  Tag tidak valid ✗                      │                │
│  │  → Password SALAH atau Token SALAH      │                │
│  │  → KEK salah → dekripsi gagal           │                │
│  │  → Error: "password atau dongle salah"  │                │
│  └────────────────────────────────────────┘                 │
│                                                               │
│  💡 Tidak dibedakan mana yang salah (keamanan)               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔑 Kenapa Butuh 2 Faktor?

### Skenario Serangan:

#### 1. Hacker Dapat Database
```
Hacker punya:
✓ wrapped_master_key
✓ kdf_salt
✓ dongle_token_hash

Hacker TIDAK punya:
✗ Password user (tidak di database)
✗ Token dongle (file fisik)

Hasil: Tidak bisa unwrap master key
```

#### 2. Hacker Dapat Password
```
Hacker punya:
✓ Password (phishing/keylog)

Hacker TIDAK punya:
✗ Token dongle (file fisik di flashdisk)
✗ Database (server aman)

Hasil: Tidak bisa unwrap master key
```

#### 3. Hacker Dapat Flashdisk
```
Hacker punya:
✓ Token (file .saferelief_key)

Hacker TIDAK punya:
✗ Password user
✗ Database (wrapped_master_key, salt)

Hasil: Tidak bisa unwrap master key
```

### ✅ Kesimpulan:
**Butuh 3 hal bersamaan untuk unwrap:**
1. Password (know)
2. Token dongle (have)
3. Database (wrapped + salt)

---

## 🧮 Kenapa Scrypt Lambat itu Bagus?

### Tanpa Scrypt (naive):
```
Hacker brute-force:
- Coba 1 juta password/detik
- Password 8 karakter: ~1 hari

❌ Terlalu cepat!
```

### Dengan Scrypt (memory-hard):
```
Scrypt butuh:
- 100 MB RAM per percobaan
- 0.5 detik per percobaan

Hacker brute-force:
- Coba 2 password/detik
- Password 8 karakter: ~1000 tahun

✅ Praktis tidak mungkin!
```

**Parameter Scrypt dari config.py:**
- `n = 16384` (2^14): CPU cost
- `r = 8`: Memory block size
- `p = 1`: Parallelization
- **Total memory**: ~128 MB per percobaan

---

## 📊 Flow Diagram Visual

```
WRAP (Setup):
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Password │───▶│  Scrypt  │───▶│   KEK    │───▶│ AES-GCM  │
└──────────┘    │  (slow)  │    │ 32 bytes │    │ Encrypt  │
                └──────────┘    └──────────┘    └──────────┘
┌──────────┐          ▲                               │
│  Token   │──────────┘                               │
│ 32 bytes │                                          │
└──────────┘                                          ▼
                                            ┌──────────────────┐
┌──────────┐                                │ Wrapped Master   │
│  Master  │───────────────────────────────▶│ Key (60 bytes)   │
│   Key    │                                │ → DATABASE       │
└──────────┘                                └──────────────────┘
```

```
UNWRAP (Login):
┌──────────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Wrapped Master   │───▶│ AES-GCM  │───▶│  Master  │───▶│  HKDF    │
│ Key (DATABASE)   │    │ Decrypt  │    │   Key    │    │ Derive   │
└──────────────────┘    │          │    │ 32 bytes │    │ Keys     │
                        └──────────┘    └──────────┘    └──────────┘
                              ▲                               │
                        ┌──────────┐                         ▼
┌──────────┐    ┌───▶│   KEK    │              ┌────────────────────┐
│ Password │───▶│    │ 32 bytes │              │ - DB Key           │
└──────────┘    │    └──────────┘              │ - Chat Enc Key     │
                │          ▲                    │ - Chat MAC Key     │
┌──────────┐    │    ┌──────────┐              │ - File Key         │
│  Token   │───▶│───▶│  Scrypt  │              │ - Stego Key        │
│(Dongle)  │         │  (slow)  │              │ - Vigenere Key     │
└──────────┘         └──────────┘              └────────────────────┐
```

---

## 💡 Pertanyaan Dosen & Jawaban

### Q1: Kenapa tidak simpan master key langsung di database?
**A:** Jika database bocor, master key juga bocor. Dengan wrapping, hacker butuh password + dongle yang tidak ada di database.

### Q2: Kenapa tidak enkripsi database saja dengan password?
**A:** Password bisa di-brute force. Dengan dongle, hacker butuh akses fisik ke flashdisk (2-factor).

### Q3: Apa bedanya wrap vs enkripsi biasa?
**A:** Wrap adalah enkripsi khusus untuk kunci. Istilah "wrap" menunjukkan bahwa ini key-encrypting-key (KEK mengenkripsi master key).

### Q4: Kenapa token dongle tidak di-hash saat derive KEK?
**A:** Token adalah entropy tinggi (32 bytes acak). Hash akan mengurangi entropy. Token di-hash hanya untuk disimpan di database (verifikasi dongle), bukan untuk kriptografi.

### Q5: Bagaimana kalau dongle hilang?
**A:** Ada file `recovery.key` (dibuat saat setup, disimpan offline). File ini berisi master key yang di-wrap dengan password pemulihan terpisah.

### Q6: Apa bedanya password login vs password pemulihan?
**A:** 
- **Password login**: untuk unwrap master key (perlu dongle juga)
- **Password pemulihan**: untuk buka recovery.key (TIDAK perlu dongle, karena dongle hilang)

### Q7: Kenapa tidak pakai public-key crypto (RSA)?
**A:** Master key symmetric lebih cepat untuk bulk encryption. Wrapping dengan symmetric crypto (AES) + KDF (Scrypt) sudah cukup aman dengan 2-factor.

### Q8: Bagaimana kalau user ganti password?
**A:** 
1. User login dengan password lama (master key terbuka)
2. Wrap ulang master key dengan KEK baru (password baru + token sama)
3. Update `wrapped_master_key` di database
4. Master key organisasi TIDAK berubah (hanya wrapping-nya)

---

## 🎯 Poin Penting untuk Presentasi

1. **Master key tidak pernah disimpan polos** ✓
2. **2-Factor Authentication built-in** (password + dongle) ✓
3. **Scrypt memory-hard** → melawan brute-force ✓
4. **AES-GCM authenticated encryption** → detect tampering ✓
5. **Recovery mechanism** jika dongle hilang ✓
6. **Key derivation** (HKDF) untuk banyak kunci dari 1 master key ✓
7. **Multi-user support** (master key sama, wrapped berbeda) ✓

---

## 📖 Referensi

- **Scrypt**: RFC 7914 - The scrypt Password-Based Key Derivation Function
- **AES-GCM**: NIST SP 800-38D - Galois/Counter Mode
- **HKDF**: RFC 5869 - HMAC-based Key Derivation Function
- **Key Wrapping**: NIST SP 800-38F - Key Wrap with AES

---

**Dibuat untuk SafeRelief Tahap 1 ✓**  
**Untuk penjelasan ke dosen dengan bahasa sederhana** 📚
