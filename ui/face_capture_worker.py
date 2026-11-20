"""Periksa satu wajah dan respons gerakan pada frame baru selama pendaftaran atau login."""

import secrets
from queue import Empty, Full, Queue
from threading import Lock
from time import monotonic

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

import config
from auth import face_auth

# Model OpenCV di-cache dan ukuran input detektornya berubah tiap inferensi.
MODEL_LOCK = Lock()


class FaceCaptureWorker(QThread):
    """Ikuti satu orang dari posisi depan, menoleh, sampai kembali ke depan."""

    instruction = Signal(str)
    completed = Signal(object, str)
    TIMEOUT_SECONDS = 20
    FRAMES_PER_POSE = 3
    # Ambang dalam satuan jarak antarmata agar tidak bergantung pada resolusi.
    CENTER_TOLERANCE = 0.12
    MIN_TURN = 0.25
    MIN_PARALLAX = 0.08

    def __init__(self, stored_encoding: np.ndarray | None = None) -> None:
        app = QApplication.instance()
        super().__init__(app)
        self._reference = stored_encoding
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

    def _next_observation(self, deadline: float) -> tuple[np.ndarray, np.ndarray] | None:
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
            if monotonic() >= deadline:
                break
            if observation is None:
                raise ValueError("Wajah tidak terdeteksi. Hadapkan wajah ke kamera, lalu ulangi.")
            return observation
        if self.isInterruptionRequested():
            return None
        raise ValueError("Waktu pemeriksaan habis. Ulangi dan ikuti arah gerakan di layar.")

    def run(self) -> None:
        deadline = monotonic() + self.TIMEOUT_SECONDS
        direction = secrets.choice((-1, 1))
        side = "kiri" if direction == -1 else "kanan"
        poses = (
            (0, "Hadapkan wajah lurus ke kamera dan tahan sebentar."),
            (direction, f"Menolehlah sampai wajah di gambar mengarah ke sisi {side}, lalu tahan."),
            (0, "Kembali menghadap lurus ke kamera dan tahan sebentar."),
        )
        try:
            reference = self._reference
            frontal_landmarks = None
            frontal_embeddings: list[np.ndarray] = []
            for target, instruction in poses:
                self._prompted_at = float("inf")
                self.instruction.emit(instruction)
                consecutive: list[np.ndarray] = []
                while len(consecutive) < self.FRAMES_PER_POSE:
                    observation = self._next_observation(deadline)
                    if observation is None:
                        return
                    embedding, landmarks = observation
                    if reference is None:
                        reference = embedding
                    similarity = face_auth.cosine_similarity(reference, embedding)
                    if not np.isfinite(similarity) or similarity < config.FACE_MATCH_THRESHOLD:
                        raise ValueError("Wajah tidak cocok. Ulangi dengan orang yang sama.")
                    turn = face_auth.head_turn(landmarks)
                    if target == 0:
                        correct_pose = abs(turn) <= self.CENTER_TOLERANCE
                    else:
                        parallax = face_auth.nose_parallax(frontal_landmarks, landmarks)
                        correct_pose = target * turn >= self.MIN_TURN and target * parallax >= self.MIN_PARALLAX
                    if correct_pose:
                        consecutive.append(embedding)
                    else:
                        consecutive.clear()
                if target == 0:
                    frontal_landmarks = landmarks
                    frontal_embeddings.extend(consecutive)
            if not self.isInterruptionRequested():
                self.completed.emit(np.mean(frontal_embeddings, axis=0).astype(np.float32), "")
        except (OSError, ValueError, cv2.error) as exc:
            if not self.isInterruptionRequested():
                self.completed.emit(None, str(exc))
