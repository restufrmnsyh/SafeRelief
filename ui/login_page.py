"""Halaman login tiga faktor dengan pengambilan kamera di thread terpisah."""

import sqlite3

import cv2
import numpy as np
from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from auth import dongle, face_auth, login, session
from crypto import keys
from database import db, secure_store


class CameraWorker(QThread):
    """Baca frame webcam di worker agar event loop UI tetap responsif."""

    frame_ready = Signal(QImage)
    camera_error = Signal(str)

    def run(self) -> None:
        camera = cv2.VideoCapture(0)
        try:
            if not camera.isOpened():
                self.camera_error.emit("Webcam tidak dapat dibuka.")
                return

            while not self.isInterruptionRequested():
                success, frame = camera.read()
                if not success or frame is None:
                    self.msleep(30)
                    continue
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width, channels = rgb_frame.shape
                image = QImage(
                    rgb_frame.data,
                    width,
                    height,
                    channels * width,
                    QImage.Format.Format_RGB888,
                ).copy()
                self.frame_ready.emit(image)
                self.msleep(30)
        except cv2.error as exc:
            self.camera_error.emit(f"Kamera gagal: {exc}")
        finally:
            camera.release()


class FaceVerificationWorker(QThread):
    """Jalankan pencocokan wajah di luar thread UI."""

    completed = Signal(bool, float, str)

    def __init__(
        self, stored_encoding: np.ndarray, frame: np.ndarray
    ) -> None:
        super().__init__()
        self._stored_encoding = stored_encoding.copy()
        self._frame = frame.copy()

    def run(self) -> None:
        try:
            matched, score = face_auth.verify_face(
                self._stored_encoding, self._frame
            )
            self.completed.emit(matched, score, "")
        except (FileNotFoundError, ValueError, cv2.error) as exc:
            self.completed.emit(False, 0.0, str(exc))


