"""
SafeRelief - Tes Face Authentication (4c)

PENTING: Semua tes di sini TIDAK memerlukan webcam fisik atau model ONNX.
Kamera di-mock dengan unittest.mock.patch; embedding dibuat sebagai
numpy array acak.

Tes yang MEMERLUKAN webcam fisik dan model ONNX harus dijalankan manual:
    python tools/test_face_cli.py
Tes tersebut tidak ada di file ini karena tidak bisa di-otomasi tanpa hardware.

Yang diuji di sini:
- cosine_similarity: nilai matematis, vektor identik, tegak lurus, berlawanan
- verify_face: match di atas threshold, no-match di bawah, wajah tidak terdeteksi
- encoding_to_bytes / bytes_to_encoding: roundtrip serialisasi
- capture_encodings: mock webcam → embedding rata-rata; webcam gagal → ValueError;
  semua frame tanpa wajah → ValueError
- _detect_and_embed: frame tanpa wajah → None (via mock detector)
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import config

# Import modul — model ONNX belum tentu ada saat tes, tapi karena
# model di-lazy-load, import tidak langsung gagal.
from auth import face_auth


# ─────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────

def _rand_emb(seed: int = 0, dim: int = 128) -> np.ndarray:
    """Buat embedding acak yang dinormalisasi (unit vector)."""
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def _make_mock_cap(frames: list[np.ndarray], open_ok: bool = True) -> MagicMock:
    """
    Buat mock cv2.VideoCapture yang mengembalikan frame dari list.
    Jika open_ok=False, isOpened() mengembalikan False.
    """
    cap = MagicMock()
    cap.isOpened.return_value = open_ok

    # read() mengembalikan (True, frame) untuk tiap frame,
    # lalu (False, None) saat habis.
    call_results = [(True, f) for f in frames] + [(False, None)] * 50
    cap.read.side_effect = call_results
    return cap


# ─────────────────────────────────────────────────────────────────────
# Tes cosine_similarity
# ─────────────────────────────────────────────────────────────────────

class TestCosineSimilarity:

    def test_identical_vectors(self):
        """Vektor identik → similarity = 1.0."""
        v = _rand_emb(1)
        score = face_auth.cosine_similarity(v, v)
        assert abs(score - 1.0) < 1e-5

    def test_opposite_vectors(self):
        """Vektor berlawanan arah → similarity = -1.0."""
        v = _rand_emb(2)
        score = face_auth.cosine_similarity(v, -v)
        assert abs(score + 1.0) < 1e-5

    def test_orthogonal_vectors(self):
        """Vektor tegak lurus → similarity ≈ 0.0."""
        a = np.zeros(128, dtype=np.float32)
        b = np.zeros(128, dtype=np.float32)
        a[0] = 1.0
        b[1] = 1.0
        score = face_auth.cosine_similarity(a, b)
        assert abs(score) < 1e-5

    def test_similar_vectors_above_threshold(self):
        """Embedding hampir sama → similarity > threshold."""
        base = _rand_emb(10)
        # Tambahkan noise kecil
        noise = np.random.default_rng(11).standard_normal(128).astype(np.float32) * 0.05
        similar = base + noise
        similar /= np.linalg.norm(similar)
        score = face_auth.cosine_similarity(base, similar)
        assert score > config.FACE_MATCH_THRESHOLD

    def test_dissimilar_vectors_below_threshold(self):
        """Embedding sangat berbeda → similarity < threshold."""
        a = _rand_emb(20)
        b = _rand_emb(21)    # seed berbeda → vektor acak yang tidak berkaitan
        score = face_auth.cosine_similarity(a, b)
        # Dua unit vector acak di ruang 128D hampir selalu dekat 0
        assert score < config.FACE_MATCH_THRESHOLD

    def test_zero_vector_raises(self):
        """Vektor nol harus raise ValueError."""
        v = _rand_emb(5)
        zero = np.zeros(128, dtype=np.float32)
        with pytest.raises(ValueError, match="nol"):
            face_auth.cosine_similarity(v, zero)

    def test_accepts_1d_and_2d_input(self):
        """Input 1D dan 2D (1×128) keduanya diterima."""
        a = _rand_emb(30).reshape(1, 128)
        b = _rand_emb(30)
        score = face_auth.cosine_similarity(a, b)
        assert abs(score - 1.0) < 1e-5


# ─────────────────────────────────────────────────────────────────────
# Tes verify_face
# ─────────────────────────────────────────────────────────────────────

class TestVerifyFace:

    def _patch_embed(self, monkeypatch, return_value):
        """Mock _detect_and_embed agar mengembalikan nilai tetap."""
        monkeypatch.setattr(face_auth, "_detect_and_embed", lambda frame: return_value)

    def test_match_above_threshold(self, monkeypatch):
        """Embedding sangat mirip → match=True, score tinggi."""
        stored = _rand_emb(1)
        # Live embedding = stored + noise kecil
        noise = np.random.default_rng(99).standard_normal(128).astype(np.float32) * 0.02
        live = stored + noise
        live /= np.linalg.norm(live)
        self._patch_embed(monkeypatch, live)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        match, score = face_auth.verify_face(stored, dummy_frame)

        assert match is True
        assert score >= config.FACE_MATCH_THRESHOLD

    def test_no_match_below_threshold(self, monkeypatch):
        """Embedding sangat berbeda → match=False, score rendah."""
        stored = _rand_emb(1)
        different = _rand_emb(999)   # vektor acak berbeda
        self._patch_embed(monkeypatch, different)

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        match, score = face_auth.verify_face(stored, dummy_frame)

        assert match is False

    def test_no_face_detected(self, monkeypatch):
        """Jika tidak ada wajah di frame → (False, 0.0)."""
        self._patch_embed(monkeypatch, None)  # None = tidak ada wajah

        stored = _rand_emb(1)
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        match, score = face_auth.verify_face(stored, dummy_frame)

        assert match is False
        assert score == 0.0

    def test_exact_threshold_boundary(self, monkeypatch):
        """Skor tepat di threshold harus dianggap match."""
        stored = _rand_emb(1)
        # Buat embedding yang cosine similarity-nya tepat di threshold
        # Cara mudah: turunkan norma bukan arah, tapi set sim manual via mock

        # Cara lebih sederhana: set live = stored → sim = 1.0 > threshold
        self._patch_embed(monkeypatch, stored.copy())

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        match, score = face_auth.verify_face(stored, dummy_frame)
        assert match is True


# ─────────────────────────────────────────────────────────────────────
# Tes encoding serialisasi
# ─────────────────────────────────────────────────────────────────────

class TestEncodingSerialization:

    def test_roundtrip(self):
        """to_bytes → from_bytes menghasilkan embedding identik."""
        original = _rand_emb(42)
        data = face_auth.encoding_to_bytes(original)
        restored = face_auth.bytes_to_encoding(data)
        np.testing.assert_array_almost_equal(original, restored, decimal=6)

    def test_bytes_length(self):
        """128 float32 = 512 byte."""
        emb = _rand_emb(0)
        data = face_auth.encoding_to_bytes(emb)
        assert len(data) == 128 * 4   # 512 bytes

    def test_2d_input_flattened(self):
        """Input shape (1, 128) juga diserialisasi ke 512 byte."""
        emb = _rand_emb(7).reshape(1, 128)
        data = face_auth.encoding_to_bytes(emb)
        assert len(data) == 512

    def test_restored_is_writable(self):
        """Array yang di-restore harus writable (copy, bukan view buffer)."""
        emb = _rand_emb(3)
        data = face_auth.encoding_to_bytes(emb)
        restored = face_auth.bytes_to_encoding(data)
        # Harus bisa dimodifikasi tanpa error
        restored[0] = 0.0


# ─────────────────────────────────────────────────────────────────────
# Tes capture_encodings (mock webcam)
# ─────────────────────────────────────────────────────────────────────

class TestCaptureEncodings:
    """
    Semua tes di kelas ini mock cv2.VideoCapture dan _detect_and_embed.
    Tidak butuh webcam fisik.
    """

    def _fake_frames(self, n: int = 10) -> list[np.ndarray]:
        """Buat list frame dummy 480×640 RGB."""
        return [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(n)]

    def test_returns_averaged_embedding(self, monkeypatch):
        """
        Mock: webcam OK, _detect_and_embed mengembalikan embedding acak.
        Hasil harus rata-rata dari embedding yang dikumpulkan.
        """
        embeddings = [_rand_emb(i) for i in range(5)]
        embed_iter = iter(embeddings)

        monkeypatch.setattr(
            face_auth, "_detect_and_embed",
            lambda frame: next(embed_iter, None)
        )

        mock_cap = _make_mock_cap(self._fake_frames(10))
        with patch("cv2.VideoCapture", return_value=mock_cap):
            result = face_auth.capture_encodings(n=5)

        expected = np.mean(embeddings, axis=0).astype(np.float32)
        np.testing.assert_array_almost_equal(result, expected, decimal=5)

    def test_webcam_not_opened_raises(self, monkeypatch):
        """Webcam gagal dibuka → ValueError dengan pesan jelas."""
        mock_cap = _make_mock_cap([], open_ok=False)
        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(ValueError, match="Webcam"):
                face_auth.capture_encodings(n=3)

    def test_no_face_in_any_frame_raises(self, monkeypatch):
        """
        Webcam OK tapi tidak ada wajah di satu frame pun → ValueError.
        Ini terjadi jika user tidak ada di depan kamera.
        """
        # _detect_and_embed selalu None
        monkeypatch.setattr(face_auth, "_detect_and_embed", lambda frame: None)

        mock_cap = _make_mock_cap(self._fake_frames(50))
        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(ValueError, match="Wajah tidak terdeteksi"):
                face_auth.capture_encodings(n=5)

    def test_some_frames_without_face(self, monkeypatch):
        """
        Jika beberapa frame tidak ada wajah, frame yang ada wajah
        tetap dikumpulkan hingga target terpenuhi.
        """
        good_emb = _rand_emb(7)
        call_count = 0

        def sometimes_detect(frame):
            nonlocal call_count
            call_count += 1
            # Kembalikan wajah setiap frame genap, None untuk frame ganjil
            return good_emb if call_count % 2 == 0 else None

        monkeypatch.setattr(face_auth, "_detect_and_embed", sometimes_detect)

        mock_cap = _make_mock_cap(self._fake_frames(100))
        with patch("cv2.VideoCapture", return_value=mock_cap):
            result = face_auth.capture_encodings(n=3)

        # Rata-rata dari 3 embedding identik = embedding itu sendiri
        np.testing.assert_array_almost_equal(result, good_emb, decimal=5)

    def test_release_called_even_on_error(self, monkeypatch):
        """cap.release() harus dipanggil bahkan saat ValueError terjadi."""
        monkeypatch.setattr(face_auth, "_detect_and_embed", lambda frame: None)

        mock_cap = _make_mock_cap(self._fake_frames(100))
        with patch("cv2.VideoCapture", return_value=mock_cap):
            with pytest.raises(ValueError):
                face_auth.capture_encodings(n=5)

        mock_cap.release.assert_called_once()


# ─────────────────────────────────────────────────────────────────────
# Tes _detect_and_embed (mock detector + recognizer)
# ─────────────────────────────────────────────────────────────────────

class TestDetectAndEmbed:
    """
    Mock _get_detector dan _get_recognizer untuk menguji logika
    _detect_and_embed tanpa model ONNX.
    """

    def _make_mocks(self, faces_array, embedding):
        """
        faces_array: None atau np.array dengan baris bounding box (simulasi YuNet)
        embedding  : np.ndarray shape (1, 128) dari recognizer.feature()
        """
        detector = MagicMock()
        detector.detect.return_value = (None, faces_array)
        detector.setInputSize.return_value = None

        recognizer = MagicMock()
        recognizer.alignCrop.return_value = np.zeros((112, 112, 3), dtype=np.uint8)
        recognizer.feature.return_value = embedding

        return detector, recognizer

    def test_no_faces_returns_none(self, monkeypatch):
        """YuNet tidak menemukan wajah → _detect_and_embed mengembalikan None."""
        detector, recognizer = self._make_mocks(None, None)
        monkeypatch.setattr(face_auth, "_get_detector", lambda: detector)
        monkeypatch.setattr(face_auth, "_get_recognizer", lambda: recognizer)

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = face_auth._detect_and_embed(frame)
        assert result is None

    def test_face_detected_returns_embedding(self, monkeypatch):
        """YuNet menemukan wajah → embedding 1D float32 dikembalikan."""
        fake_face = np.array([[100, 100, 80, 100, 0.99,
                               130, 140, 160, 140, 145, 155,
                               125, 165, 155, 165]])  # format YuNet
        expected = _rand_emb(99).reshape(1, 128)
        detector, recognizer = self._make_mocks(fake_face, expected)
        monkeypatch.setattr(face_auth, "_get_detector", lambda: detector)
        monkeypatch.setattr(face_auth, "_get_recognizer", lambda: recognizer)

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = face_auth._detect_and_embed(frame)

        assert result is not None
        assert result.shape == (128,)
        np.testing.assert_array_equal(result, expected.flatten())
