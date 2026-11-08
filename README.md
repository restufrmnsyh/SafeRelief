# SafeRelief

Aplikasi desktop untuk komunitas relawan bencana alam dengan keamanan kriptografi end-to-end.

## 📋 Deskripsi

SafeRelief adalah aplikasi desktop Windows yang mengamankan data relawan bencana dengan berbagai teknik kriptografi:
- Login 3 faktor: dongle (flashdisk) + password + biometrik wajah
- Enkripsi chat dengan super enkripsi (Vigenère + Vernam XOR/HKDF-SHA256 + HMAC)
- Enkripsi file dengan ChaCha20-Poly1305
- Enkripsi database dengan AES-256-GCM
- Steganografi LSB untuk metadata foto
- Blockchain sederhana untuk audit distribusi bantuan

## 🎯 Fitur

- **Autentikasi Multi-Faktor**: Dongle, password (Argon2), dan pengenalan wajah (YuNet + SFace)
- **Chat Terenkripsi**: Super enkripsi Vigenère → Vernam XOR/HKDF → HMAC
- **Data Korban**: Enkripsi kolom sensitif di database
- **Dokumentasi Foto**: Steganografi untuk menyisipkan metadata
- **Berkas Laporan**: Enkripsi file dengan ChaCha20-Poly1305
- **Distribusi Bantuan**: Blockchain dengan proof-of-work
- **Manajemen Relawan**: Admin dapat mengelola akun dan dongle
- **Activity Log**: Audit trail semua aksi penting

## 🛠️ Teknologi

- **Bahasa**: Python 3.11/3.12
- **UI**: PySide6 (Qt untuk Python)
- **Database**: SQLite
- **Kriptografi**:
  - Hash password: Argon2
  - Enkripsi chat: Vigenère + Vernam XOR dengan keystream HKDF-SHA256 + HMAC-SHA256
  - Enkripsi file: ChaCha20-Poly1305
  - Enkripsi database: AES-256-GCM
  - Steganografi: LSB pada PNG
  - Blockchain: SHA-256 + proof-of-work
- **Biometrik**: OpenCV dengan model YuNet dan SFace
- **Dongle**: psutil + ctypes (Windows API)

## 📦 Instalasi

1. Clone repository:
```bash
git clone <repository-url>
cd SafeRelief
```

2. Install dependensi:
```bash
pip install -r requirements.txt
```

3. Unduh model ONNX untuk face recognition dan letakkan di folder `models/`:
   - `face_detection_yunet_2023mar.onnx`
   - `face_recognition_sface_2021dec.onnx`

## 🚀 Cara Pakai

### Setup Pertama Kali

1. Siapkan flashdisk untuk dongle admin
2. Jalankan setup admin:
```bash
python setup_admin.py
```
3. Ikuti instruksi untuk membuat admin pertama

### Menjalankan Aplikasi

```bash
python app.py
```

**PENTING**: Aplikasi hanya bisa dijalankan jika dongle yang valid tercolok.

## 📁 Struktur Proyek

```
SafeRelief/
├── crypto/          # Modul kriptografi
│   ├── vigenere.py
│   ├── aes_module.py
│   ├── vernam_module.py
│   ├── chacha_module.py
│   ├── hashing.py
│   ├── keys.py
│   ├── super_encrypt.py
│   ├── stego_lsb.py
│   └── blockchain.py
├── auth/            # Autentikasi
│   ├── dongle.py
│   ├── face_auth.py
│   ├── login.py
│   └── session.py
├── database/        # Database
│   ├── schema.sql
│   ├── db.py
│   └── secure_store.py
├── ui/              # Antarmuka pengguna (PySide6)
├── models/          # Model ONNX untuk face recognition
├── data/            # Database SQLite (tidak di-commit)
├── storage/         # File terenkripsi (tidak di-commit)
├── tests/           # Unit tests (pytest)
├── config.py        # Konfigurasi aplikasi
├── app.py           # Entry point
├── setup_admin.py   # Setup admin awal
└── requirements.txt # Dependensi Python
```

## 🧪 Testing

Jalankan semua tes:
```bash
pytest tests/ -v
```

Jalankan tes spesifik:
```bash
pytest tests/test_crypto.py -v
pytest tests/test_db.py -v
```

## 🔒 Keamanan

### Manajemen Kunci

- **Master Key**: 32 byte acak, tidak pernah disimpan polos
- **KEK (Key-Encrypting Key)**: Diturunkan dari `Scrypt(password + token_dongle)`
- **Wrapped Master Key**: Tersimpan di database, hanya bisa dibuka dengan KEK yang benar
- **Kunci Turunan**: Diturunkan dari master key dengan HKDF untuk berbagai keperluan
- **Recovery Key**: File backup untuk pemulihan jika dongle admin hilang

### Keterbatasan

- LSB rapuh terhadap kompresi gambar
- Tidak ada liveness detection untuk wajah
- Vigenère lemah secara kriptanalisis (hanya lapisan demonstrasi)
- Vernam bukan OTP murni: keystream pseudo-acak dari HKDF tidak memberi perfect secrecy
- Nonce 16 byte wajib unik untuk setiap pesan; reuse keystream memungkinkan two-time-pad attack
- HMAC hanya mengautentikasi nonce dan ciphertext, sehingga key Vernam yang salah menghasilkan bytes berbeda tanpa bisa dideteksi
- Panjang ciphertext membocorkan panjang pesan dan batas pesan adalah 8160 byte
- Blockchain bersifat lokal, tidak terdistribusi
- Satu master key untuk organisasi
- File kunci dongle bisa disalin (tetap butuh password)
- Serial volume berubah jika flashdisk diformat

## 📚 Dokumentasi

- `AGENTS.md`: Panduan lengkap untuk development
- `TASKS.md`: Daftar tugas bertahap
- `config.py`: Dokumentasi semua parameter konfigurasi

## 👥 Peran Pengguna

### Admin (1 orang)
- Membuat dan mengelola akun relawan
- Melihat semua data korban
- Chat dengan relawan
- Ekstrak metadata foto steganografi
- Unduh dan dekripsi laporan
- Catat distribusi bantuan ke blockchain
- Lihat activity log

### Relawan (banyak)
- Input data korban
- Chat dengan admin
- Unggah foto dengan steganografi
- Unggah laporan terenkripsi
- Lihat riwayat distribusi bantuan

## 📄 Lisensi

Proyek tugas akhir mata kuliah Kriptografi.

## ⚠️ Catatan

Aplikasi ini dibuat untuk keperluan **demonstrasi dan pembelajaran** dalam konteks tugas kuliah. Tidak disarankan untuk digunakan di produksi tanpa audit keamanan menyeluruh dan perbaikan keterbatasan yang telah didokumentasikan.
