"""Pendaftaran dan verifikasi satu wajah dari pratinjau kamera aktif."""

from queue import Empty, Full, Queue
from threading import Lock
from time import monotonic

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication

import config
from auth import face_auth

# Model OpenCV di-cache dan ukuran input detektornya berubah tiap inferensi.
MODEL_LOCK = Lock()


def camera_preview(image: QImage, size: QSize) -> QPixmap:
    """Tampilkan seluruh frame agar wajah di tepi pratinjau tetap terlihat."""
    return QPixmap.fromImage(image).scaled(
        size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


class FaceCaptureWorker(QThread):
    """Cocokkan satu wajah pada beberapa frame setelah tombol ditekan."""

    completed = Signal(object, str)
    TIMEOUT_SECONDS = 20

    def __init__(self, stored_encoding: np.ndarray | None = None) -> None:
        app = QApplication.instance()
        super().__init__(app)
        self._reference = stored_encoding
        self._started_at = monotonic()
        self._frames: Queue[tuple[float, np.ndarray]] = Queue(maxsize=1)
        self.finished.connect(self.deleteLater)
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def submit_frame(self, frame: np.ndarray, captured_at: float) -> None:
        """Preview tetap berjalan pada kecepatan kamera saat inferensi sibuk."""
        try:
            self._frames.put_nowait((captured_at, frame))
        except Full:
            pass

    def shutdown(self) -> None:
        """Tunggu inferensi sebelum QApplication menghancurkan thread saat keluar."""
        self.requestInterruption()
        self.wait()

    def run(self) -> None:
        last_frame_at = self._started_at
        deadline = self._started_at + self.TIMEOUT_SECONDS
        reference = self._reference
        embeddings: list[np.ndarray] = []
        try:
            while monotonic() < deadline:
                if self.isInterruptionRequested():
                    return
                if len(embeddings) == config.FACE_CAPTURE_FRAMES:
                    self.completed.emit(np.mean(embeddings, axis=0).astype(np.float32), "")
                    return
                try:
                    captured_at, frame = self._frames.get(timeout=0.1)
                except Empty:
                    continue
                if captured_at <= last_frame_at:
                    continue
                last_frame_at = captured_at
                with MODEL_LOCK:
                    embedding = face_auth.observe_face(frame)
                if embedding is None:
                    raise ValueError("Wajah tidak terdeteksi. Hadapkan wajah ke kamera, lalu ulangi.")
                # Saat mendaftar, frame pertama menjadi acuan agar dua orang tidak terekam bergantian.
                if reference is None:
                    reference = embedding
                score = face_auth.cosine_similarity(reference, embedding)
                if not np.isfinite(score) or score < config.FACE_MATCH_THRESHOLD:
                    raise ValueError("Wajah tidak cocok. Ulangi dengan orang yang sama.")
                embeddings.append(embedding)
            raise ValueError("Waktu pemeriksaan habis. Tatap kamera, lalu coba lagi.")
        except (OSError, ValueError, cv2.error) as exc:
            if not self.isInterruptionRequested():
                self.completed.emit(None, str(exc))
