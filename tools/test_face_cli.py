"""
SafeRelief - Uji Face Authentication via CLI (tools/test_face_cli.py)

Skrip ini dijalankan MANUAL dari terminal untuk menguji face authentication
dengan webcam fisik. Tidak bisa dijalankan di CI/unit test karena butuh
kamera nyata.

Cara pakai:
    python tools/test_face_cli.py

Skrip akan:
  1. Capture n frame dari webcam (default: config.FACE_CAPTURE_FRAMES)
     untuk membuat "stored embedding" (simulasi data tersimpan di DB).
  2. Minta user menekan Enter, lalu capture 1 frame lagi untuk verifikasi.
  3. Cetak skor cosine similarity dan apakah verifikasi berhasil.

Contoh output normal (wajah sama):
    [CAPTURE] Mengambil 5 frame...
    [CAPTURE] Berhasil: 5 embedding dikumpulkan.
    Tekan Enter untuk mulai verifikasi...
    [VERIFY] Skor similarity: 0.512
    [VERIFY] MATCH (threshold: 0.363) ✓

Contoh output saat wajah berbeda / tidak ada wajah:
    [VERIFY] Skor similarity: 0.201
    [VERIFY] NO MATCH (threshold: 0.363) ✗

Keluar dari skrip: Ctrl+C

Requirements:
  - Webcam tercolok dan bisa diakses (index 0)
  - Model ONNX ada di models/ (lihat models/README.md)
  - Jalankan dari root proyek: python tools/test_face_cli.py
"""

import sys
from pathlib import Path

# Tambahkan root proyek ke sys.path agar import bekerja saat dijalankan
# dari subfolder mana pun.
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import cv2
import numpy as np

import config
from auth.face_auth import (
    capture_encodings,
    verify_face,
    cosine_similarity,
    _detect_and_embed,
)


def _check_models() -> bool:
    """Periksa apakah kedua model ONNX tersedia."""
    missing = []
    if not config.YUNET_MODEL.exists():
        missing.append(str(config.YUNET_MODEL))
    if not config.SFACE_MODEL.exists():
        missing.append(str(config.SFACE_MODEL))

    if missing:
        print("=" * 60)
        print("ERROR: Model ONNX belum tersedia:")
        for m in missing:
            print(f"  - {m}")
        print()
        print("Unduh model terlebih dahulu.")
        print("Lihat instruksi di models/README.md")
        print("=" * 60)
        return False
    return True


def main() -> None:
    print("=" * 60)
    print("  SafeRelief - Face Authentication CLI Test")
    print("=" * 60)
    print()

    # --- Cek model ---
    if not _check_models():
        sys.exit(1)

    n = config.FACE_CAPTURE_FRAMES
    print(f"[INFO] Threshold: {config.FACE_MATCH_THRESHOLD}")
    print(f"[INFO] Frame per capture: {n}")
    print()

    # ── Langkah 1: Capture embedding referensi ────────────────────────
    print(f"[CAPTURE] Posisikan wajah di depan kamera.")
    print(f"[CAPTURE] Mengambil {n} frame...")
    try:
        stored = capture_encodings(n)
        print(f"[CAPTURE] Berhasil: embedding shape={stored.shape}")
    except (ValueError, FileNotFoundError) as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print()
    input("Tekan Enter untuk mulai verifikasi (boleh ganti orang)...")
    print()

    # ── Langkah 2: Capture frame untuk verifikasi ─────────────────────
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Tidak bisa membuka webcam.")
        sys.exit(1)

    print("[VERIFY] Mengambil frame verifikasi...")
    frame = None
    for _ in range(30):      # beri toleransi 30 frame
        ret, f = cap.read()
        if ret and f is not None:
            frame = f
            break
    cap.release()

    if frame is None:
        print("[ERROR] Tidak bisa membaca frame dari webcam.")
        sys.exit(1)

    # ── Langkah 3: Verifikasi ─────────────────────────────────────────
    match, score = verify_face(stored, frame)

    print(f"[VERIFY] Skor cosine similarity : {score:.4f}")
    print(f"[VERIFY] Threshold              : {config.FACE_MATCH_THRESHOLD}")

    if score == 0.0:
        print("[VERIFY] Wajah TIDAK TERDETEKSI di frame verifikasi.")
    elif match:
        print(f"[VERIFY] MATCH ✓  (wajah dikenali)")
    else:
        print(f"[VERIFY] NO MATCH ✗  (wajah tidak dikenali atau orang berbeda)")

    # ── Opsional: tampilkan preview frame ─────────────────────────────
    print()
    show = input("Tampilkan preview frame? (y/N): ").strip().lower()
    if show == "y":
        cv2.imshow("Verifikasi Frame", frame)
        print("Tekan tombol apa saja untuk menutup preview.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    print()
    print("[SELESAI]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[DIBATALKAN] Ctrl+C diterima.")
        sys.exit(0)
