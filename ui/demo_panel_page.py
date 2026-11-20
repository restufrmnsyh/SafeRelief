"""Panel demonstrasi plaintext dan ciphertext untuk korban atau pesan chat."""

import base64
import re
import sqlite3

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
from auth import session
from database import db, secure_store


FIELD_NAMES = {
    "nama_lengkap": "Nama lengkap", "nik": "NIK", "alamat_asal": "Alamat asal",
    "kondisi_medis": "Kondisi medis", "kontak_keluarga": "Kontak keluarga",
    "catatan": "Catatan", "id": "ID", "kode_korban": "Kode korban",
    "nama_panggilan": "Nama panggilan", "usia": "Usia", "gender": "Jenis kelamin",
    "posko_id": "ID posko", "status": "Status", "created_by": "ID pencatat",
    "created_at": "Waktu pencatatan", "updated_at": "Terakhir diperbarui",
    "sender_id": "ID pengirim", "receiver_id": "ID penerima",
}


class ValueDelegate(QStyledItemDelegate):
    """Izinkan Qt membungkus token panjang tanpa mengubah nilai yang disalin."""

    def initStyleOption(self, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().initStyleOption(option, index)
        if index.column() == 1:
            option.text = "\u200b".join(option.text[i:i + 4] for i in range(0, len(option.text), 4))
        elif index.column() == 2:
            option.text = re.sub(r"(\S{8})(?=\S{4})", r"\1" + "\u200b", option.text)

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        # Tinggi baris mengikuti ruang teks setelah padding stylesheet dikurangi.
        if index.column() and option.widget is not None and option.rect.width() > 0:
            option = QStyleOptionViewItem(option)
            text_rect = option.widget.style().subElementRect(
                QStyle.SubElement.SE_ItemViewItemText, option, option.widget
            )
            option.rect.setWidth(max(1, text_rect.width()))
        return super().sizeHint(option, index)


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
        self.comparison = QTableWidget(0, 3)
        self.comparison.setAccessibleName("Perbandingan ciphertext dan hasil dekripsi")
        self.comparison.setHorizontalHeaderLabels(["Kolom", "Ciphertext (Base64)", "Hasil dekripsi"])
        self.comparison.setItemDelegate(ValueDelegate(self.comparison))
        self.comparison.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.comparison.setAlternatingRowColors(True)
        self.comparison.setShowGrid(False)
        self.comparison.setMinimumHeight(220)
        header = self.comparison.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in (1, 2):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        self.comparison.verticalHeader().hide()
        self.comparison.verticalHeader().setMinimumSectionSize(42)
        self.comparison.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.sectionResized.connect(self.comparison.resizeRowsToContents)
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        self.details_button = QPushButton("Rincian catatan")
        self.details_button.setCheckable(True)
        self.details = QLabel()
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.details_button.toggled.connect(self._toggle_details)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self._confirm_logout)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Panel Demo — Ciphertext vs Plaintext"))
        filters = QHBoxLayout()
        filters.addWidget(self.record_type, 1)
        filters.addWidget(self.record_input, 2)
        layout.addLayout(filters)
        layout.addWidget(self.notice)
        layout.addWidget(self.comparison, 1)
        layout.addWidget(self.details_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.details)
        layout.addWidget(self.back_button)
        layout.addWidget(self.logout_button)
        self.refresh_records()

    def _confirm_logout(self) -> None:
        """Minta konfirmasi sebelum logout dari panel demo."""
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
            window._end_session("Logout manual dari panel demo.")

    def refresh_records(self, *_signal_args: object) -> None:
        """Muat daftar metadata yang diizinkan; data terenkripsi dibaca saat pilih."""
        self.clear_sensitive_state()
        if not self._authorized():
            return
        kind = str(self.record_type.currentData())
        self.record_input.blockSignals(True)
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
        if self.record_input.count():
            self.show_selected()
        else:
            self._reset_comparison("Belum ada data korban." if kind == "victims" else "Belum ada pesan chat.")

    def show_selected(self, *_signal_args: object) -> None:
        """Pasangkan setiap nilai hasil dekripsi dengan BLOB dari kolom yang sama."""
        self._reset_comparison()
        if not self._authorized():
            return
        record_id = self.record_input.currentData()
        if record_id is None:
            return
        kind = str(self.record_type.currentData())
        try:
            if kind == "victims":
                blobs = secure_store.get_victim_ciphertext(self._conn, self._user_id, int(record_id))
                plaintext = secure_store.get_victim(
                    self._conn,
                    session.get_derived_key(config.HKDF_LABEL_DB),
                    int(record_id),
                )
                if blobs is None or plaintext is None:
                    raise ValueError("Data korban tidak ditemukan.")
                for field, blob in blobs.items():
                    self._add_comparison(FIELD_NAMES[field], blob, plaintext[field])
                metadata = {key: value for key, value in plaintext.items() if key not in blobs}
            else:
                raw_row = db.get_message_by_id(self._conn, int(record_id))
                if raw_row is None:
                    raise ValueError("Pesan tidak ditemukan.")
                plaintext = secure_store.decrypt_demo_message(
                    self._conn,
                    self._user_id,
                    int(record_id),
                    vigenere_key=session.get_vigenere_key(),
                    vernam_enc_key=session.get_derived_key(
                        config.HKDF_LABEL_CHAT_ENC
                    ),
                    vernam_mac_key=session.get_derived_key(
                        config.HKDF_LABEL_CHAT_MAC
                    ),
                )
                self._add_comparison("Isi pesan", raw_row["ciphertext"], plaintext)
                metadata = {key: raw_row[key] for key in ("id", "sender_id", "receiver_id", "created_at")}
            self.details.setText("\n".join(
                f"{FIELD_NAMES[key]}: {value if value is not None else '—'}"
                for key, value in metadata.items()
            ))
            self.comparison.show()
            self.details_button.show()
        except (
            InvalidTag,
            PermissionError,
            RuntimeError,
            ValueError,
            sqlite3.Error,
        ) as exc:
            self._reset_comparison("Perbandingan data tidak dapat ditampilkan.")
            QMessageBox.warning(self, "Panel Demo", str(exc))

    def _add_comparison(self, label: str, blob: bytes | None, plaintext: str | None) -> None:
        row = self.comparison.rowCount()
        self.comparison.insertRow(row)
        encoded = base64.b64encode(blob).decode("ascii") if blob is not None else "—"
        for column, value in enumerate((label, encoded, plaintext if plaintext is not None else "—")):
            item = QTableWidgetItem(value)
            if column == 1:
                item.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
            self.comparison.setItem(row, column, item)

    def _toggle_details(self, expanded: bool) -> None:
        self.details.setVisible(expanded)
        self.details_button.setText("Tutup rincian" if expanded else "Rincian catatan")

    def _reset_comparison(self, message: str = "") -> None:
        self.comparison.setRowCount(0)
        self.comparison.hide()
        self.details_button.setChecked(False)
        self.details_button.hide()
        self.details.clear()
        self.details.hide()
        self.notice.setText(message)
        self.notice.setVisible(bool(message))

    def clear_sensitive_state(self) -> None:
        """Kosongkan nilai dan pilihan catatan saat sesi admin berakhir."""
        self._reset_comparison()
        blocked = self.record_input.blockSignals(True)
        try:
            self.record_input.clear()
        finally:
            self.record_input.blockSignals(blocked)

    def _authorized(self) -> bool:
        """Panel ciphertext/plaintext hanya boleh dipakai admin aktif."""
        try:
            current = session.get_current_user()
            if int(current["id"]) != self._user_id:
                raise PermissionError("Sesi pengguna telah berubah.")
            secure_store.require_active_user(
                self._conn, self._user_id, "admin"
            )
            return True
        except (RuntimeError, PermissionError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Akses ditolak", str(exc))
            return False
