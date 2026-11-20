"""Unduhan .enc dan pemulihan salinan asli untuk halaman foto dan laporan."""

import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

import config
from auth import session
from crypto import chacha_module
from database import secure_store
from ui.file_preview import FilePreviewDialog, prepare_preview


Operation = Literal["copy", "encrypt", "decrypt"]
ENC_FILTER = "Berkas terenkripsi (*.enc)"


class TransferWorker(QThread):
    """Siapkan hasil di folder tujuan agar bisa dipindahkan secara atomik."""

    def __init__(self, source: Path, destination: Path, operation: Operation,
                 key: bytes, parent: QObject) -> None:
        super().__init__(parent)
        self.source = source
        self.destination = destination
        self.operation = operation
        self.key = bytearray(key)
        self.temporary: Path | None = None
        self.error = "Proses berkas belum selesai."
        self.invalid_data = False

    def run(self) -> None:
        try:
            with tempfile.NamedTemporaryFile(dir=self.destination.parent, delete=False) as output:
                self.temporary = Path(output.name)
            if self.operation == "copy":
                shutil.copyfile(self.source, self.temporary)
            elif self.operation == "encrypt":
                chacha_module.encrypt_file(str(self.source), str(self.temporary), bytes(self.key))
            else:
                try:
                    chacha_module.decrypt_file(str(self.source), str(self.temporary), bytes(self.key))
                except (InvalidTag, ValueError):
                    self.invalid_data = True
                    self.error = "File rusak atau telah diubah."
                    return
            self.error = ""
        except MemoryError:
            self.error = "Memori tidak cukup untuk memproses berkas ini."
        except (OSError, ValueError, OverflowError) as exc:
            self.error = str(exc)
        finally:
            self.key[:] = bytes(len(self.key))

    def discard(self) -> None:
        if self.temporary is not None:
            self.temporary.unlink(missing_ok=True)


class PreviewWorker(QThread):
    """Dekripsi dan siapkan isi untuk ditampilkan tanpa salinan di disk."""

    def __init__(self, source: Path, name: str, key: bytes, parent: QObject) -> None:
        super().__init__(parent)
        self.source = source
        self.name = name
        self.key = bytearray(key)
        self.content: QImage | str | bytes | None = None
        self.error = "Pratinjau belum siap."
        self.invalid_data = False

    def run(self) -> None:
        try:
            try:
                data = chacha_module.decrypt(self.source.read_bytes(), bytes(self.key))
            except (InvalidTag, ValueError):
                self.invalid_data = True
                self.error = "File rusak atau telah diubah."
                return
            self.content = prepare_preview(data)
            self.error = ""
        except (OSError, ValueError, OverflowError) as exc:
            self.error = str(exc)
        except MemoryError:
            self.error = "Memori tidak cukup untuk membuka pratinjau."
        finally:
            self.key[:] = bytes(len(self.key))

    def discard(self) -> None:
        self.content = None


