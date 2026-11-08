"""Halaman chat admin-relawan dengan ciphertext terlihat sebelum dekripsi."""

import base64
import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from auth import session
from crypto import super_encrypt
from database import db, secure_store


class ChatPage(QWidget):
    """Relawan selalu berbicara dengan admin; admin memilih relawan."""

    dashboard_requested = Signal()

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = session.get_current_user()
        self._user_id = int(self._user["id"])
        self._role = str(self._user["role"])
        if self._role not in ("admin", "relawan"):
            raise PermissionError("Peran ini tidak diizinkan menggunakan chat.")
        self._contacts = secure_store.list_chat_contacts(
            conn, self._user_id, self._role
        )
        self._messages: dict[int, sqlite3.Row] = {}

        self.contact_input = QComboBox()
        for contact in self._contacts:
            label = str(contact.get("nama_lengkap") or contact["username"])
            self.contact_input.addItem(label, int(contact["id"]))

        self.inbox = QListWidget()
        self.inbox.currentItemChanged.connect(self._show_ciphertext)
        self.ciphertext_view = QPlainTextEdit()
        self.ciphertext_view.setReadOnly(True)
        self.ciphertext_view.setPlaceholderText(
            "Ciphertext pesan terpilih akan tampil di sini."
        )
        self.manual_key_input = QLineEdit()
        self.manual_key_input.setPlaceholderText(
            "Gunakan kunci Vigenère manual (opsional untuk demo)"
        )
        self.decrypt_button = QPushButton("Decrypt")
        self.decrypt_button.clicked.connect(self.decrypt_selected)
        self.plaintext_view = QPlainTextEdit()
        self.plaintext_view.setReadOnly(True)
        self.plaintext_view.setPlaceholderText(
            "Teks asli hanya muncul setelah tombol Decrypt."
        )

        self.message_input = QPlainTextEdit()
        self.message_input.setPlaceholderText("Tulis pesan koordinasi...")
        self.message_input.setMaximumHeight(90)
        self.send_button = QPushButton("Kirim")
        self.send_button.clicked.connect(self.send_message)
        self.status_label = QLabel()
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)

        content = QHBoxLayout()
        content.addWidget(self.inbox, 1)
        message_detail = QVBoxLayout()
        message_detail.addWidget(QLabel("Ciphertext (base64)"))
        message_detail.addWidget(self.ciphertext_view)
        message_detail.addWidget(self.manual_key_input)
        message_detail.addWidget(self.decrypt_button)
        message_detail.addWidget(QLabel("Plaintext"))
        message_detail.addWidget(self.plaintext_view)
        content.addLayout(message_detail, 2)

        composer = QHBoxLayout()
        composer.addWidget(self.message_input, 1)
        composer.addWidget(self.send_button)
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, 1)
        footer.addWidget(self.back_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Chat Koordinasi Terenkripsi"))
        layout.addWidget(QLabel("Percakapan"))
        layout.addWidget(self.contact_input)
        layout.addLayout(content, 1)
        layout.addLayout(composer)
        layout.addLayout(footer)
        self.contact_input.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self, *_signal_args: object) -> None:
        """Tampilkan pesan base64 saja dan tandai pesan masuk telah dibaca."""
        if not self._authorized():
            return
        self.inbox.clear()
        self.ciphertext_view.clear()
        self.plaintext_view.clear()
        self._messages.clear()
        if self.contact_input.currentIndex() < 0:
            self.status_label.setText("Belum ada percakapan.")
            return

        contact_id = int(self.contact_input.currentData())
        try:
            secure_store.require_active_user(
                self._conn, contact_id
            )
        except PermissionError as exc:
            QMessageBox.warning(self, "Percakapan tidak tersedia", str(exc))
            return
        db.mark_messages_read(self._conn, self._user_id, contact_id)
        messages = secure_store.get_messages(
            self._conn, self._user_id, contact_id
        )
        users = {
            int(user["id"]): str(user["nama_lengkap"] or user["username"])
            for user in db.list_users(self._conn)
        }
        for message in messages:
            message_id = int(message["id"])
            self._messages[message_id] = message
            sender = users.get(int(message["sender_id"]), "Pengguna")
            encoded = base64.b64encode(bytes(message["ciphertext"])).decode(
                "ascii"
            )
            preview = encoded[:72] + ("..." if len(encoded) > 72 else "")
            timestamp = str(message["created_at"])
            item = QListWidgetItem(f"{timestamp} | {sender} | {preview}")
            item.setData(Qt.ItemDataRole.UserRole, message_id)
            self.inbox.addItem(item)
        self.status_label.setText(f"{len(messages)} pesan dalam percakapan.")

    def _show_ciphertext(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None = None,
    ) -> None:
        """Pemilihan inbox tetap memperlihatkan ciphertext, bukan teks asli."""
        if not self._authorized():
            self.ciphertext_view.clear()
            self.plaintext_view.clear()
            return
        self.plaintext_view.clear()
        if current is None:
            self.ciphertext_view.clear()
            return
        message_id = int(current.data(Qt.ItemDataRole.UserRole))
        message = self._messages[message_id]
        encoded = base64.b64encode(bytes(message["ciphertext"])).decode(
            "ascii"
        )
        self.ciphertext_view.setPlainText(encoded)

    def _authorized(self) -> bool:
        """Periksa ulang sesi dan role sebelum aksi dari widget yang terbuka."""
        try:
            current = session.get_current_user()
            if int(current["id"]) != self._user_id:
                raise PermissionError("Sesi pengguna telah berubah.")
            secure_store.require_active_user(
                self._conn, self._user_id, self._role
            )
            return True
        except (RuntimeError, PermissionError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Akses ditolak", str(exc))
            return False

    def send_message(self) -> None:
        """Enkripsi dan simpan pesan hanya untuk pasangan admin-relawan."""
        if not self._authorized():
            return
        text = self.message_input.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "Chat", "Isi pesan terlebih dahulu.")
            return
        if len(text.encode("utf-8")) > config.VERNAM_MAX_MESSAGE_BYTES:
            QMessageBox.warning(
                self,
                "Pesan terlalu panjang",
                "Pesan melebihi batas Vernam 8160 byte setelah UTF-8 encode. "
                "Kurangi panjang pesan sebelum mengirim.",
            )
            return
        if self.contact_input.currentIndex() < 0:
            QMessageBox.information(self, "Chat", "Tidak ada penerima.")
            return
        contact_id = int(self.contact_input.currentData())
        try:
            encrypted = super_encrypt.encrypt(
                text,
                session.get_vigenere_key(),
                session.get_derived_key(config.HKDF_LABEL_CHAT_ENC),
                session.get_derived_key(config.HKDF_LABEL_CHAT_MAC),
            )
            secure_store.save_message(
                self._conn, self._user_id, contact_id, encrypted
            )
        except (PermissionError, RuntimeError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Pesan tidak terkirim", str(exc))
            return

        self.message_input.clear()
        self.refresh()
        self.status_label.setText("Pesan terenkripsi berhasil dikirim.")

    def decrypt_selected(self) -> None:
        """Dekripsi hanya setelah permintaan eksplisit; kunci manual untuk demo."""
        if not self._authorized():
            return
        item = self.inbox.currentItem()
        if item is None:
            QMessageBox.information(self, "Decrypt", "Pilih pesan terlebih dahulu.")
            return
        message_id = int(item.data(Qt.ItemDataRole.UserRole))
        message = self._messages[message_id]
        try:
            manual_key = self.manual_key_input.text()
            vigenere_key = manual_key or session.get_vigenere_key()
            plaintext = super_encrypt.decrypt(
                bytes(message["ciphertext"]),
                vigenere_key,
                session.get_derived_key(config.HKDF_LABEL_CHAT_ENC),
                session.get_derived_key(config.HKDF_LABEL_CHAT_MAC),
            )
        except (PermissionError, RuntimeError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(
                self, "Gagal mendekripsi", f"Pesan tidak dapat dibuka: {exc}"
            )
            return
        self.plaintext_view.setPlainText(plaintext)

    def clear_sensitive_state(self) -> None:
        """Clear plaintext and cached conversation records when session ends."""
        self._messages.clear()
        self.inbox.clear()
        self.ciphertext_view.clear()
        self.plaintext_view.clear()
        self.message_input.clear()
