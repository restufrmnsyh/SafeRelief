# SafeRelief: Konteks Proyek untuk Agent Coding

> Baca file ini sepenuhnya sebelum menulis kode apa pun. Ini adalah sumber kebenaran rancangan.
> Jika ada instruksi yang bertentangan dengan file ini, tanyakan ke pengguna, jangan menebak.

## 1. Apa Proyek Ini

Tugas akhir mata kuliah **Kriptografi**. SafeRelief adalah **aplikasi desktop (Windows)** untuk komunitas relawan bencana alam: pendataan korban, chat koordinasi, dokumentasi foto, laporan, dan pencatatan distribusi bantuan, semuanya diamankan dengan kriptografi.

Proyek dinilai dosen berdasarkan kriteria berikut. Semuanya WAJIB terpenuhi:

1. Login biometrik (wajah) dan aplikasi hanya hidup dengan bantuan **dongle** (flashdisk).
2. Login memakai algoritma kriptografi (hash password).
3. Pesan teks dienkripsi dengan **super enkripsi** (klasik + modern).
4. Pesan **file** dienkripsi dengan algoritma yang **berbeda dari teks**.
5. Pesan penting dienkripsi **di basis data**.
6. Pesan **gambar** diamankan dengan **steganografi**.
7. Aset penting diamankan dengan **blockchain sederhana**.

Pengguna adalah mahasiswa yang akan mempresentasikan dan ditanya detail kode. Maka: **kode harus sederhana, terbaca, dan diberi komentar yang menjelaskan "kenapa"**. Hindari abstraksi berlebihan.

## 2. Keputusan Teknis (FINAL, jangan diubah tanpa izin)

| Aspek | Keputusan |
|---|---|
| OS | Windows 10/11 |
| Bahasa | Python 3.11 atau 3.12 |
| UI | **PySide6** (desktop). DILARANG Streamlit, web framework, atau Electron |
| Tema UI | qt-material (opsional) |
| Database | **SQLite** (`sqlite3` bawaan), satu file `data/saferelief.db` |
| Hash password | **Argon2** (`argon2-cffi`) |
| Enkripsi teks (chat) | **Vigenère lalu Blowfish-CBC + HMAC-SHA256** (`pycryptodome`) |
| Enkripsi file | **ChaCha20-Poly1305** (`cryptography`) |
| Enkripsi kolom DB | **AES-256-GCM** (`cryptography`) |
| Steganografi | **LSB pada PNG** (Pillow + numpy) |
| Blockchain | Tulis sendiri: SHA-256 + proof-of-work ringan (`hashlib`) |
| Wajah | OpenCV **YuNet (deteksi) + SFace (embedding)** via `cv2.FaceDetectorYN` dan `cv2.FaceRecognizerSF`. Model `.onnx` di folder `models/` |
| Dongle | `psutil` (cari drive removable) + `ctypes` `GetVolumeInformationW` (serial volume) + file kunci `.saferelief_key` |
| Tes | `pytest` |

Aturan kripto: **jangan membuat algoritma modern sendiri** (AES, Blowfish, ChaCha20, SHA-256, Argon2 pakai library). Yang boleh/harus ditulis sendiri: **Vigenère, blockchain, LSB**.

## 3. Peran Pengguna

- **Admin: tepat 1 orang.** Dibuat HANYA lewat `setup_admin.py` (sekali jalan). Tidak ada fitur membuat admin di UI. Database memaksa ini:
  `CREATE UNIQUE INDEX one_admin_only ON users(role) WHERE role = 'admin';`
  Admin tidak bisa memblokir dirinya sendiri. Tidak ada yang bisa mengubah role menjadi admin.
- **Relawan: banyak.** Dibuat admin lewat UI (nama, username, password awal, daftarkan wajah, daftarkan dongle).

Fitur per peran:

| Fitur | Admin | Relawan |
|---|---|---|
| Buat/edit/aktifkan/blokir relawan, ganti dongle | Ya | Tidak |
| Chat terenkripsi | Ya (pilih relawan dari daftar) | Ya (selalu ke admin, penerima otomatis) |
| Data korban | Lihat semua, edit | Input dan lihat |
| Foto stego | Ekstrak/verifikasi | Unggah dan sisipkan |
| Berkas laporan | Unduh dan dekripsi | Unggah |
| Distribusi bantuan (blockchain) | Catat, validasi, simulasi tampering | Lihat riwayat |
| Log aktivitas | Lihat | Tidak |

