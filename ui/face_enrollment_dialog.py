"""Dialog pendaftaran wajah relawan dengan preview kamera langsung."""

from __future__ import annotations

from collections import deque

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ui.login_page import CameraWorker
from ui.face_capture_worker import FaceCaptureWorker
from ui.workspace import style_dialog


class FaceEnrollmentDialog(QDialog):
    """Minta relawan menghadap kamera lalu capture encoding wajah yang valid.

    Preview kamera menggunakan CameraWorker yang sudah dipakai di LoginPage agar
    tidak membuka kamera baru secara terpisah dan tidak menimbulkan thread ganda.
    """

    def __init__(self, volunteer_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Daftar Wajah Relawan")
        self.setMinimumWidth(420)
        self.resize(500, 420)
        self._volunteer_name = volunteer_name
        self._camera_worker: CameraWorker | None = None
        self._last_frame: np.ndarray | None = None
        self._recent_frames: deque[np.ndarray] = deque(maxlen=6)
        self._capture_result: np.ndarray | None = None
        self._capture_worker: FaceCaptureWorker | None = None
        self._cancelled = False

        self.instruction_label = QLabel(
            f"Posisikan wajah {volunteer_name} di tengah frame, lalu klik Rekam Wajah"
        )
        self.instruction_label.setWordWrap(True)

        self.camera_label = QLabel("Memuat kamera...")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumSize(320, 240)
        self.camera_label.setStyleSheet(
            "border: 2px solid #CBD5E1; border-radius: 12px; "
            "background: #F8FAFC; color: #475569;"
        )

        self.status_label = QLabel("Siap untuk merekam wajah.")
        self.status_label.setWordWrap(True)

        self.capture_button = QPushButton("Rekam Wajah")
        self.capture_button.clicked.connect(self._handle_capture_click)
        self.cancel_button = QPushButton("Batal")
        self.cancel_button.clicked.connect(self.reject)

        action_row = QHBoxLayout()
        action_row.addWidget(self.capture_button)
        action_row.addStretch()
        action_row.addWidget(self.cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.instruction_label)
        layout.addWidget(self.camera_label)
        layout.addWidget(self.status_label)
        layout.addLayout(action_row)

        self._start_camera()
        style_dialog(self)

    @property
    def capture_result(self) -> np.ndarray | None:
        return self._capture_result

    def _start_camera(self) -> None:
        if self._camera_worker is not None:
            return
        worker = CameraWorker(self)
        worker.frame_ready.connect(self._display_frame)
        worker.camera_error.connect(self._camera_failed)
        self._camera_worker = worker
        worker.start()

    def stop_camera(self) -> None:
        worker = self._camera_worker
        if worker is None:
            return
        worker.requestInterruption()
        worker.wait(2000)
        self._camera_worker = None

    def _display_frame(self, image: QImage) -> None:
        frame = self._qimage_to_bgr(image)
        self._last_frame = frame
        self._recent_frames.append(frame.copy())
        pixmap = QPixmap.fromImage(image).scaled(
            self.camera_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_label.setPixmap(pixmap)

    @staticmethod
    def _qimage_to_bgr(image: QImage) -> np.ndarray:
        converted = image.convertToFormat(QImage.Format.Format_RGB888)
        width = converted.width()
        height = converted.height()
        bytes_per_line = converted.bytesPerLine()
        buffer = converted.bits().tobytes()
        rows = np.frombuffer(buffer, dtype=np.uint8).reshape(height, bytes_per_line)
        rgb = rows[:, : width * 3].reshape(height, width, 3)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _camera_failed(self, message: str) -> None:
        self.camera_label.setText(message)
        self.status_label.setText(message)
        self.capture_button.setEnabled(False)

    def capture_face(self) -> None:
        """Ambil embedding dari feed kamera aktif dan simpan sebagai kandidat wajah."""
        if self._camera_worker is None or not self._camera_worker.isRunning():
            self.status_label.setText("Kamera belum siap. Coba lagi beberapa saat.")
            return

        if self._cancelled or self._capture_worker is not None:
            return
        frames = list(self._recent_frames)
        if not frames and self._last_frame is not None:
            frames = [self._last_frame]
        self.capture_button.setEnabled(False)
        self.status_label.setText("Merekam... jangan bergerak")

        worker = FaceCaptureWorker(frames)
        self._capture_worker = worker
        worker.completed.connect(self._capture_completed)
        worker.finished.connect(self._capture_finished)
        worker.start()

    def _capture_finished(self) -> None:
        """Aktifkan tombol coba lagi setelah worker selesai."""
        if self.sender() is self._capture_worker:
            self._capture_worker = None
            if not self._cancelled:
                self.capture_button.setEnabled(True)

    def _capture_completed(self, encoding: object, error: str) -> None:
        """Abaikan hasil yang tiba setelah dialog dibatalkan."""
        if self._cancelled or self.sender() is not self._capture_worker:
            return
        if error:
            self.status_label.setText(error)
            return
        self._capture_result = encoding
        self.status_label.setText("Wajah berhasil direkam!")
        self.capture_button.setText("Simpan Wajah")
        self.capture_button.setEnabled(True)

    def _handle_capture_click(self) -> None:
        if self._capture_result is not None:
            self.accept()
            return
        self.capture_face()

    def accept(self) -> None:
        if self._capture_result is None:
            self.status_label.setText("Rekam wajah terlebih dahulu sebelum menyimpan.")
            return
        self.stop_camera()
        super().accept()

    def reject(self) -> None:
        self._cancelled = True
        if self._capture_worker is not None:
            self._capture_worker.requestInterruption()
            self._capture_worker = None
        self._capture_result = None
        self._recent_frames.clear()
        self._last_frame = None
        self.stop_camera()
        super().reject()

    def closeEvent(self, event) -> None:
        self.reject()
        super().closeEvent(event)
