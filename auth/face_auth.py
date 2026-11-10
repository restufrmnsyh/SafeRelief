"""
SafeRelief - Face Authentication (4c)

Autentikasi biometrik menggunakan OpenCV YuNet (deteksi) + SFace (pengenalan).

Pipeline:
  Frame webcam
    → YuNet: deteksi bounding box + landmark
    → SFace: ekstrak embedding (128-dim float vector)
    → cosine similarity antara dua embedding
    → bandingkan dengan config.FACE_MATCH_THRESHOLD

Kenapa YuNet + SFace:
- Tersedia langsung di opencv-python (cv2.FaceDetectorYN / FaceRecognizerSF)
- Model ONNX ringan, bisa jalan di laptop tanpa GPU
- Tidak perlu library face_recognition yang butuh dlib/cmake

Keterbatasan (untuk laporan):
- Tidak ada liveness detection (foto bisa lolos)
- Embedding tidak dienkripsi saat di RAM (hanya saat disimpan ke DB)
- Threshold 0.363 default dari paper SFace; butuh kalibrasi per lingkungan

Model harus tersedia di config.YUNET_MODEL dan config.SFACE_MODEL.
Jika belum ada, fungsi yang membutuhkan model raise FileNotFoundError
dengan instruksi jelas cara mengunduh.
"""

from pathlib import Path
from typing import Optional

import cv2
import numpy as np


def _open_camera(index: int = 0) -> cv2.VideoCapture:
    """Buka webcam dengan backend Windows DirectShow terlebih dahulu."""
    candidate_backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        candidate_backends.append(cv2.CAP_DSHOW)
    if hasattr(cv2, "CAP_MSMF"):
        candidate_backends.append(cv2.CAP_MSMF)
    candidate_backends.extend([cv2.CAP_ANY, -1])

    for backend in candidate_backends:
        try:
            cap = cv2.VideoCapture(index, backend)
        except cv2.error:
            continue
        if cap.isOpened():
            return cap

    cap = cv2.VideoCapture(index)
    if cap.isOpened():
        return cap
    raise ValueError(
        "Webcam tidak dapat dibuka. Pastikan kamera tercolok dan "
        "tidak dipakai aplikasi lain."
    )

import config


# ──────────────────────────────────────────────────────────────────────
# Inisialisasi model (lazy — hanya dimuat saat pertama dipakai)
# ──────────────────────────────────────────────────────────────────────

_detector: Optional[cv2.FaceDetectorYN]    = None
_recognizer: Optional[cv2.FaceRecognizerSF] = None


def _get_detector() -> cv2.FaceDetectorYN:
    """Lazy-load YuNet detector."""
    global _detector
    if _detector is None:
        model_path = config.YUNET_MODEL
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Model YuNet tidak ditemukan: {model_path}\n"
                "Unduh dari https://github.com/opencv/opencv_zoo/tree/main/"
                "models/face_detection_yunet dan simpan ke folder models/."
            )
        _detector = cv2.FaceDetectorYN.create(
            str(model_path),
            "",
            (320, 320),   # ukuran input default; di-resize sesuai frame nanti
        )
    return _detector


def _get_recognizer() -> cv2.FaceRecognizerSF:
    """Lazy-load SFace recognizer."""
    global _recognizer
    if _recognizer is None:
        model_path = config.SFACE_MODEL
        if not Path(model_path).exists():
            raise FileNotFoundError(
                f"Model SFace tidak ditemukan: {model_path}\n"
                "Unduh dari https://github.com/opencv/opencv_zoo/tree/main/"
                "models/face_recognition_sface dan simpan ke folder models/.\n"
                "Lihat models/README.md untuk instruksi lengkap."
            )
        _recognizer = cv2.FaceRecognizerSF.create(str(model_path), "")
    return _recognizer


# ──────────────────────────────────────────────────────────────────────
# Fungsi inti
# ──────────────────────────────────────────────────────────────────────