Tidak ada chat antar relawan.

## 4. Alur Login (3 faktor, berlaku untuk admin DAN relawan)

1. **Gerbang dongle:** aplikasi tidak menampilkan form login sebelum ada dongle valid tercolok. Pesan hanya "Dongle valid terdeteksi" (jangan bocorkan pemilik).
2. **Username + password:** verifikasi hash Argon2. Cek `is_active`. 3x gagal berturut-turut mengunci akun 5 menit (`failed_attempts`, `locked_until`).
3. **Wajah:** webcam, embedding dibandingkan dengan yang tersimpan (cosine similarity, threshold di konfigurasi).

Aturan:
- **Satu dongle satu orang**: `dongle_serial UNIQUE`. Setelah username diketik, dongle harus cocok dengan akun TERSEBUT (serial + SHA-256 token). Dongle milik orang lain ditolak.
- Dongle dicabut saat aplikasi berjalan: **logout otomatis** (QTimer cek tiap 2 detik) dan master key dihapus dari memori.
- Akun diblokir (`is_active = 0`): login ditolak, sesi aktif diputus. Data tidak dihapus.
- Ganti dongle: hapus serial/token lama, tulis yang baru, catat `DONGLE_REPLACED`.
- Semua event penting dicatat di `activity_log`.

## 5. Manajemen Kunci

Prinsip: **kunci tidak pernah tersimpan utuh di satu tempat**, dan **pengguna tidak pernah mengetik kunci** (hanya password login yang memang diperlukan).

Satu **master key organisasi** (32 byte acak), dibuat saat `setup_admin.py`. Master key TIDAK disimpan polos, dan TIDAK disimpan polos di dongle.

**Faktor kunci:**

| Komponen | Disimpan di | Fungsi |
|---|---|---|
| Token acak 32 byte | **Dongle** (`.saferelief_key`) | Faktor "something you have", bagian dari KEK |
| `wrapped_master_key` + `kdf_salt` | Tabel `users` | Tidak berguna tanpa KEK |
| KEK (key-encrypting key) | Dihitung, tidak disimpan | `Scrypt(password + token_dongle, kdf_salt)` |

- `wrapped_master_key = AES-GCM(KEK, master_key)`.
- Saat login sukses (dongle + password benar), master key dibuka dan disimpan di **memori sesi saja**. Dongle saja tidak cukup, password saja juga tidak cukup.
- Saat admin membuat relawan, admin (yang memegang master key di sesi) membungkusnya dengan KEK relawan itu. Jika password atau dongle berubah, master key dibungkus ulang (butuh sesi yang sedang membuka master key).
- Wajah TIDAK ikut menurunkan kunci (hanya autentikasi).
- **File pemulihan admin:** saat `setup_admin.py`, buat `recovery.key` (master key dibungkus `Scrypt(password pemulihan)`), disimpan offline oleh admin. Dipakai `reset_admin.py` jika dongle admin hilang/rusak.

**Kunci turunan (HKDF-SHA256 dari master key), label `info` berbeda:**

| Label | Dipakai untuk |
|---|---|
| `b"db"` | AES-GCM kolom database (32 byte) |
| `b"chat-enc"` | Blowfish chat (32 byte) |
| `b"chat-mac"` | HMAC-SHA256 chat (32 byte) |
| `b"file"` | ChaCha20-Poly1305 file (32 byte) |
| `b"stego"` | AES-GCM payload steganografi (32 byte) |
| `b"vigenere"` | Kunci Vigenère otomatis: 16 karakter ASCII cetak (32-126), dipetakan dari byte HKDF dengan `32 + (byte % 95)` |

Kunci turunan dihitung di memori, tidak pernah ditulis ke disk atau database. Dilarang menulis kunci/kredensial di dalam kode. Saat logout atau dongle dicabut, master key dan semua kunci turunan dihapus dari memori.

## 6. Spesifikasi Tiap Fitur

