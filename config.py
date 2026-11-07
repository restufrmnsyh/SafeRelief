"""
Konfigurasi SafeRelief.

File ini berisi path, konstanta, dan parameter sistem.
Tidak ada kunci/password yang di-hardcode di sini.
"""
import os
from pathlib import Path

# ===== Path Proyek =====
BASE_DIR = Path(__file__).parent.resolve()

# Database
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "saferelief.db"

# Storage untuk file terenkripsi
STORAGE_DIR = BASE_DIR / "storage"

# Model ONNX untuk face recognition
MODELS_DIR = BASE_DIR / "models"
YUNET_MODEL = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = MODELS_DIR / "face_recognition_sface_2021dec.onnx"

# ===== Blockchain =====
# Difficulty: jumlah leading zeros di hash SHA-256
# 3 = "000..." (ringan, cocok untuk demo)
# 4 = "0000..." (lebih berat)
BLOCKCHAIN_DIFFICULTY = 3

# ===== Face Recognition =====
# Threshold cosine similarity untuk menganggap wajah cocok
# Rentang: 0.0 (berbeda) s/d 1.0 (identik)
# Default YuNet+SFace: 0.363 (tuning bisa disesuaikan)
FACE_MATCH_THRESHOLD = 0.363

# Jumlah frame wajah yang ditangkap saat registrasi
# Beberapa frame dirata-rata untuk embedding yang lebih robust
FACE_CAPTURE_FRAMES = 5

# ===== Login Security =====
# Batas percobaan login gagal sebelum akun dikunci
MAX_LOGIN_ATTEMPTS = 3

# Durasi penguncian akun dalam detik (5 menit)
ACCOUNT_LOCK_DURATION = 300

# ===== Dongle Verification =====
# Interval pengecekan dongle (detik) saat aplikasi berjalan
# QTimer akan cek tiap 2 detik apakah dongle masih tercolok
DONGLE_CHECK_INTERVAL = 2

# Nama file kunci di dongle
DONGLE_KEY_FILE = ".saferelief_key"

# ===== Master Key =====
# Panjang master key organisasi (bytes)
MASTER_KEY_LENGTH = 32

# Panjang token dongle (bytes)
DONGLE_TOKEN_LENGTH = 32

# ===== Enkripsi =====
# Nonce/IV lengths (bytes)
AES_GCM_NONCE_LENGTH = 12
CHACHA20_NONCE_LENGTH = 12
BLOWFISH_IV_LENGTH = 8

# HMAC (bytes)
HMAC_SHA256_LENGTH = 32

# Vigenère key length (karakter ASCII cetak 32-126)
VIGENERE_KEY_LENGTH = 16

# ===== Argon2 Parameters =====
# Parameter untuk hashing password pengguna
# time_cost: iterasi (default 2, lebih tinggi = lebih lambat & aman)
# memory_cost: KB memori (default 102400 = 100 MB)
# parallelism: thread (default 8)
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 102400
ARGON2_PARALLELISM = 8

# ===== Scrypt Parameters =====
# Parameter untuk derive KEK (Key Encrypting Key)
# n: CPU/memory cost (2^14 = 16384)
# r: block size (8)
# p: parallelization (1)
SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1

# ===== UI =====
# Window size
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# ===== Logging =====
# Format timestamp untuk activity_log
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

# ===== File Upload Limits =====
# Batas ukuran file upload (bytes) - 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# ===== Steganografi =====
# Format output gambar steganografi
STEGO_OUTPUT_FORMAT = "PNG"  # Harus PNG (lossless)

# ===== HKDF Labels =====
# Label untuk key derivation dari master key
# JANGAN DIUBAH setelah data ada (akan membuat data tidak terbaca)
HKDF_LABEL_DB = b"db"
HKDF_LABEL_CHAT_ENC = b"chat-enc"
HKDF_LABEL_CHAT_MAC = b"chat-mac"
HKDF_LABEL_FILE = b"file"
HKDF_LABEL_STEGO = b"stego"
HKDF_LABEL_VIGENERE = b"vigenere"


def ensure_directories():
    """
    Pastikan direktori yang diperlukan ada.
    Dipanggil saat aplikasi start atau setup.
    """
    DATA_DIR.mkdir(exist_ok=True)
    STORAGE_DIR.mkdir(exist_ok=True)
    MODELS_DIR.mkdir(exist_ok=True)


if __name__ == "__main__":
    # Test: print konfigurasi
    ensure_directories()
    print("SafeRelief Configuration")
    print("=" * 50)
    print(f"Base Directory: {BASE_DIR}")
    print(f"Database: {DB_PATH}")
    print(f"Storage: {STORAGE_DIR}")
    print(f"Models: {MODELS_DIR}")
    print(f"Blockchain Difficulty: {BLOCKCHAIN_DIFFICULTY}")
    print(f"Face Threshold: {FACE_MATCH_THRESHOLD}")
    print(f"Max Login Attempts: {MAX_LOGIN_ATTEMPTS}")
    print(f"Account Lock Duration: {ACCOUNT_LOCK_DURATION}s")
    print("=" * 50)
    print("Directories created successfully!")