class LoginPage(QWidget):
    """Mengautentikasi password, dongle milik akun, lalu wajah."""

    authenticated = Signal(dict)

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("loginPage")
        self._conn = conn
        self._gate_open = False
        self._preauth_user: dict[str, object] | None = None
        self._transient_master_key: bytearray | None = None
        self._stored_encoding: np.ndarray | None = None
        self._last_frame: np.ndarray | None = None
        self._camera_worker: CameraWorker | None = None
        self._face_worker: FaceVerificationWorker | None = None

        self.gate_label = QLabel("Mencari dongle...")
        self.gate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        credentials_form = QFormLayout()
        credentials_form.addRow("Username", self.username_input)
        credentials_form.addRow("Password", self.password_input)

        self.submit_button = QPushButton("Lanjutkan")
        self.submit_button.clicked.connect(self.submit_credentials)

        self.camera_label = QLabel("Kamera belum diaktifkan.")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumSize(480, 320)
        self.camera_label.setStyleSheet("background-color: #202020; color: white;")
        self.verify_face_button = QPushButton("Verifikasi Wajah")
        self.verify_face_button.setEnabled(False)
        self.verify_face_button.clicked.connect(self.verify_current_face)

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.gate_label)
        layout.addLayout(credentials_form)
        layout.addWidget(self.submit_button)
        layout.addWidget(self.camera_label, stretch=1)
        layout.addWidget(self.verify_face_button)
        layout.addWidget(self.message_label)

        self._set_face_controls_visible(False)

    def set_gate_status(self, message: str) -> None:
        """Tampilkan status gerbang tanpa menyebut pemilik dongle."""
        self.gate_label.setText(message)
        was_open = self._gate_open
        self._gate_open = message == "Dongle valid terdeteksi"
        if was_open and not self._gate_open:
            self._clear_pre_auth()

    def show_session_ended(self, message: str) -> None:
        """Tampilkan alasan sesi dihentikan setelah gerbang dongle terbuka."""
        self._clear_pre_auth()
        self.username_input.clear()
        self.password_input.clear()
        self.set_gate_status("Dongle valid terdeteksi")
        self.message_label.setText(message)

    def submit_credentials(self) -> None:
        """Periksa password dan dongle akun sebelum membuka langkah wajah."""
        self._clear_pre_auth()
        self.message_label.clear()
        if not self._gate_open:
            self.message_label.setText("Dongle valid belum terdeteksi.")
            return

        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            self.message_label.setText("Username dan password wajib diisi.")
            return

        self.submit_button.setEnabled(False)
        master_key: bytearray | None = None
        try:
            user = login.authenticate(self._conn, username, password)
            token = dongle.verify_dongle(user)
            wrapped = user.get("wrapped_master_key")
            salt = user.get("kdf_salt")
            if wrapped is None or salt is None:
                raise ValueError("Akun belum memiliki master key terdaftar.")

            # Embedding wajah dienkripsi dengan kunci turunan master key,
            # sehingga kunci dibuka sementara dan hanya masuk sesi setelah wajah cocok.
            master_key = bytearray(
                keys.unwrap_master_key(
                    bytes(wrapped), password, token, bytes(salt)
                )
            )
            db_key = keys.derive_key(
                bytes(master_key), config.HKDF_LABEL_DB
            )
            encoding_bytes = secure_store.load_face_encoding(
                self._conn, db_key, int(user["id"])
            )
            if encoding_bytes is None:
                raise ValueError("Wajah belum terdaftar untuk akun ini.")

            self._preauth_user = user
            self._transient_master_key = master_key
            master_key = None
            self._stored_encoding = face_auth.bytes_to_encoding(encoding_bytes)
            self._set_face_controls_visible(True)
            self.camera_label.setText("Menghubungkan ke webcam...")
            self.message_label.setText(
                "Password dan dongle cocok. Silakan verifikasi wajah."
            )
            self._start_camera()
        except (ValueError, OSError, sqlite3.Error, InvalidTag) as exc:
            self._clear_pre_auth()
            self.message_label.setText(str(exc))
        finally:
            if master_key is not None:
                master_key[:] = b"\x00" * len(master_key)
            self.password_input.clear()
            self.submit_button.setEnabled(True)

    def _start_camera(self) -> None:
        """Mulai feed webcam pada QThread."""
        if self._camera_worker is not None:
            return
        worker = CameraWorker(self)
        worker.frame_ready.connect(self._display_frame)
        worker.camera_error.connect(self._camera_failed)
        self._camera_worker = worker
        worker.start()

    def stop_camera(self) -> None:
        """Hentikan webcam saat halaman login disembunyikan atau aplikasi tutup."""
        worker = self._camera_worker
        if worker is None:
            return
        worker.requestInterruption()
        worker.wait(3000)
        if worker.isFinished():
            self._camera_worker = None

    def _display_frame(self, image: QImage) -> None:
        self._last_frame = self._qimage_to_bgr(image)
        pixmap = QPixmap.fromImage(image).scaled(
            self.camera_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_label.setPixmap(pixmap)

    @staticmethod
    def _qimage_to_bgr(image: QImage) -> np.ndarray:
        """Konversi salinan frame Qt ke format BGR yang dipakai OpenCV."""
        converted = image.convertToFormat(QImage.Format.Format_RGB888)
        width = converted.width()
        height = converted.height()
        bytes_per_line = converted.bytesPerLine()
        buffer = converted.bits().tobytes()
        rows = np.frombuffer(buffer, dtype=np.uint8).reshape(
            height, bytes_per_line
        )
        rgb = rows[:, : width * 3].reshape(height, width, 3)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _camera_failed(self, message: str) -> None:
        self.camera_label.setText(message)
        self.message_label.setText(message)
        self.verify_face_button.setEnabled(False)

    def resizeEvent(self, event) -> None:
        """Pertahankan skala feed ketika ukuran jendela berubah."""
        pixmap = self.camera_label.pixmap()
        if pixmap is not None:
            self.camera_label.setPixmap(
                pixmap.scaled(
                    self.camera_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        super().resizeEvent(event)

    def verify_current_face(self) -> None:
        """Bandingkan frame terbaru dengan embedding tersimpan di worker."""
        if (
            not self._gate_open
            or self._stored_encoding is None
            or self._last_frame is None
        ):
            self.message_label.setText(
                "Tunggu sampai frame webcam tersedia untuk verifikasi."
            )
            return
        if self._face_worker is not None and self._face_worker.isRunning():
            return

        worker = FaceVerificationWorker(
            self._stored_encoding, self._last_frame
        )
        worker.completed.connect(self._face_verification_finished)
        worker.finished.connect(self._face_worker_finished)
        self._face_worker = worker
        self.verify_face_button.setEnabled(False)
        self.message_label.setText("Memverifikasi wajah...")
        worker.start()

    def _face_verification_finished(
        self, matched: bool, score: float, error: str
    ) -> None:
        if not self._gate_open:
            return
        if error:
            self.message_label.setText(error)
            self.verify_face_button.setEnabled(True)
            return
        if not matched:
            if score == 0.0:
                self.message_label.setText("Wajah tidak terdeteksi. Coba lagi.")
            else:
                self.message_label.setText(
                    f"Wajah tidak cocok (skor {score:.3f}). Coba lagi."
                )
            self.verify_face_button.setEnabled(True)
            return

        user = self._preauth_user
        master_key = self._transient_master_key
        if user is None or master_key is None:
            self.message_label.setText("Sesi autentikasi sudah kedaluwarsa.")
            self._clear_pre_auth()
            return

        try:
            current_user = db.get_user_by_id(self._conn, int(user["id"]))
            if current_user is None or not current_user["is_active"]:
                raise PermissionError("Akun dinonaktifkan saat proses login.")
            dongle.verify_dongle(current_user)
        except (OSError, ValueError, sqlite3.Error, PermissionError) as exc:
            self.message_label.setText(str(exc))
            self._clear_pre_auth()
            return

        session.login(user, bytes(master_key))
        self._clear_pre_auth()
        self.authenticated.emit(user)

    def _face_worker_finished(self) -> None:
        self._face_worker = None
        if self._gate_open:
            self.verify_face_button.setEnabled(True)

    def _set_face_controls_visible(self, visible: bool) -> None:
        self.camera_label.setVisible(visible)
        self.verify_face_button.setVisible(visible)
        self.verify_face_button.setEnabled(visible)

    def _clear_pre_auth(self) -> None:
        self.stop_camera()
        if self._transient_master_key is not None:
            self._transient_master_key[:] = b"\x00" * len(
                self._transient_master_key
            )
        self._transient_master_key = None
        self._preauth_user = None
        self._stored_encoding = None
        self._last_frame = None
        self._set_face_controls_visible(False)

    def hideEvent(self, event) -> None:
        """Hapus data pralogin saat user meninggalkan halaman."""
        self._clear_pre_auth()
        super().hideEvent(event)