### 6.1 Chat teks (super enkripsi)
- Kirim: `Vigenère(plaintext, vig_key)` lalu `Blowfish-CBC`.
- Blowfish: IV acak 8 byte, padding PKCS7, kunci 32 byte. **Encrypt-then-MAC**: `HMAC-SHA256(mac_key, iv + ciphertext)`.
- Format blob: `[IV 8][ciphertext][HMAC 32]`. Disimpan di `messages.ciphertext`.
- Dekripsi: verifikasi HMAC dengan `hmac.compare_digest` SEBELUM dekripsi, lalu Blowfish, lalu Vigenère.
- **Kunci Vigenère otomatis** (diturunkan dari master key, label `b"vigenere"`). Pengguna tidak mengetik kunci: Decrypt cukup satu klik.
- **Mode demo:** di panel chat ada kotak opsional "Gunakan kunci Vigenère manual". Normalnya kosong (pakai kunci otomatis). Jika diisi, kunci manual dipakai untuk dekripsi, sehingga kunci salah menghasilkan teks acak (bukan error) untuk keperluan demo.
- Inbox menampilkan ciphertext (base64/hex) dulu; teks asli muncul setelah Decrypt.
- Vigenère bekerja pada karakter ASCII 32-126 (modulus 95). Karakter lain dibiarkan.

### 6.2 File
- ChaCha20-Poly1305, nonce 12 byte acak di awal file `.enc`.
- File `.enc` disimpan di `storage/` dengan **nama UUID**; nama asli di tabel `files.nama_asli`.
- Dekripsi gagal dengan `InvalidTag` berarti tampilkan "File rusak atau telah diubah" dan catat ke log.
- Relawan unggah; admin unduh dan dekripsi (kunci otomatis dari master key).

### 6.3 Database (kolom sensitif)
- Kolom berakhiran `_enc` berisi BLOB `nonce(12) + ciphertext + tag` AES-GCM, kunci `b"db"`.
- Kolom terenkripsi di `victims`: nama_lengkap, nik, alamat_asal, kondisi_medis, kontak_keluarga, catatan.
- Kolom plaintext: kode_korban, nama_panggilan, usia, gender, posko_id, status.
- Enkripsi/dekripsi HANYA di `database/secure_store.py`. SQL HANYA di `database/db.py`. UI dilarang menulis SQL.
- `PRAGMA foreign_keys = ON` di setiap koneksi. Semua query berparameter (`?`), dilarang f-string untuk nilai.
- `face_encoding` di `users` juga dienkripsi AES-GCM.

### 6.4 Steganografi (foto)
- Payload: `ID korban/posko | koordinat | timestamp | ID petugas | SHA-256 foto asli`, dienkripsi AES-GCM (kunci `b"stego"`) lalu disisipkan ke **LSB kanal RGB** PNG.
- Header 4 byte (panjang payload) di awal. Tolak jika kapasitas tidak cukup (`ValueError` pesan jelas).
- Output selalu PNG (lossless). Input JPG dikonversi dengan peringatan.
- Ekstrak oleh admin menampilkan metadata. Foto yang diedit/dikompres gagal diekstrak.

### 6.5 Blockchain (distribusi bantuan)
- Block: `index, timestamp, data(dict), prev_hash, nonce, hash`.
- Hash = SHA-256 atas JSON terurut (`sort_keys=True`). Difficulty default 3 (hash diawali `"000"`).
- `is_valid()` mengembalikan `(bool, index_block_rusak_atau_None)`.
- Genesis block dibuat saat init. Disimpan di tabel `blockchain`.
- Isi `data`: jenis, jumlah, dari, ke, petugas.
- Tombol **Validasi Chain** dan **Simulasi Tampering** (mengubah jumlah di satu block untuk demo, lalu validasi menunjukkan block rusak).
- Tabel `aid_distribution` TIDAK dipakai; riwayat dibaca langsung dari `blockchain`.

### 6.6 Dongle
- `provision_dongle(drive, user_id)`: tulis `.saferelief_key` berisi token acak 32 byte (hex); simpan serial volume + SHA-256(token) di DB. Tolak serial yang sudah dipakai user lain.
- `verify_dongle(user)`: serial DAN hash token harus cocok.
- Token dongle juga menjadi faktor KEK (lihat bagian 5), jadi dongle bukan sekadar "pemeriksaan", tapi bagian dari kunci.
- **Ganti dongle:** butuh sesi yang membuka master key; token baru ditulis, lalu master key dibungkus ulang dengan KEK baru, dicatat `DONGLE_REPLACED`.
- Keterbatasan (dicatat di laporan): file kunci bisa disalin (tetap butuh password untuk membuka master key), serial berubah jika diformat.

