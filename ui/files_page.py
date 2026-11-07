"""Halaman berkas laporan ChaCha20-Poly1305 untuk relawan dan admin."""

import hashlib
import os
import sqlite3
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
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


class FileDecryptWorker(QThread):
    """Dekripsi ke file sementara lalu pindahkan hasil utuh ke tujuan."""

    def __init__(
        self,
        encrypted_path: Path,
        destination: Path,
        key: bytes,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.encrypted_path = encrypted_path
        self.destination = destination
        self.key = bytearray(key)
        self.error = ""

    def run(self) -> None:
        temporary = self.destination.with_name(
            f".{self.destination.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            chacha_module.decrypt_file(
                str(self.encrypted_path), str(temporary), bytes(self.key)
            )
            os.replace(temporary, self.destination)
        except InvalidTag:
            temporary.unlink(missing_ok=True)
            self.error = "invalid_tag"
        except (OSError, ValueError) as exc:
            temporary.unlink(missing_ok=True)
            self.error = str(exc)
        finally:
            self.key[:] = b"\x00" * len(self.key)


class FilesPage(QWidget):
    """Relawan mengunggah; hanya admin dapat mengunduh dan mendekripsi."""

    dashboard_requested = Signal()
    _columns = ("ID", "Nama asli", "Ukuran", "Pengunggah", "Waktu")

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
        self._pending_download_id: int | None = None

        self.table = QTableWidget(0, len(self._columns))
        self.table.setHorizontalHeaderLabels(self._columns)
        self.table.setColumnHidden(0, True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.upload_button = QPushButton("Unggah Berkas")
        self.upload_button.setVisible(self._role == "relawan")
        self.upload_button.clicked.connect(self.choose_and_upload)
        self.download_button = QPushButton("Unduh dan Dekripsi")
        self.download_button.setVisible(self._role == "admin")
        self.download_button.clicked.connect(self.choose_and_download)
        self.status_label = QLabel()
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)

        actions = QHBoxLayout()
        if self._role == "relawan":
            actions.addWidget(self.upload_button)
        if self._role == "admin":
            actions.addWidget(self.download_button)
        actions.addStretch()
        actions.addWidget(self.back_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Berkas Laporan Terenkripsi"))
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        self.refresh()

    def choose_and_upload(self) -> None:
        """Pilih file sumber; salinan terenkripsi disimpan memakai nama UUID."""
        source, _ = QFileDialog.getOpenFileName(
            self, "Pilih berkas laporan", "", "Semua file (*)"
        )
        if source:
            self.upload_file(Path(source))

    def upload_file(self, source_path: Path) -> None:
        """Jalankan ChaCha20-Poly1305 di worker dan simpan record via secure_store."""
        if self._role != "relawan":
            raise PermissionError("Hanya relawan yang dapat mengunggah berkas.")
        if self._worker is not None:
            return
        if not source_path.is_file():
            QMessageBox.critical(self, "Gagal mengunggah", "File sumber tidak ditemukan.")
            return
        try:
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

    def choose_and_download(self) -> None:
        """Minta tujuan output untuk berkas terpilih; admin-only."""
        if self._role != "admin":
            raise PermissionError("Hanya admin yang dapat mengunduh berkas.")
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Unduh berkas", "Pilih berkas terlebih dahulu.")
            return
        file_id = int(self.table.item(row, 0).text())
        metadata = next(item for item in self._files if item["id"] == file_id)
        destination, _ = QFileDialog.getSaveFileName(
            self, "Simpan berkas terdekripsi", str(metadata["nama_asli"])
        )
        if destination:
            self.decrypt_file(file_id, Path(destination))

    def decrypt_file(self, file_id: int, destination: Path) -> None:
        """Dekripsi berkas terpilih secara aman; hanya admin boleh memanggilnya."""
        if self._role != "admin":
            raise PermissionError("Hanya admin yang dapat mengunduh berkas.")
        if self._worker is not None:
            return
        try:
            file_row = secure_store.get_file_for_admin(
                self._conn, self._user_id, file_id
            )
            if file_row is None:
                raise ValueError("Catatan berkas tidak ditemukan.")
            encrypted_path = self._stored_file_path(str(file_row["path_enc"]))
            if not encrypted_path.is_file():
                raise FileNotFoundError("File terenkripsi tidak ditemukan di storage.")
            if encrypted_path.resolve() == destination.resolve():
                raise ValueError("Tujuan dekripsi tidak boleh menimpa file terenkripsi.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            worker = FileDecryptWorker(
                encrypted_path,
                destination,
                session.get_derived_key(config.HKDF_LABEL_FILE),
                self,
            )
        except (PermissionError, OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Gagal menyiapkan dekripsi", str(exc))
            return

        self._pending_download_id = file_id
        self.download_button.setEnabled(False)
        worker.finished.connect(self._download_finished)
        self._worker = worker
        worker.start()

    def _download_finished(self) -> None:
        worker = self._worker
        file_id = self._pending_download_id
        self._pending_download_id = None
        self._worker = None
        self.download_button.setEnabled(True)
        if worker is not None:
            worker.deleteLater()
        error = (
            worker.error
            if isinstance(worker, FileDecryptWorker)
            else "Hasil worker dekripsi tidak tersedia."
        )
        if error == "invalid_tag":
            message = "File rusak atau telah diubah."
            try:
                secure_store.log_activity(
                    self._conn,
                    "FILE_DECRYPT_FAILED",
                    user_id=self._user_id,
                    detail=f"file_id={file_id}",
                )
            except sqlite3.Error as exc:
                message += f" Gagal mencatat event: {exc}"
            self.status_label.setText(message)
            QMessageBox.critical(self, "Dekripsi gagal", message)
        elif error:
            self.status_label.setText(error)
            QMessageBox.critical(self, "Dekripsi gagal", error)
        else:
            self.status_label.setText("Berkas berhasil didekripsi.")
            QMessageBox.information(self, "Unduh berkas", "Berkas berhasil disimpan.")

    def refresh(self) -> None:
        """Muat daftar berkas sesuai hak akses peran aktif."""
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
            values = (
                file_row["id"],
                file_row["nama_asli"],
                f"{int(file_row['ukuran'])} byte",
                users.get(file_row.get("uploader_id"), "-"),
                file_row["created_at"],
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
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

    def stop_worker(self) -> None:
        """Tunggu enkripsi/dekripsi berkas sebelum jendela aplikasi ditutup."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
