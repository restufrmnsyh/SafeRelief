"""Halaman login tiga faktor dengan form akun dan pratinjau wajah terpusat."""

import sqlite3
from collections import deque

import cv2
import numpy as np
from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QPixmap, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import config
from auth import dongle, face_auth, login, session
from crypto import keys
from database import db, secure_store
from ui.face_capture_worker import FaceCaptureWorker, MODEL_LOCK
from ui.login_style import LOGIN_STYLE


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
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        super().__init__(app)
        self._stored_encoding = stored_encoding.copy()
        self._frame = frame.copy()
        self.finished.connect(self.deleteLater)
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def shutdown(self) -> None:
        """Selesaikan inferensi sebelum aplikasi menghancurkan worker."""
        self.requestInterruption()
        self.wait()

    def run(self) -> None:
        try:
            with MODEL_LOCK:
                if self.isInterruptionRequested():
                    return
                matched, score = face_auth.verify_face(
                    self._stored_encoding, self._frame
                )
            if not self.isInterruptionRequested():
                self.completed.emit(matched, score, "")
        except (FileNotFoundError, ValueError, cv2.error) as exc:
            if not self.isInterruptionRequested():
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
        self._capture_worker: FaceCaptureWorker | None = None

        self.setStyleSheet(LOGIN_STYLE)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("loginScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        root_layout.addWidget(self.scroll)
        canvas = QWidget()
        canvas.setObjectName("loginCanvas")
        self.canvas_layout = QVBoxLayout(canvas)
        self.canvas_layout.setContentsMargins(24, 24, 24, 24)
        self.scroll.setWidget(canvas)

        self.card_frame = QFrame()
        self.card_frame.setObjectName("mainLoginCard")
        self.card_frame.setMaximumWidth(860)
        self.card_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.work_layout = QVBoxLayout(self.card_frame)
        self.work_layout.setContentsMargins(32, 32, 32, 32)
        self.work_layout.setSpacing(12)
        self.work_layout.addWidget(self._label("Masuk ke SafeRelief", "loginTitle"))
        self.work_layout.addWidget(self._label(
            "Gunakan akun yang terhubung dengan dongle Anda.", "loginDescription"
        ))
        self.gate_label = self._label("Mencari dongle...", "loginGateStatus")
        self.work_layout.addWidget(self.gate_label)
        self.work_layout.addSpacing(12)
        self.content_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.content_layout.setSpacing(24)
        self.account_panel = QFrame()
        self.account_panel.setObjectName("loginAccount")
        account_layout = QVBoxLayout(self.account_panel)
        account_layout.setContentsMargins(0, 0, 0, 0)
        account_layout.setSpacing(8)
        account_layout.addWidget(self._label("Identitas akun", "loginSectionTitle"))
        account_layout.addSpacing(8)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Masukkan username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Masukkan password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        for caption, field in (("Username", self.username_input), ("Password", self.password_input)):
            label = self._label(caption, "loginFieldLabel")
            label.setBuddy(field)
            field.setAccessibleName(caption)
            field.setMinimumWidth(0)
            account_layout.addWidget(label)
            account_layout.addWidget(field)
            account_layout.addSpacing(8)
        self.submit_button = self._action("Periksa akun")
        self.submit_button.clicked.connect(self.submit_credentials)
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.submit_button.click)
        account_layout.addWidget(self.submit_button)
        account_layout.addWidget(self._label(
            "Kamera aktif setelah akun diperiksa.", "loginCameraHint"
        ))
        account_layout.addStretch(1)

        self.face_panel = QFrame()
        self.face_panel.setObjectName("loginFace")
        face_layout = QVBoxLayout(self.face_panel)
        face_layout.setContentsMargins(0, 0, 0, 0)
        face_layout.setSpacing(8)
        self.face_title = self._label("Verifikasi wajah", "loginSectionTitle")
        face_layout.addWidget(self.face_title)
        face_layout.addSpacing(8)
        self.camera_label = self._label("", "loginCamera")
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setMinimumHeight(176)
        # Abaikan lebar pixmap agar frame kamera tidak memperlebar form saat jendela diperkecil.
        self.camera_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.camera_label.setAccessibleName("Pratinjau kamera untuk verifikasi wajah")
        face_layout.addWidget(self.camera_label)
        self.verify_face_button = self._action("Verifikasi Wajah")
        self.verify_face_button.clicked.connect(self.verify_current_face)
        face_layout.addWidget(self.verify_face_button)
        self.camera_hint = self._label("Posisikan wajah di tengah kamera.", "loginCameraHint")
        face_layout.addWidget(self.camera_hint)
        face_layout.addStretch(1)
        self.content_layout.addWidget(self.account_panel, 1)
        self.content_layout.addWidget(self.face_panel, 1)
        self.work_layout.addLayout(self.content_layout)
        self.message_label = self._label("", "loginMessage")
        self.message_label.setMinimumHeight(40)
        self.message_label.setAccessibleName("Status autentikasi")
        self.work_layout.addWidget(self.message_label)
        self.canvas_layout.addStretch(1)
        self.canvas_layout.addWidget(self.card_frame, 0, Qt.AlignmentFlag.AlignHCenter)
        self.canvas_layout.addStretch(1)
        self.set_gate_status("Mencari dongle...")
        self._set_face_controls_visible(False)
        QWidget.setTabOrder(self.username_input, self.password_input)
        QWidget.setTabOrder(self.password_input, self.submit_button)
        QWidget.setTabOrder(self.submit_button, self.verify_face_button)

    @staticmethod
    def _label(text: str, name: str) -> QLabel:
        """Bungkus teks agar tetap terbaca pada jendela sempit."""
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        return label

    @staticmethod
    def _action(text: str) -> QPushButton:
        """Gunakan kontrol native dengan dukungan Enter dan Space."""
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_Return), button)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        shortcut.activated.connect(button.click)
        return button

    def set_gate_status(self, message: str) -> None:
        was_open = self._gate_open
        self._gate_open = message == "Dongle valid terdeteksi"

        self.gate_label.setText("Dongle valid terdeteksi" if self._gate_open else message)
        self.gate_label.setProperty("valid", self._gate_open)
        self.gate_label.style().unpolish(self.gate_label)
        self.gate_label.style().polish(self.gate_label)

        if was_open and not self._gate_open:
            self._clear_pre_auth()

    def show_session_ended(self, message: str) -> None:
        self._clear_pre_auth()
        self.username_input.clear()
        self.password_input.clear()
        self.set_gate_status("Dongle valid terdeteksi")
        self._set_message(message)

    def _set_message(self, text: str, tone: str = "error") -> None:
        """Pertahankan ukuran dan kontras pesan pada semua hasil autentikasi."""
        color = {"error": "#983A32", "success": "#216345", "info": "#4F50D9"}[tone]
        self.message_label.setStyleSheet(f"color: {color}; font-size: 13px; border: none;")
        self.message_label.setText(text)

    def submit_credentials(self) -> None:
        self._clear_pre_auth()
        self.message_label.clear()
        if not self._gate_open:
            self._set_message("Dongle valid belum terdeteksi.")
            return

        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            self._set_message("Username dan password wajib diisi.")
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
                self._set_message(
                    "Wajah belum terdaftar. Posisikan wajah di kamera lalu klik 'Daftarkan Wajah'.",
                    "info",
                )
                return

            self._registration_mode = False
            self._stored_encoding = face_auth.bytes_to_encoding(encoding_bytes)
            self._set_face_controls_visible(True)
            self._set_message("Kredensial valid. Tatap kamera dan verifikasi.", "success")
        except (ValueError, OSError, sqlite3.Error, InvalidTag) as exc:
            self._clear_pre_auth()
            self._set_message(str(exc))
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
            self.camera_label.contentsRect().size(),
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
        self._set_message(message)
        self.verify_face_button.setEnabled(False)

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Susun ulang konten, lalu sesuaikan preview tanpa memotong frame."""
        super().resizeEvent(event)
        columns = self.width() >= 680
        margin = 24 if columns else 16
        self.canvas_layout.setContentsMargins(margin, margin, margin, margin)
        # Sisakan jalur scrollbar supaya form panjang tidak memicu gulir horizontal.
        self.card_frame.setFixedWidth(min(860, max(240, self.width() - margin * 2 - 12)))
        self.content_layout.setDirection(
            QBoxLayout.Direction.LeftToRight if columns else QBoxLayout.Direction.TopToBottom
        )
        self.work_layout.setContentsMargins(32 if columns else 24, 28, 32 if columns else 24, 24)
        if self._last_frame is not None:
            rgb = cv2.cvtColor(self._last_frame, cv2.COLOR_BGR2RGB)
            image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888)
            self.camera_label.setPixmap(
                QPixmap.fromImage(image).scaled(
                    self.camera_label.contentsRect().size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def register_current_face(self) -> None:
        """Daftarkan wajah pengguna dari feed kamera aktif tanpa membuka webcam baru."""
        if not self._gate_open or self._preauth_user is None:
            self._set_message("Sesi pendaftaran wajah belum siap.")
            return

        if self._capture_worker is not None:
            return
        frames = list(self._recent_frames)
        if not frames and self._last_frame is not None:
            frames = [self._last_frame]
        if not frames:
            self._set_message("Tunggu sampai frame webcam tersedia.")
            return
        worker = FaceCaptureWorker(frames)
        self._capture_worker = worker
        worker.completed.connect(self._registration_finished)
        worker.finished.connect(self._capture_finished)
        self.verify_face_button.setEnabled(False)
        self._set_message("Merekam wajah...", "info")
        worker.start()

    def _capture_finished(self) -> None:
        """Hasil dari permintaan lama tidak boleh mengubah kontrol sesi baru."""
        if self.sender() is self._capture_worker:
            self._capture_worker = None
            if self._gate_open and self._preauth_user is not None:
                self.verify_face_button.setEnabled(True)

    def _registration_finished(self, average_encoding: object, error: str) -> None:
        """Simpan hasil hanya jika permintaan dan faktor autentikasi masih berlaku."""
        if self.sender() is not self._capture_worker or not self._gate_open:
            return
        if error:
            self._set_message(error)
            return

        user = self._preauth_user
        master_key = self._transient_master_key
        db_key = self._preauth_db_key
        if user is None or master_key is None or db_key is None:
            self._set_message("Sesi pendaftaran wajah sudah kedaluwarsa.")
            self._clear_pre_auth()
            return

        try:
            current_user = secure_store.require_active_user(self._conn, int(user["id"]))
            dongle.verify_dongle(current_user)
            secure_store.save_face_encoding(
                self._conn,
                db_key,
                int(user["id"]),
                face_auth.encoding_to_bytes(average_encoding),
            )
            self._stored_encoding = average_encoding
            self._registration_mode = False
            self._set_face_controls_visible(True)
            self._set_message("Wajah berhasil didaftarkan.", "success")
            db.log_activity(self._conn, "LOGIN_SUCCESS", user_id=int(user["id"]))
            session.login(user, bytes(master_key))
            self._clear_pre_auth()
            self.authenticated.emit(user)
        except (ValueError, OSError, sqlite3.Error, cv2.error) as exc:
            self._set_message(str(exc))

    def verify_current_face(self) -> None:
        if not self._gate_open:
            self._set_message("Tunggu sampai frame webcam tersedia.")
            return

        if self._registration_mode:
            self.register_current_face()
            return

        if self._stored_encoding is None or self._last_frame is None:
            self._set_message("Tunggu sampai frame webcam tersedia.")
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
        self._set_message("Memverifikasi wajah...", "info")
        worker.start()

    def _face_verification_finished(
        self, matched: bool, score: float, error: str
    ) -> None:
        if (self.sender() is not None and self.sender() is not self._face_worker
                or not self._gate_open):
            return
        if error:
            self._set_message(error)
            self.verify_face_button.setEnabled(True)
            return
        if not matched:
            if score == 0.0:
                self._set_message("Wajah tidak terdeteksi. Coba lagi.")
            else:
                self._set_message(
                    f"Wajah tidak cocok (skor {score:.3f})."
                )
            self.verify_face_button.setEnabled(True)
            return

        user = self._preauth_user
        master_key = self._transient_master_key
        if user is None or master_key is None:
            self._set_message("Sesi autentikasi sudah kedaluwarsa.")
            self._clear_pre_auth()
            return

        try:
            current_user = db.get_user_by_id(self._conn, int(user["id"]))
            if current_user is None or not current_user["is_active"]:
                raise PermissionError("Akun dinonaktifkan saat proses login.")
            dongle.verify_dongle(current_user)
            db.log_activity(self._conn, "LOGIN_SUCCESS", user_id=int(user["id"]))
        except (OSError, ValueError, sqlite3.Error, PermissionError) as exc:
            self._set_message(str(exc))
            self._clear_pre_auth()
            return

        session.login(user, bytes(master_key))
        self._clear_pre_auth()
        self.authenticated.emit(user)

    def _face_worker_finished(self) -> None:
        if self.sender() is not self._face_worker:
            return
        self._face_worker = None
        if self._gate_open:
            self.verify_face_button.setEnabled(True)

    def _set_face_controls_visible(self, visible: bool) -> None:
        """Perbarui petunjuk kamera tanpa mengubah keputusan autentikasi."""
        if not visible:
            self.camera_label.clear()
            self.camera_label.setText("Kamera belum aktif\n\nPeriksa akun untuk membuka kamera.")
            self.face_title.setText("Verifikasi wajah")
            self.camera_hint.setText("Posisikan wajah di tengah kamera.")
            self.verify_face_button.setText("Verifikasi Wajah")
            self.verify_face_button.setEnabled(False)
            return

        self.camera_label.setText("Membuka kamera...")
        if self._registration_mode:
            self.verify_face_button.setText("Daftarkan Wajah")
            self.face_title.setText("Pendaftaran wajah")
            self.camera_hint.setText("Login pertama: daftarkan wajah Anda.")
        else:
            self.verify_face_button.setText("Verifikasi Wajah")
            self.face_title.setText("Verifikasi wajah")
            self.camera_hint.setText("Tatap kamera, lalu verifikasi wajah.")
        self.verify_face_button.setEnabled(True)

    def _clear_pre_auth(self) -> None:
        if self._face_worker is not None:
            self._face_worker.requestInterruption()
            self._face_worker = None
        if self._capture_worker is not None:
            self._capture_worker.requestInterruption()
            self._capture_worker = None
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
