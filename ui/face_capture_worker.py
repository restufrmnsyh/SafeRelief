"""Periksa satu wajah dan respons gerakan pada frame baru selama pendaftaran atau login."""

import secrets
from collections import deque
from queue import Empty, Full, Queue
from threading import Lock
from time import monotonic

import cv2
import numpy as np
from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

import config
from auth import face_auth, hand_challenge

# Model OpenCV di-cache dan ukuran input detektornya berubah tiap inferensi.
MODEL_LOCK = Lock()


def camera_preview(image: QImage, size: QSize, worker: "FaceCaptureWorker | None") -> QPixmap:
    """Gambar kotak di preview saja agar garis tidak ikut masuk ke model."""
    pixmap = QPixmap.fromImage(image)
    if worker is not None:
        x, y, side = hand_challenge.hand_box(image.width(), image.height(), worker.box_on_left)
        painter = QPainter(pixmap)
        thickness = max(2, image.height() // 120)
        painter.setPen(QPen(QColor("#182535"), thickness + 2))
        painter.drawRect(x, y, side - 1, side - 1)
        painter.setPen(QPen(QColor("#ffffff"), thickness))
        painter.drawRect(x, y, side - 1, side - 1)
        painter.end()
    return pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


class FaceCaptureWorker(QThread):
    """Periksa satu wajah hidup saat tangan diangkat lalu diturunkan."""

    instruction = Signal(str)
    completed = Signal(object, str)
    TIMEOUT_SECONDS = 20
    FRAMES_PER_POSE = 5
    MIN_LIVE_FRAMES = 4

    def __init__(self, stored_encoding: np.ndarray | None = None) -> None:
        app = QApplication.instance()
        super().__init__(app)
        self._reference = stored_encoding
        self.box_on_left = secrets.choice((True, False))
        self._frames: Queue[tuple[float, np.ndarray]] = Queue(maxsize=1)
        self._prompted_at = float("inf")
        self.finished.connect(self.deleteLater)
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def submit_frame(self, frame: np.ndarray, captured_at: float) -> None:
        """Preview tetap berjalan pada kecepatan kamera saat inferensi sibuk."""
        try:
            self._frames.put_nowait((captured_at, frame))
        except Full:
            pass

    def prompt_shown(self) -> None:
        """Slot UI memanggil ini setelah petunjuk baru dipasang pada label."""
        self._prompted_at = monotonic()

    def shutdown(self) -> None:
        """Tunggu inferensi sebelum QApplication menghancurkan thread saat keluar."""
        self.requestInterruption()
        self.wait()

    def _next_observation(self, deadline: float) -> tuple[np.ndarray, bool, int | None] | None:
        while not self.isInterruptionRequested():
            if monotonic() >= deadline:
                break
            try:
                captured_at, frame = self._frames.get(timeout=0.1)
            except Empty:
                continue
            if captured_at <= self._prompted_at:
                continue
            with MODEL_LOCK:
                observation = face_auth.observe_face(frame)
                if observation is None:
                    raise ValueError("Wajah tidak terdeteksi. Hadapkan wajah ke kamera, lalu ulangi.")
                embedding, face_box = observation
                live = hand_challenge.face_is_live(frame, face_box)
                fingers = hand_challenge.visible_fingers(frame, self.box_on_left)
            if monotonic() >= deadline:
                break
            return embedding, live, fingers
        return None

    def run(self) -> None:
        deadline = monotonic() + self.TIMEOUT_SECONDS
        prompts = [
            (None, "Tatap kamera. Biarkan kotak kosong."),
            (3, "Angkat tiga jari di dalam kotak dan tahan sebentar."),
            (None, "Turunkan tangan sampai kotak kosong."),
        ]
        try:
            reference = self._reference
            embeddings: list[np.ndarray] = []
            for required, instruction in prompts:
                liveness_hint_shown = False
                self._prompted_at = float("inf")
                self.instruction.emit(instruction)
                # Setiap langkah memerlukan bukti baru dari wajah dan pose tangan yang sama.
                samples: deque[tuple[np.ndarray, bool]] = deque(maxlen=self.FRAMES_PER_POSE)
                while True:
                    observation = self._next_observation(deadline)
                    if observation is None:
                        if self.isInterruptionRequested():
                            return
                        if liveness_hint_shown:
                            raise ValueError("Wajah hidup belum terverifikasi. Coba lagi dengan cahaya dari depan.")
                        raise ValueError("Waktu pemeriksaan habis. Ulangi dan ikuti petunjuk di layar.")
                    embedding, live, fingers = observation
                    if reference is None:
                        reference = embedding
                    similarity = face_auth.cosine_similarity(reference, embedding)
                    if not np.isfinite(similarity) or similarity < config.FACE_MATCH_THRESHOLD:
                        raise ValueError("Wajah tidak cocok. Ulangi dengan orang yang sama.")
                    if fingers != required:
                        samples.clear()
                        if live and liveness_hint_shown:
                            self.instruction.emit(instruction)
                            liveness_hint_shown = False
                        continue
                    samples.append((embedding, live))
                    if len(samples) < self.FRAMES_PER_POSE:
                        continue
                    live_samples = [sample for sample, passed in samples if passed]
                    if live and len(live_samples) >= self.MIN_LIVE_FRAMES:
                        if required is None:
                            embeddings.extend(live_samples)
                        break
                    if not liveness_hint_shown:
                        liveness_hint_shown = True
                        self.instruction.emit(instruction + " Dekatkan sedikit wajah dan hadap ke arah cahaya.")
            if not self.isInterruptionRequested():
                self.completed.emit(np.mean(embeddings, axis=0).astype(np.float32), "")
        except (OSError, ValueError, cv2.error) as exc:
            if not self.isInterruptionRequested():
                self.completed.emit(None, str(exc))
