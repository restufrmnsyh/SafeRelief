"""Worker embedding bersama untuk login pertama dan pendaftaran relawan."""

from threading import Lock

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from auth import face_auth

# Model OpenCV di-cache dan ukuran input detektornya berubah tiap inferensi.
MODEL_LOCK = Lock()


class FaceCaptureWorker(QThread):
    """Proses salinan frame tanpa menyentuh widget atau koneksi SQLite."""

    completed = Signal(object, str)

    def __init__(self, frames: list[np.ndarray]) -> None:
        app = QApplication.instance()
        super().__init__(app)
        self._frames = [frame.copy() for frame in frames]
        self.finished.connect(self.deleteLater)
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Tunggu inferensi sebelum QApplication menghancurkan thread saat keluar."""
        self.requestInterruption()
        self.wait()

    def run(self) -> None:
        try:
            embeddings: list[np.ndarray] = []
            with MODEL_LOCK:
                for frame in self._frames:
                    if self.isInterruptionRequested():
                        return
                    embedding = face_auth._detect_and_embed(frame)
                    if embedding is not None:
                        embeddings.append(embedding)
            if self.isInterruptionRequested():
                return
            if not embeddings:
                raise ValueError("Wajah tidak terdeteksi. Posisikan wajah dengan jelas.")
            self.completed.emit(np.mean(embeddings, axis=0).astype(np.float32), "")
        except (OSError, ValueError, cv2.error) as exc:
            if not self.isInterruptionRequested():
                self.completed.emit(None, str(exc))
        finally:
            self._frames.clear()
