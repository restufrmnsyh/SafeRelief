"""Halaman login tiga faktor dengan tampilan Web App Full White Screen terpusat."""

import sqlite3
from collections import deque

import cv2
import numpy as np
from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
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
        camera = face_auth._open_camera(0)
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
        self._preauth_db_key: bytes | None = None
        self._stored_encoding: np.ndarray | None = None
        self._last_frame: np.ndarray | None = None
        self._recent_frames: deque[np.ndarray] = deque(maxlen=6)
        self._camera_worker: CameraWorker | None = None
        self._face_worker: FaceVerificationWorker | None = None
        self._registration_mode = False

        # Full White Screen Background
        self.setStyleSheet("background-color: #FFFFFF; color: #0F172A;")

        # Layout Utama: Seluruh Layar Putih Terpusat
        root_layout = QVBoxLayout(self)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root_layout.setContentsMargins(40, 40, 40, 40)
        root_layout.setSpacing(16)

        # Container Card Putih Bersih
        self.card_frame = QFrame()
        self.card_frame.setStyleSheet(
            "QFrame#mainLoginCard {"
            "   background-color: #FFFFFF;"
            "   border: 1px solid #E2E8F0;"
            "   border-radius: 20px;"
            "}"
        )
        self.card_frame.setObjectName("mainLoginCard")

        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(36, 32, 36, 32)
        card_layout.setSpacing(20)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Header Title (Tepat di Tengah Atas)
        title_label = QLabel("SafeRelief")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 28px; font-weight: 800; color: #0F172A; border: none;"
        )

        # Status Dongle (Di Tengah Atas Form)
        self.gate_label = QLabel("✖ Mencari dongle...")
        self.gate_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_gate_status("Mencari dongle...")

        card_layout.addWidget(title_label, alignment=Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.gate_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Grid Content Horizontal (Kiri: Form, Kanan: Kamera)
        content_layout = QHBoxLayout()
        content_layout.setSpacing(40)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ==========================================
        # BAGIAN KIRI: FORM USERNAME & PASSWORD
        # ==========================================
        left_box = QVBoxLayout()
        left_box.setSpacing(10)
        left_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        input_qss = (
            "QLineEdit {"
            "   background-color: #F8FAFC;"
            "   border: 1px solid #CBD5E1;"
            "   border-radius: 8px;"
            "   padding: 10px 14px;"
            "   font-size: 13px;"
            "   color: #0F172A;"
            "}"
            "QLineEdit:focus {"
            "   background-color: #EFF6FF;"
            "   border: 2px solid #3B82F6;"
            "}"
        )

        lbl_user = QLabel("Username")
        lbl_user.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_user.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569; border: none;")
        self.username_input = QLineEdit()
        self.username_input.setFixedWidth(270)
        self.username_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.username_input.setPlaceholderText("Masukkan username")
        self.username_input.setStyleSheet(input_qss)

        lbl_pass = QLabel("Password")
        lbl_pass.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_pass.setStyleSheet("font-size: 12px; font-weight: 600; color: #475569; border: none;")
        self.password_input = QLineEdit()
        self.password_input.setFixedWidth(270)
        self.password_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.password_input.setPlaceholderText("Masukkan password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet(input_qss)

        self.submit_button = QPushButton("Cek Kredensial & Aktifkan Kamera")
        self.submit_button.setFixedWidth(270)
        self.submit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_button.setStyleSheet(
            "QPushButton {"
            "   background-color: #DBEAFE;"
            "   color: #1E40AF;"
            "   border: 1px solid #BFDBFE;"
            "   border-radius: 8px;"
            "   padding: 10px;"
            "   font-weight: 700;"
            "   font-size: 12px;"
            "   margin-top: 6px;"
            "}"
            "QPushButton:hover {"
            "   background-color: #BFDBFE;"
            "   color: #1E3A8A;"
            "}"
            "QPushButton:disabled {"
            "   background-color: #F1F5F9;"
            "   color: #94A3B8;"
            "   border-color: #E2E8F0;"
            "}"
        )
        self.submit_button.clicked.connect(self.submit_credentials)

        left_box.addWidget(lbl_user, alignment=Qt.AlignmentFlag.AlignCenter)
        left_box.addWidget(self.username_input, alignment=Qt.AlignmentFlag.AlignCenter)
        left_box.addWidget(lbl_pass, alignment=Qt.AlignmentFlag.AlignCenter)
        left_box.addWidget(self.password_input, alignment=Qt.AlignmentFlag.AlignCenter)
        left_box.addWidget(self.submit_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # ==========================================
        # BAGIAN KANAN: KAMERA & VERIFIKASI WAJAH
        # ==========================================
        right_box = QVBoxLayout()
        right_box.setSpacing(10)
        right_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.camera_label = QLabel("Isi form & klik 'Lanjutkan'")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setFixedSize(280, 190)
        self.camera_label.setStyleSheet(
            "border: 2px dashed #CBD5E1; border-radius: 12px; background-color: #F8FAFC; color: #64748B; font-size: 12px;"
        )

        self.verify_face_button = QPushButton("Verifikasi Wajah")
        self.verify_face_button.setFixedWidth(240)
        self.verify_face_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.verify_face_button.setStyleSheet(
            "QPushButton {"
            "   background-color: #DBEAFE;"
            "   color: #1E40AF;"
            "   border: 1px solid #BFDBFE;"
            "   border-radius: 8px;"
            "   padding: 9px;"
            "   font-weight: 700;"
            "   font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "   background-color: #BFDBFE;"
            "}"
            "QPushButton:disabled {"
            "   background-color: #F1F5F9;"
            "   color: #94A3B8;"
            "   border-color: #E2E8F0;"
            "}"
        )
        self.verify_face_button.setEnabled(False)
        self.verify_face_button.clicked.connect(self.verify_current_face)

        self.message_label = QLabel("")
        self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
        self.message_label.setWordWrap(True)
        self.message_label.setFixedWidth(270)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        right_box.addWidget(self.camera_label, alignment=Qt.AlignmentFlag.AlignCenter)
        right_box.addWidget(self.verify_face_button, alignment=Qt.AlignmentFlag.AlignCenter)
        right_box.addWidget(self.message_label, alignment=Qt.AlignmentFlag.AlignCenter)

        content_layout.addLayout(left_box)
        content_layout.addLayout(right_box)

        card_layout.addLayout(content_layout)
        root_layout.addWidget(self.card_frame)

    def set_gate_status(self, message: str) -> None:
        was_open = self._gate_open
        self._gate_open = message == "Dongle valid terdeteksi"

        if self._gate_open:
            self.gate_label.setText("✔ Dongle Valid Terdeteksi")
            self.gate_label.setStyleSheet(
                "color: #16A34A; "
                "background-color: transparent; "
                "border: 1.5px solid #22C55E; "
                "border-radius: 8px; "
                "padding: 5px 14px; "
                "font-weight: 700; font-size: 11px;"
            )
        else:
            self.gate_label.setText("✖ Mencari dongle...")
            self.gate_label.setStyleSheet(
                "color: #DC2626; "
                "background-color: transparent; "
                "border: 1.5px solid #EF4444; "
                "border-radius: 8px; "
                "padding: 5px 14px; "
                "font-weight: 700; font-size: 11px;"
            )

        if was_open and not self._gate_open:
            self._clear_pre_auth()

    def show_session_ended(self, message: str) -> None:
        self._clear_pre_auth()
        self.username_input.clear()
        self.password_input.clear()
        self.set_gate_status("Dongle valid terdeteksi")
        self.message_label.setText(message)

    def submit_credentials(self) -> None:
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
        db_key: bytes | None = None
        try:
            user = login.authenticate(self._conn, username, password)
            token = dongle.verify_dongle(user)
            wrapped = user.get("wrapped_master_key")
            salt = user.get("kdf_salt")
            if wrapped is None or salt is None:
                raise ValueError("Akun belum memiliki master key terdaftar.")

            master_key = bytearray(
                keys.unwrap_master_key(
                    bytes(wrapped), password, token, bytes(salt)
                )
            )
            db_key = keys.derive_key(bytes(master_key), config.HKDF_LABEL_DB)
            encoding_bytes = secure_store.load_face_encoding(
                self._conn, db_key, int(user["id"])
            )

            self._preauth_user = user
            self._transient_master_key = master_key
            self._preauth_db_key = db_key
            master_key = None
            db_key = None

            self._start_camera()
            if encoding_bytes is None:
                self._registration_mode = True
                self._set_face_controls_visible(True)
                self.message_label.setStyleSheet(
                    "color: #0F766E; font-size: 11px; font-weight: 600; border: none;"
                )
                self.message_label.setText(
                    "Wajah belum terdaftar. Posisikan wajah di kamera lalu klik 'Daftarkan Wajah'."
                )
                return

            self._registration_mode = False
            self._stored_encoding = face_auth.bytes_to_encoding(encoding_bytes)
            self._set_face_controls_visible(True)
            self.message_label.setStyleSheet(
                "color: #059669; font-size: 11px; font-weight: 600; border: none;"
            )
            self.message_label.setText(
                "Kredensial valid. Tatap kamera & verifikasi."
            )
        except (ValueError, OSError, sqlite3.Error, InvalidTag) as exc:
            self._clear_pre_auth()
            self.message_label.setStyleSheet(
                "color: #DC2626; font-size: 11px; font-weight: 600; border: none;"
            )
            self.message_label.setText(str(exc))
        finally:
            if master_key is not None:
                master_key[:] = b"\x00" * len(master_key)
            if db_key is not None:
                db_key = b"\x00" * len(db_key)
            self.password_input.clear()
            self.submit_button.setEnabled(True)

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
        worker.wait(3000)
        if worker.isFinished():
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
        rows = np.frombuffer(buffer, dtype=np.uint8).reshape(
            height, bytes_per_line
        )
        rgb = rows[:, : width * 3].reshape(height, width, 3)
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

    def _camera_failed(self, message: str) -> None:
        self.camera_label.setText(message)
        self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
        self.message_label.setText(message)
        self.verify_face_button.setEnabled(False)

    def resizeEvent(self, event) -> None:
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

    def register_current_face(self) -> None:
        """Daftarkan wajah pengguna dari feed kamera aktif tanpa membuka webcam baru."""
        if not self._gate_open or self._preauth_user is None:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Sesi pendaftaran wajah belum siap.")
            return

        embeddings: list[np.ndarray] = []
        for frame in self._recent_frames:
            emb = face_auth._detect_and_embed(frame)
            if emb is not None:
                embeddings.append(emb)

        if not embeddings and self._last_frame is not None:
            emb = face_auth._detect_and_embed(self._last_frame)
            if emb is not None:
                embeddings.append(emb)

        if not embeddings:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Wajah tidak terdeteksi di feed kamera. Posisikan wajah dengan jelas.")
            return

        user = self._preauth_user
        master_key = self._transient_master_key
        db_key = self._preauth_db_key
        if user is None or master_key is None or db_key is None:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Sesi pendaftaran wajah sudah kedaluwarsa.")
            self._clear_pre_auth()
            return

        try:
            average_encoding = np.mean(embeddings, axis=0).astype(np.float32)
            secure_store.save_face_encoding(
                self._conn,
                db_key,
                int(user["id"]),
                face_auth.encoding_to_bytes(average_encoding),
            )
            self._stored_encoding = average_encoding
            self._registration_mode = False
            self._set_face_controls_visible(True)
            self.message_label.setStyleSheet("color: #059669; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Wajah berhasil didaftarkan. Lanjutkan verifikasi wajah.")
            session.login(user, bytes(master_key))
            self._clear_pre_auth()
            self.authenticated.emit(user)
        except (ValueError, OSError, sqlite3.Error, cv2.error) as exc:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText(str(exc))

    def verify_current_face(self) -> None:
        if not self._gate_open:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Tunggu sampai frame webcam tersedia.")
            return

        if self._registration_mode:
            self.register_current_face()
            return

        if self._stored_encoding is None or self._last_frame is None:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Tunggu sampai frame webcam tersedia.")
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
        self.message_label.setStyleSheet("color: #2563EB; font-size: 11px; font-weight: 600; border: none;")
        self.message_label.setText("Memverifikasi wajah...")
        worker.start()

    def _face_verification_finished(
        self, matched: bool, score: float, error: str
    ) -> None:
        if not self._gate_open:
            return
        if error:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText(error)
            self.verify_face_button.setEnabled(True)
            return
        if not matched:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            if score == 0.0:
                self.message_label.setText("Wajah tidak terdeteksi. Coba lagi.")
            else:
                self.message_label.setText(
                    f"Wajah tidak cocok (skor {score:.3f})."
                )
            self.verify_face_button.setEnabled(True)
            return

        user = self._preauth_user
        master_key = self._transient_master_key
        if user is None or master_key is None:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
            self.message_label.setText("Sesi autentikasi sudah kedaluwarsa.")
            self._clear_pre_auth()
            return

        try:
            current_user = db.get_user_by_id(self._conn, int(user["id"]))
            if current_user is None or not current_user["is_active"]:
                raise PermissionError("Akun dinonaktifkan saat proses login.")
            dongle.verify_dongle(current_user)
        except (OSError, ValueError, sqlite3.Error, PermissionError) as exc:
            self.message_label.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600; border: none;")
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
        # Kamera tetap terlihat di UI agar tata letak tidak bergeser/kosong sebelah
        if not visible:
            self.camera_label.setText("Isi form & klik 'Lanjutkan'")
            self.verify_face_button.setText("Verifikasi Wajah")
            self.verify_face_button.setEnabled(False)
            return

        if self._registration_mode:
            self.verify_face_button.setText("Daftarkan Wajah")
        else:
            self.verify_face_button.setText("Verifikasi Wajah")
        self.verify_face_button.setEnabled(True)

    def _clear_pre_auth(self) -> None:
        self.stop_camera()
        self._registration_mode = False
        self._recent_frames.clear()
        if self._transient_master_key is not None:
            self._transient_master_key[:] = b"\x00" * len(
                self._transient_master_key
            )
        self._transient_master_key = None
        self._preauth_db_key = None
        self._preauth_user = None
        self._stored_encoding = None
        self._last_frame = None
        self._set_face_controls_visible(False)

    def hideEvent(self, event) -> None:
        self._clear_pre_auth()
        super().hideEvent(event)