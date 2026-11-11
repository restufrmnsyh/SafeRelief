"""Tampilan data korban dengan daftar plaintext aman dan detail terdekripsi."""

import base64
import sqlite3

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import config
from auth import session
from database import db, secure_store


STATUSES = ("selamat", "luka ringan", "luka berat", "meninggal", "tidak diketahui")
TABLE_COLUMNS = ("Kode", "Nama panggilan", "Usia", "Status", "Posko", "Aksi")


class VictimFormDialog(QDialog):
    """Form tambah/edit; secure_store mengenkripsi kolom sensitif."""

    def __init__(
        self,
        poskoes: list[dict],
        victim: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Data Korban" if victim else "Tambah Korban")
        self.code_input = QLineEdit()
        self.nickname_input = QLineEdit()
        self.age_input = QSpinBox()
        self.age_input.setRange(0, 130)
        self.gender_input = QComboBox()
        self.gender_input.addItem("Tidak diisi", None)
        self.gender_input.addItem("Laki-laki", "L")
        self.gender_input.addItem("Perempuan", "P")
        self.status_input = QComboBox()
        self.status_input.addItems(STATUSES)
        self.post_input = QComboBox()
        self.post_input.addItem("Tidak ditentukan", None)
        for post in poskoes:
            self.post_input.addItem(post["nama"], post["id"])

        self.full_name_input = QLineEdit()
        self.nik_input = QLineEdit()
        self.address_input = QLineEdit()
        self.medical_input = QLineEdit()
        self.family_contact_input = QLineEdit()
        self.notes_input = QLineEdit()

        form = QFormLayout(self)
        form.addRow("Kode korban", self.code_input)
        form.addRow("Nama panggilan", self.nickname_input)
        form.addRow("Usia", self.age_input)
        form.addRow("Gender", self.gender_input)
        form.addRow("Status", self.status_input)
        form.addRow("Posko", self.post_input)
        form.addRow("Nama lengkap (terenkripsi)", self.full_name_input)
        form.addRow("NIK (terenkripsi)", self.nik_input)
        form.addRow("Alamat asal (terenkripsi)", self.address_input)
        form.addRow("Kondisi medis (terenkripsi)", self.medical_input)
        form.addRow("Kontak keluarga (terenkripsi)", self.family_contact_input)
        form.addRow("Catatan (terenkripsi)", self.notes_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        if victim:
            self._populate(victim)

    def _populate(self, victim: dict) -> None:
        self.code_input.setText(str(victim.get("kode_korban") or ""))
        self.code_input.setEnabled(False)
        self.nickname_input.setText(str(victim.get("nama_panggilan") or ""))
        self.age_input.setValue(int(victim.get("usia") or 0))
        self.gender_input.setCurrentIndex(
            max(0, self.gender_input.findData(victim.get("gender")))
        )
        self.status_input.setCurrentText(
            str(victim.get("status") or "tidak diketahui")
        )
        self.post_input.setCurrentIndex(
            max(0, self.post_input.findData(victim.get("posko_id")))
        )
        for widget, field in (
            (self.full_name_input, "nama_lengkap"),
            (self.nik_input, "nik"),
            (self.address_input, "alamat_asal"),
            (self.medical_input, "kondisi_medis"),
            (self.family_contact_input, "kontak_keluarga"),
            (self.notes_input, "catatan"),
        ):
            widget.setText(str(victim.get(field) or ""))

    def values(self) -> dict[str, object]:
        code = self.code_input.text().strip()
        if not code:
            raise ValueError("Kode korban wajib diisi.")
        return {
            "kode_korban": code,
            "nama_panggilan": self.nickname_input.text().strip() or None,
            "usia": self.age_input.value() or None,
            "gender": self.gender_input.currentData(),
            "status": self.status_input.currentText(),
            "posko_id": self.post_input.currentData(),
            "nama_lengkap": self.full_name_input.text().strip() or None,
            "nik": self.nik_input.text().strip() or None,
            "alamat_asal": self.address_input.text().strip() or None,
            "kondisi_medis": self.medical_input.text().strip() or None,
            "kontak_keluarga": self.family_contact_input.text().strip() or None,
            "catatan": self.notes_input.text().strip() or None,
        }


class VictimDetailDialog(QDialog):
    """Tampilan detail korban yang menampilkan ciphertext sebelum dekripsi eksplisit."""

    decrypt_requested = Signal()

    def __init__(
        self,
        summary: dict[str, object] | None,
        fields: dict[str, bytes | None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detail Korban")
        self._fields = dict(fields)

        layout = QVBoxLayout(self)
        title = QLabel("Ringkasan korban")
        title.setStyleSheet("font-weight: 700;")
        layout.addWidget(title)

        summary_layout = QFormLayout()
        for label, value in (summary or {}).items():
            summary_layout.addRow(f"{label}:", QLabel(str(value) if value is not None else "-"))
        layout.addLayout(summary_layout)

        sensitive_title = QLabel("Kolom sensitif")
        sensitive_title.setStyleSheet("font-weight: 700;")
        layout.addWidget(sensitive_title)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["Field", "Ciphertext (base64)", "Plaintext"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.setColumnWidth(0, 200)
        table.setColumnWidth(1, 350)
        table.setColumnWidth(2, 250)

        for field_name, blob in self._fields.items():
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(field_name))
            ciphertext = "-" if blob is None else base64.b64encode(blob).decode("ascii")
            table.setItem(row, 1, QTableWidgetItem(ciphertext))
            table.setItem(row, 2, QTableWidgetItem("(terenkripsi)"))

        layout.addWidget(table)
        buttons = QHBoxLayout()
        decrypt_button = QPushButton("Decrypt")
        decrypt_button.clicked.connect(self.decrypt_requested.emit)
        close_button = QPushButton("Tutup")
        close_button.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(decrypt_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self._table = table

    def show_plaintext(self, detail: dict) -> None:
        """Isi kolom plaintext dengan hasil dekripsi yang baru saja diminta."""
        for row in range(self._table.rowCount()):
            field_name = self._table.item(row, 0).text()
            value = detail.get(field_name)
            self._table.setItem(
                row,
                2,
                QTableWidgetItem(str(value) if value is not None else "(terenkripsi)"),
            )

    def clear_plaintext(self) -> None:
        """Kosongkan semua plaintext agar tidak tertinggal setelah logout."""
        for row in range(self._table.rowCount()):
            self._table.setItem(row, 2, QTableWidgetItem("(terenkripsi)"))

    def closeEvent(self, event) -> None:
        """Pastikan plaintext tidak tertinggal saat dialog ditutup."""
        self.clear_plaintext()
        super().closeEvent(event)


class VictimsPage(QWidget):
    """Daftar, cari, filter, tambah/edit, dan lihat detail korban."""

    dashboard_requested = Signal()

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = session.get_current_user()
        self._db_key = bytearray(
            session.get_derived_key(config.HKDF_LABEL_DB)
        )
        self._victims: list[dict] = []
        self._posko_names: dict[int, str] = {}
        self._detail_dialog: VictimDetailDialog | None = None
        self._decrypted_victim_id: int | None = None
        self._is_refreshing_table = False

        self.setStyleSheet(
            "QWidget { background: #edf5fb; color: #1E2A39; }"
            "QLabel { color: #1E2A39; }"
            "QTableWidget, QLineEdit, QSpinBox, QComboBox, QDialog { background: #f9fcff; border: 1px solid #dfeaf5; border-radius: 10px; }"
            "QPushButton { background-color: #ffffff; color: #1E2A39; border: 1px solid #dfeaf5; border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #eef7ff; border-color: #bfdcf0; }"
        )

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cari kode atau nama panggilan")
        self.search_input.textChanged.connect(self._apply_filters)
        self.status_filter = QComboBox()
        self.status_filter.addItem("Semua status", None)
        for status in STATUSES:
            self.status_filter.addItem(status, status)
        self.status_filter.currentIndexChanged.connect(self._apply_filters)

        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setColumnWidth(5, 140)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self.table.currentCellChanged.connect(self._handle_selection_changed)

        self.add_button = QPushButton("Tambah")
        self.add_button.clicked.connect(self.add_victim)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_victim)
        self.detail_button = QPushButton("Detail")
        self.detail_button.clicked.connect(self.show_detail)
        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self.delete_victim)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self._confirm_logout)
        self.edit_button.setEnabled(False)

        controls = QHBoxLayout()
        controls.addWidget(self.search_input, stretch=1)
        controls.addWidget(self.status_filter)
        actions = QHBoxLayout()
        actions.addWidget(self.add_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.detail_button)
        actions.addWidget(self.delete_button)
        actions.addStretch()
        actions.addWidget(self.back_button)
        actions.addWidget(self.logout_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Data Korban"))
        layout.addLayout(controls)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(actions)
        self.refresh()

    def _confirm_logout(self) -> None:
        """Minta konfirmasi sebelum logout dari halaman korban."""
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
            window._end_session("Logout manual dari halaman korban.")

    def refresh(self) -> None:
        """Muat daftar aman plaintext dan label posko."""
        if not self._authorized():
            return
        self._victims = [
            dict(row) for row in secure_store.list_victims(self._conn)
        ]
        self._posko_names = {
            int(row["id"]): str(row["nama"])
            for row in secure_store.list_posko(self._conn)
        }
        self._apply_filters()

    def _on_row_double_clicked(self, row: int, column: int) -> None:
        if row >= 0 and column >= 0:
            self.table.setCurrentCell(row, column)
            self.show_detail()

    def _handle_selection_changed(self, row: int, column: int, previous_row: int, previous_column: int) -> None:
        """Hanya sinkronkan tombol Edit ke row yang aktif; jangan membatalkan status decrypt yang sudah valid."""
        if self._is_refreshing_table:
            return
        victim = self._selected_victim()
        if victim is None:
            self.edit_button.setEnabled(False)
            return
        self._sync_edit_button_state(victim)

    def _sync_edit_button_state(self, victim: dict | None = None) -> None:
        """Admin harus mendekripsi data korban sebelum menu Edit dibuka."""
        if victim is None:
            victim = self._selected_victim()
        if self._user["role"] == "admin":
            enabled = victim is not None and int(victim["id"]) == int(self._decrypted_victim_id or -1)
            self.edit_button.setEnabled(enabled)
            return
        self.edit_button.setEnabled(True)

    def _mask_table_value(self, value: object) -> str:
        """Tampilkan placeholder terenkripsi di daftar admin sampai decrypt dieksekusi."""
        if value is None:
            return "-"
        text = str(value)
        return "[terenkripsi]" if text else "-"

    def _apply_filters(self) -> None:
        if not self._authorized():
            self._victims.clear()
            self.table.setRowCount(0)
            return
        self._is_refreshing_table = True
        query = self.search_input.text().strip().casefold()
        status = self.status_filter.currentData()
        self.table.setRowCount(0)
        try:
            for victim in self._victims:
                if status and victim["status"] != status:
                    continue
                haystack = " ".join(
                    (
                        str(victim.get("kode_korban") or ""),
                        str(victim.get("nama_panggilan") or ""),
                    )
                ).casefold()
                if query and query not in haystack:
                    continue

                row_index = self.table.rowCount()
                self.table.insertRow(row_index)
                is_admin_view = self._user["role"] == "admin"
                is_decrypted = int(victim["id"]) == int(self._decrypted_victim_id or -1)
                values = (
                    victim.get("kode_korban"),
                    victim.get("nama_panggilan"),
                    victim.get("usia"),
                    victim.get("status"),
                    self._posko_names.get(victim.get("posko_id")),
                )
                for column, value in enumerate(values):
                    raw_text = "" if value is None else str(value)
                    if is_admin_view and not is_decrypted:
                        raw_text = self._mask_table_value(value)
                    item = QTableWidgetItem(raw_text)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, victim["id"])
                    self.table.setItem(row_index, column, item)

                action_button = QPushButton("Decrypt" if is_admin_view and not is_decrypted else "Open")
                action_button.setFixedWidth(110)
                action_button.clicked.connect(
                    lambda _checked=False, victim_id=int(victim["id"]): self._decrypt_victim(victim_id)
                )
                self.table.setCellWidget(row_index, 5, action_button)
            self.table.resizeColumnsToContents()
        finally:
            self._is_refreshing_table = False

    def _selected_victim(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Data Korban", "Pilih korban terlebih dahulu.")
            return None
        victim_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next(
            (victim for victim in self._victims if victim["id"] == victim_id),
            None,
        )

    def _can_edit(self, victim: dict) -> bool:
        return self._user["role"] == "admin" or (
            victim.get("created_by") == self._user.get("id")
        )

    def _authorized(self) -> bool:
        """Cegah widget lama menjalankan aksi setelah sesi diblokir/logout."""
        try:
            current = session.get_current_user()
            if int(current["id"]) != int(self._user["id"]):
                raise PermissionError("Sesi pengguna telah berubah.")
            secure_store.require_active_user(
                self._conn, int(self._user["id"]), str(self._user["role"])
            )
            return True
        except (RuntimeError, PermissionError, sqlite3.Error) as exc:
            QMessageBox.warning(self, "Akses ditolak", str(exc))
            return False

    def add_victim(self) -> None:
        if not self._authorized():
            return
        dialog = VictimFormDialog(
            [dict(row) for row in secure_store.list_posko(self._conn)], parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if not self._authorized():
                return
            data = dialog.values()
            data["created_by"] = int(self._user["id"])
            secure_store.add_victim(self._conn, bytes(self._db_key), data)
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal menyimpan korban", str(exc))

    def edit_victim(self) -> None:
        if not self._authorized():
            return
        victim = self._selected_victim()
        if victim is None:
            return
        if self._user["role"] == "admin":
            victim_id = int(victim["id"])
            if self._decrypted_victim_id != victim_id:
                QMessageBox.warning(
                    self,
                    "Edit diblokir",
                    "Data korban harus didekripsi terlebih dahulu sebelum bisa diedit.",
                )
                return
        if not self._can_edit(victim):
            QMessageBox.warning(
                self,
                "Akses ditolak",
                "Relawan hanya dapat mengedit data korban yang diinputnya.",
            )
            return
        detail = secure_store.get_victim(
            self._conn, bytes(self._db_key), int(victim["id"])
        )
        if detail is None:
            QMessageBox.warning(self, "Data Korban", "Data korban tidak ditemukan.")
            self.refresh()
            return
        dialog = VictimFormDialog(
            [dict(row) for row in secure_store.list_posko(self._conn)],
            detail,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            if not self._authorized():
                return
            values = dialog.values()
            values.pop("kode_korban")
            secure_store.update_victim(
                self._conn, bytes(self._db_key), int(victim["id"]), values
            )
            self.refresh()
        except (ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal memperbarui korban", str(exc))

    def show_detail(self) -> None:
        if not self._authorized():
            return
        victim = self._selected_victim()
        if victim is None:
            return

        if self._user["role"] == "admin":
            ciphertext = secure_store.get_victim_ciphertext(
                self._conn, int(self._user["id"]), int(victim["id"])
            )
            if ciphertext is None:
                QMessageBox.warning(self, "Data Korban", "Data korban tidak ditemukan.")
                self.refresh()
                return

            summary = {
                "Kode korban": victim.get("kode_korban"),
                "Nama panggilan": victim.get("nama_panggilan"),
                "Status": victim.get("status"),
                "Posko": self._posko_names.get(victim.get("posko_id")),
            }
            if self._detail_dialog is not None and self._detail_dialog.isVisible():
                self._detail_dialog.close()
            dialog = VictimDetailDialog(summary, ciphertext, parent=self)
            dialog.decrypt_requested.connect(
                lambda victim_id=int(victim["id"]): self._decrypt_victim(victim_id)
            )
            dialog.finished.connect(self._reset_detail_dialog)
            self._detail_dialog = dialog
            self._sync_edit_button_state(victim)
            dialog.open()
            return

        detail = secure_store.get_victim(
            self._conn, bytes(self._db_key), int(victim["id"])
        )
        if detail is None:
            QMessageBox.warning(self, "Data Korban", "Data korban tidak ditemukan.")
            self.refresh()
            return

        fields = (
            ("kode_korban", "Kode"),
            ("nama_panggilan", "Nama panggilan"),
            ("nama_lengkap", "Nama lengkap"),
            ("nik", "NIK"),
            ("alamat_asal", "Alamat asal"),
            ("usia", "Usia"),
            ("gender", "Gender"),
            ("kondisi_medis", "Kondisi medis"),
            ("kontak_keluarga", "Kontak keluarga"),
            ("catatan", "Catatan"),
            ("status", "Status"),
        )
        lines = [
            f"{label}: {detail.get(key) if detail.get(key) is not None else '-'}"
            for key, label in fields
        ]
        posko_id = detail.get("posko_id")
        lines.append(f"Posko: {self._posko_names.get(posko_id, '-')}")
        QMessageBox.information(self, "Detail Korban", "\n".join(lines))

    def delete_victim(self) -> None:
        """Hapus korban permanen dengan konfirmasi admin."""
        if not self._authorized():
            return
        if self._user["role"] != "admin":
            QMessageBox.warning(
                self,
                "Akses ditolak",
                "Hanya admin yang dapat menghapus data korban.",
            )
            return

        victim = self._selected_victim()
        if victim is None:
            return
        kode = str(victim.get("kode_korban") or "-")
        answer = QMessageBox.question(
            self,
            "Konfirmasi hapus korban",
            "Yakin ingin menghapus data korban "
            f"{kode}? Tindakan ini tidak dapat dibatalkan. "
            "Foto dan dokumentasi terkait korban ini (jika ada) juga akan kehilangan referensinya.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            db.delete_victim(self._conn, int(victim["id"]))
            db.log_activity(
                self._conn,
                "DELETE_VICTIM",
                user_id=int(self._user["id"]),
                detail=f"victim_id={victim['id']}; kode_korban={kode}",
            )
            self._decrypted_victim_id = None
            self.status_label = getattr(self, "status_label", None)
            if self.status_label is not None:
                self.status_label.setText(f"Data korban '{kode}' berhasil dihapus.")
            self.refresh()
        except (PermissionError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal menghapus korban", str(exc))

    def _decrypt_victim(self, victim_id: int) -> None:
        """Decrypt detail korban untuk admin hanya saat tombol Decrypt ditekan."""
        if not self._authorized():
            return
        try:
            detail = secure_store.decrypt_victim(
                self._conn,
                bytes(self._db_key),
                int(self._user["id"]),
                int(victim_id),
            )
        except (
            ValueError,
            PermissionError,
            RuntimeError,
            sqlite3.Error,
            InvalidTag,
        ) as exc:
            QMessageBox.critical(self, "Gagal mendekripsi", f"Pesan tidak dapat dibuka: {exc}")
            return
        if detail is None:
            QMessageBox.warning(self, "Data Korban", "Data korban tidak ditemukan.")
            return
        self._decrypted_victim_id = int(victim_id)
        self._sync_edit_button_state({"id": int(victim_id)})
        if self._detail_dialog is not None:
            self._detail_dialog.show_plaintext(detail)
            self._detail_dialog._table.viewport().update()
        self._apply_filters()

    def _reset_detail_dialog(self, *_args) -> None:
        """Hapus referensi dialog, tapi jangan menghapus state decrypt yang sudah valid."""
        dialog = self._detail_dialog
        if dialog is not None:
            dialog.clear_plaintext()
        self._detail_dialog = None
        if self._decrypted_victim_id is None:
            self.edit_button.setEnabled(False)
        else:
            self._sync_edit_button_state({"id": int(self._decrypted_victim_id)})

    def clear_sensitive_state(self) -> None:
        """Tutup dialog detail dan hapus plaintext yang mungkin tersisa saat logout."""
        dialog = self._detail_dialog
        if dialog is not None:
            self._detail_dialog = None
            dialog.reject()
            dialog.clear_plaintext()
        self._decrypted_victim_id = None
        self.edit_button.setEnabled(False)
        self._db_key[:] = b"\x00" * len(self._db_key)
        self._victims.clear()
        self.table.setRowCount(0)