### 6.7 Admin awal (`setup_admin.py`)
Dijalankan sekali dari terminal. Menolak jalan jika admin sudah ada. Langkah: init DB, minta username/password (`getpass`, konfirmasi, min 8 karakter), hash Argon2, provision dongle, tangkap wajah (5 frame), buat master key lalu bungkus dengan KEK (password + token dongle), buat **`recovery.key`** (minta password pemulihan terpisah, simpan di lokasi yang dipilih admin), insert admin. **Atomik**: gagal di tengah berarti tidak ada yang tersimpan. Catat `ADMIN_BOOTSTRAP`.

`reset_admin.py` (opsional): dijalankan di komputer server dengan akses fisik; memakai `recovery.key` + password pemulihan untuk membuka master key, lalu mendaftarkan dongle dan password admin baru.

## 7. Skema Database (ringkas)

- `users`: id, nama_lengkap, username UNIQUE, password_hash, role, posko_id, face_encoding_enc, dongle_serial UNIQUE, dongle_token_hash, wrapped_master_key, kdf_salt, failed_attempts, locked_until, is_active, created_at
- `posko`: id, nama, lokasi, kapasitas, created_at
- `victims`: id, kode_korban UNIQUE, nama_panggilan, usia, gender, posko_id, status, nama_lengkap_enc, nik_enc, alamat_asal_enc, kondisi_medis_enc, kontak_keluarga_enc, catatan_enc, created_by, created_at, updated_at
- `photos`: id, victim_id, posko_id, image_path, original_hash, keterangan, uploaded_by, created_at
- `messages`: id, sender_id, receiver_id, ciphertext, is_read, created_at
- `files`: id, uploader_id, nama_asli, path_enc, ukuran, file_hash, created_at
- `blockchain`: idx PK, timestamp, data, prev_hash, nonce, hash
- `activity_log`: id, user_id, aksi, detail, created_at

## 8. Struktur Proyek

```
safe_relief/
├── crypto/      vigenere.py, aes_module.py, blowfish_module.py, chacha_module.py,
│                hashing.py, keys.py, super_encrypt.py, stego_lsb.py, blockchain.py
├── auth/        dongle.py, face_auth.py, login.py, session.py
├── database/    schema.sql, db.py, secure_store.py
├── ui/          halaman-halaman PySide6
├── models/      model YuNet + SFace (.onnx)
├── data/        saferelief.db (jangan di-commit)
├── storage/     file .enc (jangan di-commit)
├── tests/
├── setup_admin.py
├── app.py
├── config.py
└── requirements.txt
```

Dependensi: PySide6, cryptography, argon2-cffi, pycryptodome, opencv-python, numpy, Pillow, psutil, pytest (opsional: qt-material).

## 9. Aturan Bekerja untuk Agent

1. **Kerjakan satu tahap per sesi** sesuai `TASKS.md`. Jangan mengerjakan tahap berikutnya sebelum tes tahap ini lolos.
2. **Tulis tes (pytest) bersama kodenya**, jalankan, dan laporkan hasilnya. Jangan klaim "sudah jalan" tanpa menjalankannya.
3. **Jangan mengubah modul yang sudah lolos tes** tanpa alasan jelas. Jika perlu, jelaskan dulu.
4. Setiap file: docstring, type hint, dan komentar singkat tentang alasan desain (pengguna akan menjelaskannya ke dosen).
5. **Jangan menambah fitur, library, atau mengganti keputusan di bagian 2** tanpa bertanya.
6. Jangan hardcode kunci, password, atau token. Jangan log data sensitif/plaintext.
7. Operasi berat (kamera, enkripsi file besar) di `QThread`, UI tidak boleh membeku.
8. Setelah tahap selesai, ringkas: file yang dibuat, cara menjalankan tes, dan hal yang perlu dipahami pengguna.
9. Jika ada ambiguitas, **tanya satu pertanyaan jelas**, jangan menebak diam-diam.
10. Pesan commit: satu tahap, satu commit (usulkan pesannya, biarkan pengguna yang commit).
11. Kode ini untuk demo tugas kuliah; keterbatasannya dicatat jujur, bukan disembunyikan.

## 10. Keterbatasan yang Diakui (untuk laporan)

LSB rapuh terhadap kompresi; tidak ada liveness detection wajah; Vigenère lemah secara kriptanalisis (lapisan klasik); Blowfish blok 64-bit; blockchain lokal tidak terdistribusi; satu master key dan satu admin (jika dongle admin hilang, pemulihan lewat `recovery.key` yang disimpan offline; tanpa file itu, data tidak bisa dipulihkan); file kunci dongle bisa disalin.
