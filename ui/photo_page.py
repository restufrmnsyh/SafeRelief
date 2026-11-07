"""Halaman dokumentasi foto PNG dengan payload AES-GCM di kanal LSB."""

import hashlib
import json
import sqlite3
import uuid
import warnings
from datetime import datetime
from pathlib import Path

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
from auth import session
from crypto import aes_module, stego_lsb
from database import secure_store


class PhotoEmbedWorker(QThread):
    """Jalankan hashing gambar dan LSB di luar event loop UI."""

    def __init__(
        self,
        source_path: Path,
        output_path: Path,
        metadata: dict[str, object],
        stego_key: bytes,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._source_path = source_path
        self._output_path = output_path
        self._metadata = metadata
        self._stego_key = bytearray(stego_key)
        self.output = ""
        self.image_hash = ""
        self.warning = ""
        self.error = ""

    def run(self) -> None:
        try:
            with self._source_path.open("rb") as source:
                image_hash = hashlib.file_digest(source, "sha256").hexdigest()
            payload = dict(self._metadata)
            payload["original_sha256"] = image_hash
            encrypted_payload = aes_module.encrypt(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                self._stego_key,
            )
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                output = stego_lsb.embed(
                    str(self._source_path),
                    encrypted_payload,
                    str(self._output_path),
                )
            self.output = str(output)
            self.image_hash = image_hash
            self.warning = "; ".join(str(item.message) for item in caught)
        except (OSError, ValueError) as exc:
            self.error = str(exc)
        finally:
            self._stego_key[:] = b"\x00" * len(self._stego_key)


class PhotoPage(QWidget):
    """Relawan menyisipkan foto; admin memverifikasi dan mengekstrak metadata."""

    dashboard_requested = Signal()
    _columns = ("ID", "Korban", "Posko", "Keterangan", "Waktu")

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = session.get_current_user()
        self._user_id = int(self._user["id"])
        self._role = str(self._user["role"])
        if self._role not in ("admin", "relawan"):
            raise PermissionError("Peran ini tidak diizinkan melihat foto.")
        self._photos: list[dict] = []
        self._worker: PhotoEmbedWorker | None = None
        self._pending_metadata: dict[str, object] | None = None
        self._pending_output: Path | None = None
        self._cancelled = False

        self.table = QTableWidget(0, len(self._columns))
        self.table.setHorizontalHeaderLabels(self._columns)
        self.table.setColumnHidden(0, True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.victim_id_input = QLineEdit()
        self.victim_id_input.setPlaceholderText("ID korban (opsional)")
        self.posko_id_input = QLineEdit()
        self.posko_id_input.setPlaceholderText("ID posko (opsional)")
        self.coordinates_input = QLineEdit()
        self.coordinates_input.setPlaceholderText("Koordinat (opsional)")
        self.caption_input = QLineEdit()
        self.caption_input.setPlaceholderText("Keterangan foto")
        self._selected_image_path: Path | None = None
        self.choose_photo_button = QPushButton("Pilih Foto")
        self.choose_photo_button.clicked.connect(self.choose_photo)
        self.upload_button = QPushButton("Sisipkan")
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.embed_selected_photo)
        self.extract_button = QPushButton("Verifikasi / Ekstrak")
        self.extract_button.clicked.connect(self.extract_selected)
        self.extract_button.setVisible(self._role == "admin")
        self.metadata_view = QLabel("Metadata hasil ekstraksi tampil di sini.")
        self.metadata_view.setWordWrap(True)
        self.status_label = QLabel()
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)

        form = QFormLayout()
        form.addRow("ID korban", self.victim_id_input)
        form.addRow("ID posko", self.posko_id_input)
        form.addRow("Koordinat", self.coordinates_input)
        form.addRow("Keterangan", self.caption_input)
        actions = QHBoxLayout()
        if self._role == "relawan":
            actions.addWidget(self.choose_photo_button)
            actions.addWidget(self.upload_button)
        actions.addWidget(self.extract_button)
        actions.addStretch()
        actions.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Dokumentasi Foto Steganografi"))
        if self._role == "relawan":
            layout.addLayout(form)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        layout.addWidget(QLabel("Metadata terverifikasi"))
        layout.addWidget(self.metadata_view)
        layout.addWidget(self.status_label)
        self.refresh()

    def choose_photo(self) -> None:
        """Pilih sumber foto; penyisipan baru dimulai setelah konfirmasi."""
        if not self._authorized("relawan"):
            return
        source, _ = QFileDialog.getOpenFileName(
            self, "Pilih foto", "", "Gambar (*.png *.jpg *.jpeg *.bmp)"
        )
        if source:
            self._selected_image_path = Path(source)
            self.upload_button.setEnabled(True)
            self.status_label.setText(
                f"Foto dipilih: {self._selected_image_path.name}"
            )

    def embed_selected_photo(self) -> None:
        """Jalankan penyisipan untuk gambar yang telah dipilih."""
        if self._selected_image_path is None:
            QMessageBox.information(self, "Sisipkan foto", "Pilih foto terlebih dahulu.")
            return
        self.embed_photo(self._selected_image_path)

    def embed_photo(self, source_path: Path) -> None:
        """Enkripsi metadata lalu sisipkan ke file PNG baru bernama UUID."""
        if not self._authorized("relawan"):
            return
        if self._worker is not None:
            return
        if not source_path.is_file():
            QMessageBox.critical(self, "Gagal menyisipkan foto", "File foto tidak ditemukan.")
            return
        try:
            victim_id = self._optional_id(self.victim_id_input.text(), "korban")
            posko_id = self._optional_id(self.posko_id_input.text(), "posko")
            if victim_id is None and posko_id is None:
                raise ValueError("Isi ID korban atau ID posko.")
            caption = self.caption_input.text().strip()
            payload = {
                "victim_id": victim_id,
                "posko_id": posko_id,
                "coordinates": self.coordinates_input.text().strip() or None,
                "timestamp": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "officer_id": self._user_id,
                "keterangan": caption,
            }
            stego_key = session.get_derived_key(config.HKDF_LABEL_STEGO)
            config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
            output_path = config.STORAGE_DIR / f"{uuid.uuid4().hex}.png"
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Gagal menyiapkan foto", str(exc))
            return

        self._pending_metadata = {
            "victim_id": victim_id,
            "posko_id": posko_id,
            "keterangan": caption,
        }
        self._pending_output = output_path
        self.choose_photo_button.setEnabled(False)
        self.upload_button.setEnabled(False)
        worker = PhotoEmbedWorker(
            source_path, output_path, payload, stego_key, self
        )
        worker.finished.connect(self._embed_finished)
        self._worker = worker
        worker.start()

    @staticmethod
    def _optional_id(value: str, label: str) -> int | None:
        if not value.strip():
            return None
        try:
            parsed = int(value)
        except ValueError as exc:
            raise ValueError(f"ID {label} harus berupa bilangan bulat.") from exc
        if parsed <= 0:
            raise ValueError(f"ID {label} harus lebih besar dari nol.")
        return parsed

    def _embed_finished(self) -> None:
        worker = self._worker
        if worker is None:
            raise RuntimeError("Worker penyisipan foto tidak tersedia.")
        if self._cancelled:
            worker.deleteLater()
            if self._pending_output is not None:
                self._pending_output.unlink(missing_ok=True)
            self._worker = None
            self._pending_output = None
            self._pending_metadata = None
            return
        output = worker.output
        image_hash = worker.image_hash
        warning = worker.warning
        error = worker.error
        self._worker = None
        self.choose_photo_button.setEnabled(True)
        self.upload_button.setEnabled(self._selected_image_path is not None)
        worker.deleteLater()
        metadata = self._pending_metadata
        output_path = self._pending_output
        self._pending_metadata = None
        self._pending_output = None
        if error:
            self.status_label.setText(error)
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            QMessageBox.critical(self, "Gagal menyisipkan foto", error)
            return
        if metadata is None:
            raise RuntimeError("Metadata foto tidak tersedia setelah penyisipan.")
        if not self._authorized("relawan"):
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            return
        try:
            secure_store.save_photo(
                self._conn,
                user_id=self._user_id,
                victim_id=metadata["victim_id"],
                posko_id=metadata["posko_id"],
                image_path=Path(output).name,
                original_hash=image_hash,
                keterangan=str(metadata["keterangan"]),
            )
        except (PermissionError, sqlite3.Error, ValueError) as exc:
            Path(output).unlink(missing_ok=True)
            QMessageBox.critical(self, "Gagal menyimpan foto", str(exc))
            return
        self.refresh()
        self.status_label.setText(
            "Foto disisipkan dan disimpan sebagai PNG."
            + (f" {warning}" if warning else "")
        )

    def refresh(self) -> None:
        """Muat galeri sesuai peran; relawan hanya melihat unggahannya."""
        if not self._authorized():
            return
        self._photos = [
            dict(row)
            for row in secure_store.list_photos(
                self._conn, self._user_id, self._role
            )
        ]
        self.table.setRowCount(0)
        for photo in self._photos:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                photo["id"],
                photo.get("victim_id") or "-",
                photo.get("posko_id") or "-",
                photo.get("keterangan") or "",
                photo.get("created_at") or "",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()

    def extract_selected(self) -> None:
        """Admin mengekstrak LSB dan memverifikasi tag AES-GCM metadata."""
        if not self._authorized("admin"):
            return
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Ekstrak foto", "Pilih foto terlebih dahulu.")
            return
        photo_id = int(self.table.item(row, 0).text())
        photo = next(item for item in self._photos if item["id"] == photo_id)
        try:
            image_path = self._stored_image_path(str(photo["image_path"]))
            encrypted_payload = stego_lsb.extract(str(image_path))
            raw_payload = aes_module.decrypt(
                encrypted_payload,
                session.get_derived_key(config.HKDF_LABEL_STEGO),
            )
            metadata = json.loads(raw_payload.decode("utf-8"))
            if metadata.get("original_sha256") != photo["original_hash"]:
                raise ValueError("Hash foto tidak cocok dengan catatan database.")
        except (InvalidTag, OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            message = f"Foto rusak, diubah, atau metadata tidak valid: {exc}"
            self.status_label.setText(message)
            QMessageBox.warning(self, "Verifikasi foto gagal", message)
            return
        self.metadata_view.setText(
            json.dumps(metadata, ensure_ascii=False, indent=2)
        )
        self.status_label.setText("Foto dan metadata berhasil diverifikasi.")

    @staticmethod
    def _stored_image_path(filename: str) -> Path:
        """Batasi path galeri ke nama file langsung di storage organisasi."""
        relative = Path(filename)
        root = config.STORAGE_DIR.resolve()
        candidate = (root / relative).resolve()
        if relative.is_absolute() or len(relative.parts) != 1 or candidate.parent != root:
            raise ValueError("Path foto di database tidak valid.")
        return candidate

    def stop_worker(self, *, cancel_pending: bool = False) -> None:
        """Tunggu penyisipan yang sedang berjalan sebelum jendela ditutup."""
        self._cancelled = cancel_pending
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        if cancel_pending and self._pending_output is not None:
            self._pending_output.unlink(missing_ok=True)
            self._pending_output = None

    def _authorized(self, required_role: str | None = None) -> bool:
        """Tolak aksi jika akun diblokir atau role sesi berubah."""
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

    def clear_sensitive_state(self) -> None:
        """Clear extracted photo metadata and cached gallery rows."""
        self.metadata_view.clear()
        self._photos.clear()
        self.table.setRowCount(0)
