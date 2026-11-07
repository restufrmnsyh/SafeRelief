# SafeRelief: Daftar Tugas Bertahap

Kerjakan berurutan. Tiap tahap punya **syarat lulus**; jangan lanjut sebelum terpenuhi.
Rujukan rancangan: `AGENTS.md`.

## Tahap 0: Lingkungan
- [ ] Buat struktur folder sesuai AGENTS.md bagian 8 (+ `__init__.py` di folder kode)
- [ ] `requirements.txt` sesuai daftar dependensi
- [ ] `.gitignore` (venv, data/, storage/, __pycache__, *.db, *.enc)
- [ ] `config.py`: path DB, folder storage, difficulty blockchain, threshold wajah, durasi kunci akun
- **Lulus:** `python -c "import PySide6, cryptography, argon2, Crypto, cv2, PIL, psutil; print('OK')"` mencetak `OK`

## Tahap 1: Modul kripto dasar
- [ ] `crypto/vigenere.py` (ASCII 32-126)
- [ ] `crypto/aes_module.py` (AES-256-GCM, nonce+ct+tag)
- [ ] `crypto/blowfish_module.py` (CBC + HMAC encrypt-then-MAC)
- [ ] `crypto/chacha_module.py` (bytes dan file)
- [ ] `crypto/hashing.py` (Argon2, SHA-256)
- [ ] `crypto/keys.py` (HKDF label db/chat-enc/chat-mac/file/stego/vigenere; `derive_vigenere_key` menghasilkan 16 karakter ASCII 32-126; Scrypt KEK dari password + token dongle; wrap/unwrap master key; buat dan buka file pemulihan)
- [ ] `crypto/super_encrypt.py`
- [ ] `tests/test_crypto.py`
- **Tes wajib:** round-trip tiap algoritma; kunci salah gagal; ubah 1 byte gagal (GCM, Poly1305, HMAC); kunci Vigenère salah menghasilkan teks berbeda (bukan error); hash password berbeda untuk password sama; unwrap master key dengan password salah gagal; unwrap dengan token dongle salah gagal; unwrap hanya berhasil jika password DAN token benar; kunci Vigenère turunan deterministik (master key sama menghasilkan kunci sama) dan semua karakternya dalam rentang 32-126; file pemulihan bisa dibuka dengan password pemulihan yang benar saja.
- **Lulus:** `pytest tests/test_crypto.py -v` hijau semua.

## Tahap 2: Steganografi dan blockchain
- [ ] `crypto/stego_lsb.py` (embed, extract, capacity)
- [ ] `crypto/blockchain.py` (Block, Blockchain, PoW, is_valid, to_list/load_from_list)
- [ ] `tests/test_stego.py`, `tests/test_blockchain.py`
- **Tes wajib:** round-trip stego; payload terlalu besar ditolak; selisih piksel maksimal 1 per kanal; ubah data block terdeteksi dan menunjuk index yang benar; ubah prev_hash terdeteksi.
- **Lulus:** semua tes hijau. Cek visual: gambar asli dan stego tampak sama.

## Tahap 3: Database
- [ ] `database/schema.sql` (termasuk `one_admin_only` dan `dongle_serial UNIQUE`)
- [ ] `database/db.py` (get_connection, init_db, CRUD, SQL berparameter)
- [ ] `database/secure_store.py` (enkripsi/dekripsi kolom `_enc`)
- [ ] `tests/test_db.py` (DB sementara via `tmp_path`)
- **Tes wajib:** admin kedua ditolak oleh DB; dongle_serial duplikat ditolak; korban tersimpan terenkripsi dan terbaca kembali; foreign key aktif.
- **Lulus:** buka `.db` di DB Browser for SQLite, kolom `nik_enc` berupa data acak.

## Tahap 4: Autentikasi
Kerjakan berurutan dan uji manual tiap sub-tahap.
- [x] 4a `auth/login.py`: verifikasi password, hitung gagal, kunci akun, cek `is_active`, catat log
- [x] 4b `auth/dongle.py`: find_removable_drives, get_volume_serial, provision_dongle, verify_dongle
- [x] 4c `auth/face_auth.py` + skrip uji CLI webcam (unduh model YuNet dan SFace ke `models/`)
- [x] 4d `auth/session.py`: simpan user aktif + master key di memori, clear saat logout
- [x] 4e `setup_admin.py` (atomik, menolak jika admin ada, membuat master key terbungkus dan `recovery.key`)
- [ ] 4f `reset_admin.py` (opsional): pemulihan lewat `recovery.key`
- **Lulus:** master key hanya terbuka jika dongle dan password benar; wajah sendiri lolos, wajah orang lain ditolak; dongle orang lain ditolak; 3x salah password mengunci akun; `setup_admin.py` kedua kali menolak jalan.

## Tahap 5: UI PySide6
Satu halaman per sesi. UI hanya memanggil `secure_store`/`auth`, tanpa SQL.
- [x] 5.1 Jendela utama + gerbang dongle (`QStackedWidget`, `QTimer` 2 detik)
- [x] 5.2 Login (form + kamera di `QThread`)
- [x] 5.3 Dashboard (menu menyesuaikan peran)
- [x] 5.4 Data korban (tabel, cari, filter, tambah/edit/detail)
- [x] 5.5 Chat (ciphertext di inbox, tombol Decrypt satu klik dengan kunci Vigenère otomatis, kotak opsional "kunci Vigenère manual" untuk demo)
- [x] 5.6 Dokumentasi foto (sisipkan dan ekstrak)
- [x] 5.7 Berkas laporan (unggah, daftar, dekripsi/unduh)
- [ ] 5.8 Distribusi bantuan (catat, riwayat, Validasi Chain, Simulasi Tampering)
- [x] 5.9 Manajemen relawan (admin: buat, edit, aktif/blokir, daftar wajah, daftar/ganti dongle; ganti dongle dan reset password membungkus ulang master key)
- [ ] 5.10 Log aktivitas (admin)
- [ ] 5.11 Panel Demo: ciphertext vs plaintext berdampingan
- **Lulus:** tiap halaman bisa dipakai tanpa error dan UI tidak membeku.

## Tahap 6: Integrasi
- [ ] Logout otomatis saat dongle dicabut (hapus master key dari memori)
- [ ] Pembatasan menu dan fungsi per peran (cek di lapisan logika, bukan hanya menyembunyikan tombol)
- [ ] Blokir akun memutus sesi
- [ ] Data contoh (seed): 1 admin (via setup), 2 relawan, sekitar 10 korban, 5 block bantuan
- [ ] `reset_admin.py` (pemulihan lewat akses fisik, opsional)

## Tahap 7: Pengujian dan Demo
- [ ] Jalankan checklist demo di laptop presentasi:
  - [ ] Tanpa dongle aplikasi menolak jalan
  - [ ] 3x gagal login mengunci akun
  - [ ] DB Browser menampilkan ciphertext
  - [ ] Stego: ekstrak berhasil; gambar yang diedit gagal
  - [ ] File `.enc` diubah 1 byte gagal didekripsi
  - [ ] Validasi chain mendeteksi tampering
  - [ ] Cabut dongle membuat aplikasi logout
- [ ] Rekam video demo cadangan
- [ ] Bantu menyusun daftar keterbatasan dan diagram untuk laporan