class EncryptedDownloads(QObject):
    """Pilih file lokal dan periksa sesi admin lagi sebelum menerbitkan hasil."""

    status = Signal(str)

    def __init__(self, page: QWidget, conn: sqlite3.Connection, user_id: int,
                 admin_authorized: Callable[[], bool]) -> None:
        super().__init__(page)
        self.page = page
        self.conn = conn
        self.user_id = user_id
        self.admin_authorized = admin_authorized
        self.worker: TransferWorker | PreviewWorker | None = None
        self.preview: FilePreviewDialog | None = None
        self.closed = False

    def download(self, source: Path, name: str, *, encrypt_photo: bool = False) -> None:
        if not self._ready():
            return
        output, _ = QFileDialog.getSaveFileName(
            self.page, "Unduh berkas terenkripsi", Path(name).name + ".enc", ENC_FILTER
        )
        if not output:
            return
        destination = Path(output)
        if destination.suffix.lower() != ".enc":
            QMessageBox.warning(self.page, "Nama berkas", "Gunakan ekstensi .enc untuk unduhan.")
            return
        self._start(source, destination, "encrypt" if encrypt_photo else "copy")

    def choose_and_decrypt(self) -> None:
        if not self._ready():
            return
        selected, _ = QFileDialog.getOpenFileName(self.page, "Buka Berkas Terenkripsi", "", ENC_FILTER)
        if not selected or not self._ready():
            return
        source = Path(selected)
        if source.suffix.lower() != ".enc":
            QMessageBox.warning(self.page, "Buka berkas", "Pilih file .enc hasil unduhan SafeRelief.")
            return
        self.show_preview(source, source.with_suffix("").name)

    def show_preview(self, source: Path, name: str) -> None:
        if self._ready():
            self._run(PreviewWorker(source, name, session.get_derived_key(config.HKDF_LABEL_FILE), self))

    def decrypt(self, source: Path, destination: Path) -> None:
        self._start(source, destination, "decrypt")

    def _ready(self) -> bool:
        if self.closed or not self.admin_authorized():
            return False
        if self.worker is not None:
            self.status.emit("Tunggu proses berkas yang sedang berjalan.")
            return False
        return True

    def _start(self, source: Path, destination: Path, operation: Operation) -> None:
        if not self._ready():
            return
        try:
            target = destination.resolve()
            if target == source.resolve() or target.is_relative_to(config.STORAGE_DIR.resolve()):
                raise ValueError("Pilih lokasi terpisah dari berkas sumber dan folder storage.")
            if operation == "decrypt" and destination.suffix.lower() == ".enc":
                raise ValueError("Gunakan ekstensi asli untuk hasil dekripsi.")
            key = b"" if operation == "copy" else session.get_derived_key(config.HKDF_LABEL_FILE)
            worker = TransferWorker(source, destination, operation, key, self)
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.warning(self.page, "Gagal menyiapkan berkas", str(exc))
            return
        self._run(worker)

    def _run(self, worker: TransferWorker | PreviewWorker) -> None:
        self.worker = worker
        worker.finished.connect(self._finished)
        self.status.emit("Memproses berkas…")
        worker.start()

    def _finished(self) -> None:
        worker = self.worker
        if worker is None:
            return
        self.worker = None
        try:
            if self.closed or not self.admin_authorized():
                return
            if worker.invalid_data:
                try:
                    secure_store.log_activity(self.conn, "FILE_DECRYPT_FAILED", user_id=self.user_id)
                except (PermissionError, sqlite3.Error):
                    worker.error += " Gagal mencatat aktivitas."
            if worker.error:
                raise ValueError(worker.error)
            if isinstance(worker, PreviewWorker):
                if worker.content is None:
                    raise ValueError("Isi pratinjau tidak tersedia.")
                if self.preview is not None:
                    self.preview.reject()
                self.preview = FilePreviewDialog(worker.name, worker.content, self.page)
                self.preview.finished.connect(self._preview_closed)
                self.preview.open()
                action = "FILE_DECRYPTED"
                message = "Berkas dibuka dalam pratinjau."
            else:
                os.replace(worker.temporary, worker.destination)
                if worker.operation == "decrypt":
                    action = "FILE_DECRYPTED"
                    message = f"Hasil dekripsi disimpan sebagai {worker.destination.name}."
                else:
                    action = "FILE_DOWNLOADED"
                    message = f"Unduhan terenkripsi disimpan sebagai {worker.destination.name}."
            try:
                secure_store.log_activity(self.conn, action, user_id=self.user_id)
            except (PermissionError, sqlite3.Error):
                message += " Gagal mencatat aktivitas."
            self.status.emit(message)
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.status.emit(str(exc))
            QMessageBox.critical(self.page, "Gagal memproses berkas", str(exc))
        finally:
            worker.discard()
            worker.deleteLater()

    def _preview_closed(self) -> None:
        self.preview = None

    def stop(self, *, cancel_pending: bool) -> None:
        self.closed = cancel_pending
        if cancel_pending and self.preview is not None:
            self.preview.reject()
        if self.worker is not None:
            self.worker.wait()
            if cancel_pending:
                self.worker.discard()
