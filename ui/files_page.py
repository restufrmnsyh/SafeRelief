"""Halaman berkas laporan ChaCha20-Poly1305 untuk relawan dan admin."""

import base64
import hashlib
import os
import sqlite3
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
from auth import session
from crypto import chacha_module
from database import db, secure_store
from ui.encrypted_downloads import EncryptedDownloads


class FileEncryptWorker(QThread):
    """Enkripsi dan hash berkas di worker supaya UI tidak macet."""

    def __init__(
        self,
        source_path: Path,
        encrypted_path: Path,
        key: bytes,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.source_path = source_path
        self.encrypted_path = encrypted_path
        self.key = bytearray(key)
        self.file_hash = ""
        self.file_size = 0
        self.error = ""

    def run(self) -> None:
        try:
            self.file_size = self.source_path.stat().st_size
            if self.file_size > config.MAX_FILE_SIZE:
                raise ValueError("Ukuran file melebihi batas 50 MB.")
            with self.source_path.open("rb") as source:
                self.file_hash = hashlib.file_digest(source, "sha256").hexdigest()
            chacha_module.encrypt_file(
                str(self.source_path), str(self.encrypted_path), bytes(self.key)
            )
        except (OSError, ValueError) as exc:
            self.encrypted_path.unlink(missing_ok=True)
            self.error = str(exc)
        finally:
            self.key[:] = b"\x00" * len(self.key)


class FilesPage(QWidget):
    """Relawan mengunggah; hanya admin dapat mengunduh dan mendekripsi."""

    dashboard_requested = Signal()
    _columns = ("ID", "Nama asli", "Ukuran", "Pengunggah", "Waktu")
    _allowed_extensions = (
        ".docx", ".pptx", ".pdf", ".xlsx",
        ".mp4", ".mov", ".mkv", ".avi", ".webm",
    )

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = session.get_current_user()
        self._user_id = int(self._user["id"])
        self._role = str(self._user["role"])
        if self._role not in ("admin", "relawan"):
            raise PermissionError("Peran ini tidak diizinkan melihat berkas.")
        self._files: list[dict] = []
        self._worker: QThread | None = None
        self._pending_upload: tuple[Path, Path] | None = None
        self._cancelled = False

        self.setStyleSheet(
            "QWidget { background: #edf5fb; color: #1E2A39; }"
            "QLabel { color: #1E2A39; }"
            "QTableWidget, QLineEdit, QComboBox, QPlainTextEdit { background: #f9fcff; border: 1px solid #dfeaf5; border-radius: 10px; }"
            "QPushButton { background-color: #ffffff; color: #1E2A39; border: 1px solid #dfeaf5; border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #eef7ff; border-color: #bfdcf0; }"
        )

        self.table = QTableWidget(0, len(self._columns) + 1)
        self.table.setHorizontalHeaderLabels([*self._columns, "Aksi"])
        if self._role == "admin":
            header = self.table.horizontalHeaderItem(1)
            header.setText("Ciphertext berkas (Base64)")
            header.setToolTip("Menampilkan hingga 48 byte pertama ciphertext dari isi berkas.")
        self.table.setColumnHidden(0, True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.upload_button = QPushButton("Unggah Berkas")
        self.upload_button.setVisible(self._role == "relawan")
        self.upload_button.clicked.connect(self.choose_and_upload)
        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self.delete_selected_file)
        self.status_label = QLabel()
        self.downloads = EncryptedDownloads(self, conn, self._user_id, lambda: self._authorized("admin"))
        self.downloads.status.connect(self.status_label.setText)
        self.open_button = QPushButton("Buka Berkas Terenkripsi")
        self.open_button.clicked.connect(self.downloads.choose_and_decrypt)
        self.open_button.setVisible(self._role == "admin")
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self._confirm_logout)

        actions = QHBoxLayout()
        if self._role == "relawan":
            actions.addWidget(self.upload_button)
        if self._role == "admin":
            self.preview_button = QPushButton("Pratinjau")
            self.preview_button.clicked.connect(self.preview_selected)
            actions.addWidget(self.preview_button)
            actions.addWidget(self.open_button)
            actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.back_button)
        actions.addWidget(self.logout_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Berkas Laporan Terenkripsi"))
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        self.refresh()

    def _confirm_logout(self) -> None:
        """Minta konfirmasi sebelum logout dari halaman berkas."""
        window = self.window()
        if window is None or not hasattr(window, "_end_session"):
            return
        reply = QMessageBox.question(
            self,
            "Logout",
            "Yakin ingin logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            window._end_session("Logout manual dari halaman berkas.")

    def choose_and_upload(self) -> None:
        """Pilih file sumber; salinan terenkripsi disimpan memakai nama UUID."""
        patterns = " ".join(f"*{extension}" for extension in self._allowed_extensions)
        source, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih berkas laporan",
            "",
            f"Dokumen dan video ({patterns})",
        )
        if source:
            self.upload_file(Path(source))

    def upload_file(self, source_path: Path) -> None:
        """Jalankan ChaCha20-Poly1305 di worker dan simpan record via secure_store."""
        if not self._authorized("relawan"):
            return
        if self._worker is not None:
            return
        if not source_path.is_file():
            QMessageBox.critical(self, "Gagal mengunggah", "File sumber tidak ditemukan.")
            return
        try:
            suffix = source_path.suffix.lower()
            if suffix not in self._allowed_extensions:
                extensions = ", ".join(self._allowed_extensions)
                raise ValueError(
                    f"Format berkas tidak didukung. Pilih berkas dengan ekstensi {extensions}."
                )
            if source_path.stat().st_size > config.MAX_FILE_SIZE:
                raise ValueError("Ukuran file melebihi batas 50 MB.")
            config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{uuid.uuid4().hex}.enc"
            encrypted_path = config.STORAGE_DIR / filename
            worker = FileEncryptWorker(
                source_path,
                encrypted_path,
                session.get_derived_key(config.HKDF_LABEL_FILE),
                self,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Gagal mengunggah", str(exc))
            return

        self._pending_upload = (source_path, encrypted_path)
        self.upload_button.setEnabled(False)
        worker.finished.connect(self._upload_finished)
        self._worker = worker
        worker.start()

    def _upload_finished(self) -> None:
        worker = self._worker
        pending = self._pending_upload
        self._worker = None
        self._pending_upload = None
        self.upload_button.setEnabled(True)
        if worker is not None:
            worker.deleteLater()
        if self._cancelled:
            if pending is not None:
                pending[1].unlink(missing_ok=True)
            return
        error = (
            worker.error
            if isinstance(worker, FileEncryptWorker)
            else "Hasil worker unggah tidak tersedia."
        )
        if error:
            self.status_label.setText(error)
            QMessageBox.critical(self, "Gagal mengenkripsi berkas", error)
            return
        if not isinstance(worker, FileEncryptWorker) or pending is None:
            raise RuntimeError("Hasil worker unggah tidak tersedia.")
        source_path, encrypted_path = pending
        if not self._authorized("relawan"):
            encrypted_path.unlink(missing_ok=True)
            return
        try:
            secure_store.save_file(
                self._conn,
                uploader_id=self._user_id,
                nama_asli=source_path.name,
                path_enc=encrypted_path.name,
                ukuran=worker.file_size,
                file_hash=worker.file_hash,
            )
        except (PermissionError, sqlite3.Error, ValueError) as exc:
            encrypted_path.unlink(missing_ok=True)
            QMessageBox.critical(self, "Gagal menyimpan metadata berkas", str(exc))
            return
        self.refresh()
        self.status_label.setText("Berkas berhasil dienkripsi dan disimpan.")

    def _admin_report(self, file_id: int | None) -> tuple[Path, str] | None:
        """Ambil sumber terenkripsi dan nama tampilan milik baris yang dipilih."""
        if not self._authorized("admin"):
            return
        if file_id is None:
            row_index = self.table.currentRow()
            if row_index < 0:
                QMessageBox.information(self, "Berkas laporan", "Pilih berkas terlebih dahulu.")
                return
            file_id = int(self.table.item(row_index, 0).text())
        try:
            row = secure_store.get_file_for_admin(self._conn, self._user_id, file_id)
            if row is None:
                raise ValueError("Catatan berkas tidak ditemukan.")
            return self._stored_file_path(row["path_enc"]), row["nama_asli"]
        except (PermissionError, OSError, sqlite3.Error, ValueError) as exc:
            QMessageBox.warning(self, "Gagal membaca berkas", str(exc))
            return None

    def choose_and_download(self, file_id: int | None = None) -> None:
        report = self._admin_report(file_id)
        if report is not None:
            self.downloads.download(*report)

    def preview_selected(self) -> None:
        report = self._admin_report(None)
        if report is not None:
            self.downloads.show_preview(*report)

    def delete_selected_file(self) -> None:
        """Hapus berkas yang dipilih dengan konfirmasi dan bersihkan file terenkripsi."""
        if not self._authorized():
            return
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Hapus berkas", "Pilih berkas terlebih dahulu.")
            return
        file_id = int(self.table.item(row, 0).text())
        metadata = next((item for item in self._files if item["id"] == file_id), None)
        if metadata is None:
            QMessageBox.warning(self, "Hapus berkas", "Berkas tidak ditemukan.")
            return
        answer = QMessageBox.question(
            self,
            "Konfirmasi hapus berkas",
            "Yakin ingin menghapus berkas ini? File terenkripsi yang terkait juga akan dihapus.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            encrypted_path = self._stored_file_path(str(metadata["path_enc"]))
            secure_store.delete_file(
                self._conn,
                user_id=self._user_id,
                role=self._role,
                file_id=file_id,
            )
            encrypted_path.unlink(missing_ok=True)
            self.status_label.setText("Berkas berhasil dihapus.")
            self.refresh()
        except (PermissionError, ValueError, sqlite3.Error, OSError) as exc:
            QMessageBox.critical(self, "Gagal menghapus berkas", str(exc))

    def decrypt_file(self, file_id: int, destination: Path) -> None:
        """Pulihkan berkas terdaftar ke tujuan yang dipilih admin."""
        report = self._admin_report(file_id)
        if report is not None:
            self.downloads.decrypt(report[0], destination)

    def refresh(self) -> None:
        """Muat daftar berkas sesuai hak akses peran aktif."""
        if not self._authorized():
            return
        users = {
            int(user["id"]): str(user["nama_lengkap"] or user["username"])
            for user in db.list_users(self._conn)
        }
        self._files = [
            dict(row)
            for row in secure_store.list_files(
                self._conn, self._user_id, self._role
            )
        ]
        self.table.setRowCount(0)
        for file_row in self._files:
            row = self.table.rowCount()
            self.table.insertRow(row)
            file_label = (
                self._ciphertext_preview(file_row["path_enc"])
                if self._role == "admin" else file_row["nama_asli"]
            )
            values = (
                file_row["id"],
                file_label,
                f"{int(file_row['ukuran'])} byte",
                users.get(file_row.get("uploader_id"), "-"),
                file_row["created_at"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if self._role == "admin" and column == 1:
                    item.setToolTip(item.text())
                self.table.setItem(row, column, item)
            if self._role == "admin":
                action = QPushButton("Unduh")
                action.clicked.connect(
                    lambda _checked=False, file_id=int(file_row["id"]): self.choose_and_download(file_id)
                )
                self.table.setCellWidget(row, 5, action)
        self.table.resizeColumnsToContents()

    @staticmethod
    def _stored_file_path(filename: str) -> Path:
        """Jangan izinkan path di database keluar dari folder storage."""
        relative = Path(filename)
        root = config.STORAGE_DIR.resolve()
        candidate = (root / relative).resolve()
        if relative.is_absolute() or len(relative.parts) != 1 or candidate.parent != root:
            raise ValueError("Path file di database tidak valid.")
        return candidate

    @classmethod
    def _ciphertext_preview(cls, filename: str) -> str:
        """Lewati nonce dan tag agar sel hanya memuat ciphertext isi berkas."""
        try:
            with cls._stored_file_path(filename).open("rb") as stream:
                size = stream.seek(0, os.SEEK_END) - config.CHACHA20_NONCE_LENGTH - 16
                if size < 0:
                    return "Format .enc tidak lengkap"
                if size == 0:
                    return "Berkas kosong"
                stream.seek(config.CHACHA20_NONCE_LENGTH)
                prefix = stream.read(min(size, 48))
        except (OSError, ValueError, RuntimeError):
            return "Berkas tidak tersedia"
        encoded = base64.b64encode(prefix).decode("ascii")
        return encoded + ("…" if size > len(prefix) else "")

    def stop_worker(self, *, cancel_pending: bool = False) -> None:
        """Tunggu enkripsi/dekripsi berkas sebelum jendela aplikasi ditutup."""
        self.downloads.stop(cancel_pending=cancel_pending)
        self._cancelled = cancel_pending
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        if cancel_pending:
            if self._pending_upload is not None:
                _source, encrypted_path = self._pending_upload
                encrypted_path.unlink(missing_ok=True)
                self._pending_upload = None

    def _authorized(self, required_role: str | None = None) -> bool:
        """Tolak aksi jika akun diblokir atau widget berasal dari sesi lama."""
        try:
            current = session.get_current_user()
            if int(current["id"]) != self._user_id:
                raise PermissionError("Sesi pengguna telah berubah.")
            if required_role is not None and self._role != required_role:
                raise PermissionError(
                    f"Hanya {required_role} yang dapat melakukan tindakan ini."
                )
            secure_store.require_active_user(
                self._conn, self._user_id, self._role
            )
            return True
        except (RuntimeError, PermissionError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Akses ditolak", str(exc))
            return False