def _detect_and_embed(frame: np.ndarray) -> Optional[np.ndarray]:
    """
    Deteksi wajah di frame lalu ekstrak embedding.

    Args:
        frame: Gambar BGR (numpy uint8 array dari cv2.VideoCapture).

    Returns:
        Embedding 1D float32 array (128 dimensi), atau None jika tidak
        ada wajah terdeteksi.
    """
    detector = _get_detector()
    recognizer = _get_recognizer()

    h, w = frame.shape[:2]

    # Set ukuran input detector sesuai resolusi frame
    detector.setInputSize((w, h))

    _, faces = detector.detect(frame)
    if faces is None or len(faces) == 0:
        return None

    # Pakai wajah pertama (asumsi: satu orang di frame)
    face = faces[0]

    # Align + crop wajah sebelum ekstrak embedding
    aligned = recognizer.alignCrop(frame, face)

    # Ekstrak embedding (128-dim float32 vector)
    embedding = recognizer.feature(aligned)  # shape: (1, 128)
    return embedding.flatten()               # → (128,)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Hitung cosine similarity antara dua embedding.

    Cosine similarity = dot(a, b) / (||a|| * ||b||)
    Rentang: -1.0 (berlawanan) s/d 1.0 (identik).
    Wajah yang sama biasanya menghasilkan nilai > 0.363.

    Args:
        a: Embedding pertama (1D float array).
        b: Embedding kedua (1D float array).

    Returns:
        Nilai similarity float dalam rentang [-1.0, 1.0].

    Raises:
        ValueError: Jika salah satu embedding nol (norm = 0).
    """
    a = np.asarray(a, dtype=np.float32).flatten()
    b = np.asarray(b, dtype=np.float32).flatten()

    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("Embedding tidak boleh berupa vektor nol.")

    return float(np.dot(a, b) / (norm_a * norm_b))


def capture_encodings(n: int = None) -> np.ndarray:
    """
    Capture n frame dari webcam, deteksi wajah, rata-ratakan embedding.

    Dipakai saat REGISTRASI wajah (setup admin / tambah relawan).
    Merata-ratakan beberapa frame meningkatkan robustness embedding.

    Args:
        n: Jumlah frame yang berhasil dikumpulkan. Default: config.FACE_CAPTURE_FRAMES.

    Returns:
        Embedding rata-rata (1D float32 array, 128 dimensi).

    Raises:
        ValueError: Webcam tidak bisa dibuka.
        ValueError: Tidak ada wajah terdeteksi di seluruh frame.
        FileNotFoundError: Model ONNX belum diunduh.
    """
    if n is None:
        n = config.FACE_CAPTURE_FRAMES

    cap = _open_camera(0)

    embeddings = []
    max_attempts = n * 10  # beri toleransi frame tanpa wajah
    attempts = 0

    try:
        while len(embeddings) < n and attempts < max_attempts:
            ret, frame = cap.read()
            attempts += 1
            if not ret or frame is None:
                continue

            emb = _detect_and_embed(frame)
            if emb is not None:
                embeddings.append(emb)
    finally:
        cap.release()

    if not embeddings:
        raise ValueError(
            f"Wajah tidak terdeteksi setelah {attempts} frame. "
            "Pastikan wajah berada di depan kamera dengan pencahayaan cukup."
        )

    # Rata-ratakan semua embedding yang berhasil dikumpulkan
    avg = np.mean(embeddings, axis=0).astype(np.float32)
    return avg


def verify_face(
    stored_encoding: np.ndarray,
    frame: np.ndarray,
) -> tuple[bool, float]:
    """
    Verifikasi apakah wajah di frame cocok dengan embedding tersimpan.

    Dipakai saat LOGIN (faktor ketiga dari tiga faktor autentikasi).

    Args:
        stored_encoding: Embedding yang tersimpan di DB (dari capture_encodings).
        frame           : Frame BGR dari webcam saat login.

    Returns:
        (match, score) di mana:
        - match: True jika score >= config.FACE_MATCH_THRESHOLD
        - score: Cosine similarity (float, -1.0 s/d 1.0)
        Jika wajah tidak terdeteksi di frame: (False, 0.0)

    Raises:
        FileNotFoundError: Model ONNX belum diunduh.
    """
    live_embedding = _detect_and_embed(frame)
    if live_embedding is None:
        return False, 0.0

    score = cosine_similarity(stored_encoding, live_embedding)
    match = score >= config.FACE_MATCH_THRESHOLD
    return match, score


def encoding_to_bytes(encoding: np.ndarray) -> bytes:
    """
    Serialisasi embedding ke bytes untuk disimpan ke DB (setelah enkripsi AES).

    Format: numpy float32 array → tobytes() (little-endian, 128 × 4 = 512 byte)
    """
    return np.asarray(encoding, dtype=np.float32).flatten().tobytes()


def bytes_to_encoding(data: bytes) -> np.ndarray:
    """
    Deserialisasi bytes ke embedding numpy array.

    Kebalikan dari encoding_to_bytes().
    """
    return np.frombuffer(data, dtype=np.float32).copy()
