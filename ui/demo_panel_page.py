"""Panel demonstrasi plaintext dan ciphertext untuk korban atau pesan chat."""

import base64
import json
import sqlite3

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
from auth import session
from database import db, secure_store


class DemoPanelPage(QWidget):
    """Bandingkan BLOB ciphertext mentah dan hasil secure_store terdekripsi."""

    dashboard_requested = Signal()

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        user = session.get_current_user()
        self._user_id = int(user["id"])
        if user.get("role") != "admin":
            raise PermissionError("Panel demo hanya dapat dibuka admin.")

        self.record_type = QComboBox()
        self.record_type.addItem("Data korban", "victims")
        self.record_type.addItem("Pesan chat", "messages")
        self.record_type.currentIndexChanged.connect(self.refresh_records)
        self.record_input = QComboBox()
        self.record_input.currentIndexChanged.connect(self.show_selected)
        self.raw_view = QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setPlaceholderText("Ciphertext mentah dari database.db.")
        self.plaintext_view = QPlainTextEdit()
        self.plaintext_view.setReadOnly(True)
        self.plaintext_view.setPlaceholderText(
            "Plaintext terdekripsi dari secure_store."
        )
        columns = QHBoxLayout()
        raw_column = QVBoxLayout()
        raw_column.addWidget(QLabel("Ciphertext mentah"))
        raw_column.addWidget(self.raw_view)
        plain_column = QVBoxLayout()
        plain_column.addWidget(QLabel("Hasil dekripsi"))
        plain_column.addWidget(self.plaintext_view)
        columns.addLayout(raw_column)
        columns.addLayout(plain_column)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Panel Demo — Ciphertext vs Plaintext"))
        layout.addWidget(self.record_type)
        layout.addWidget(self.record_input)
        layout.addLayout(columns, 1)
        layout.addWidget(self.back_button)
        self.refresh_records()

    def refresh_records(self, *_signal_args: object) -> None:
        """Muat daftar metadata yang diizinkan; data terenkripsi dibaca saat pilih."""
        kind = str(self.record_type.currentData())
        self.record_input.blockSignals(True)
        self.record_input.clear()
        if kind == "victims":
            rows = secure_store.list_demo_victims(
                self._conn, self._user_id
            )
            for victim in rows:
                self.record_input.addItem(
                    f"{victim['kode_korban']} — {victim['nama_panggilan'] or ''}",
                    int(victim["id"]),
                )
        else:
            rows = secure_store.list_demo_messages(
                self._conn, self._user_id
            )
            for message in rows:
                self.record_input.addItem(
                    f"Pesan #{message['id']} — {message['created_at']}",
                    int(message["id"]),
                )
        self.record_input.blockSignals(False)
        self.raw_view.clear()
        self.plaintext_view.clear()
        if self.record_input.count():
            self.show_selected()

    def show_selected(self, *_signal_args: object) -> None:
        """Baca raw row melalui db.py dan plaintext melalui secure_store."""
        record_id = self.record_input.currentData()
        if record_id is None:
            self.raw_view.setPlainText("Tidak ada record untuk ditampilkan.")
            self.plaintext_view.clear()
            return
        kind = str(self.record_type.currentData())
        try:
            if kind == "victims":
                raw_row = db.get_victim_by_id(self._conn, int(record_id))
                if raw_row is None:
                    raise ValueError("Data korban tidak ditemukan.")
                raw_fields = {
                    field: (
                        base64.b64encode(bytes(raw_row[f"{field}_enc"])).decode(
                            "ascii"
                        )
                        if raw_row[f"{field}_enc"] is not None
                        else None
                    )
                    for field in (
                        "nama_lengkap",
                        "nik",
                        "alamat_asal",
                        "kondisi_medis",
                        "kontak_keluarga",
                        "catatan",
                    )
                }
                raw_fields["kode_korban"] = raw_row["kode_korban"]
                raw_fields["nama_panggilan"] = raw_row["nama_panggilan"]
                plaintext = secure_store.get_victim(
                    self._conn,
                    session.get_derived_key(config.HKDF_LABEL_DB),
                    int(record_id),
                )
            else:
                raw_row = db.get_message_by_id(self._conn, int(record_id))
                if raw_row is None:
                    raise ValueError("Pesan tidak ditemukan.")
                raw_fields = {
                    "id": raw_row["id"],
                    "sender_id": raw_row["sender_id"],
                    "receiver_id": raw_row["receiver_id"],
                    "ciphertext_base64": base64.b64encode(
                        bytes(raw_row["ciphertext"])
                    ).decode("ascii"),
                }
                plaintext = secure_store.decrypt_demo_message(
                    self._conn,
                    self._user_id,
                    int(record_id),
                    vigenere_key=session.get_vigenere_key(),
                    blowfish_enc_key=session.get_derived_key(
                        config.HKDF_LABEL_CHAT_ENC
                    ),
                    blowfish_mac_key=session.get_derived_key(
                        config.HKDF_LABEL_CHAT_MAC
                    ),
                )
            self.raw_view.setPlainText(
                self._format_json(raw_fields)
            )
            self.plaintext_view.setPlainText(
                self._format_json(plaintext) if isinstance(plaintext, dict)
                else str(plaintext)
            )
        except (
            InvalidTag,
            PermissionError,
            RuntimeError,
            ValueError,
            sqlite3.Error,
        ) as exc:
            self.raw_view.setPlainText(f"Gagal membaca ciphertext: {exc}")
            self.plaintext_view.clear()
            QMessageBox.warning(self, "Panel Demo", str(exc))

    @staticmethod
    def _format_json(value: object) -> str:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
