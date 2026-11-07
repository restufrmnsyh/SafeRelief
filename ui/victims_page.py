"""Tampilan data korban dengan daftar plaintext aman dan detail terdekripsi."""

import sqlite3

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
from database import secure_store


STATUSES = ("selamat", "luka ringan", "luka berat", "meninggal", "tidak diketahui")
TABLE_COLUMNS = ("Kode", "Nama panggilan", "Usia", "Status", "Posko")


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
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)

        self.add_button = QPushButton("Tambah")
        self.add_button.clicked.connect(self.add_victim)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_victim)
        self.detail_button = QPushButton("Detail")
        self.detail_button.clicked.connect(self.show_detail)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)

        controls = QHBoxLayout()
        controls.addWidget(self.search_input, stretch=1)
        controls.addWidget(self.status_filter)
        actions = QHBoxLayout()
        actions.addWidget(self.add_button)
        actions.addWidget(self.edit_button)
        actions.addWidget(self.detail_button)
        actions.addStretch()
        actions.addWidget(self.back_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Data Korban"))
        layout.addLayout(controls)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(actions)
        self.refresh()

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

    def _apply_filters(self) -> None:
        if not self._authorized():
            self._victims.clear()
            self.table.setRowCount(0)
            return
        query = self.search_input.text().strip().casefold()
        status = self.status_filter.currentData()
        self.table.setRowCount(0)
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
            values = (
                victim.get("kode_korban"),
                victim.get("nama_panggilan"),
                victim.get("usia"),
                victim.get("status"),
                self._posko_names.get(victim.get("posko_id")),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, victim["id"])
                self.table.setItem(row_index, column, item)
        self.table.resizeColumnsToContents()

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
        detail = secure_store.get_victim(
            self._conn, bytes(self._db_key), int(victim["id"])
        )
        if detail is None:
            QMessageBox.warning(self, "Data Korban", "Data korban tidak ditemukan.")
            self.refresh()
            return

        # Sesuai peran pada rancangan: relawan dapat melihat data untuk
        # koordinasi, sedangkan edit dibatasi pada input relawan itu sendiri.
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
        lines.append(
            f"Posko: {self._posko_names.get(posko_id, '-')}"
        )
        QMessageBox.information(self, "Detail Korban", "\n".join(lines))

    def clear_sensitive_state(self) -> None:
        """Overwrite the cached database key and clear decrypted victim rows."""
        self._db_key[:] = b"\x00" * len(self._db_key)
        self._victims.clear()
        self.table.setRowCount(0)
