"""Halaman admin untuk membuat, mengedit, dan menghapus posko."""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
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

from auth import session
from database import db, secure_store


class PoskoFormDialog(QDialog):
    """Dialog tambah/edit posko yang sederhana dan jelas untuk admin."""

    def __init__(
        self,
        posko: dict | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tambah Posko" if posko is None else "Edit Posko")
        self.name_input = QLineEdit()
        self.location_input = QLineEdit()
        self.capacity_input = QSpinBox()
        self.capacity_input.setRange(0, 1000000)

        form = QFormLayout(self)
        form.addRow("Nama posko", self.name_input)
        form.addRow("Lokasi", self.location_input)
        form.addRow("Kapasitas", self.capacity_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if posko is not None:
            self.name_input.setText(str(posko.get("nama") or ""))
            self.location_input.setText(str(posko.get("lokasi") or ""))
            self.capacity_input.setValue(int(posko.get("kapasitas") or 0))

    def values(self) -> dict[str, object]:
        name = self.name_input.text().strip()
        location = self.location_input.text().strip()
        if not name or not location:
            raise ValueError("Nama posko dan lokasi wajib diisi.")
        return {
            "nama": name,
            "lokasi": location,
            "kapasitas": int(self.capacity_input.value()),
        }


class PoskoManagementPage(QWidget):
    """Kelola posko admin, termasuk hitung pengguna/korban yang terikat."""

    dashboard_requested = Signal()

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        user = session.get_current_user()
        if user.get("role") != "admin":
            raise PermissionError("Halaman ini hanya untuk admin.")
        secure_store.require_active_user(
            self._conn, int(user["id"]), str(user["role"])
        )
        self._last_deleted_id: int | None = None

        self.setStyleSheet(
            "QWidget { background: #edf5fb; color: #1E2A39; }"
            "QLabel { color: #1E2A39; }"
            "QTableWidget, QLineEdit, QSpinBox, QComboBox { background: #f9fcff; border: 1px solid #dfeaf5; border-radius: 10px; }"
            "QPushButton { background-color: #ffffff; color: #1E2A39; border: 1px solid #dfeaf5; border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #eef7ff; border-color: #bfdcf0; }"
        )

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ("Nama", "Lokasi", "Kapasitas", "Korban terkait", "Relawan terkait", "ID")
        )
        self.table.setColumnHidden(5, True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.add_button = QPushButton("Tambah Posko")
        self.add_button.clicked.connect(self.add_posko)
        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.edit_posko)
        self.delete_button = QPushButton("Hapus")
        self.delete_button.clicked.connect(self.delete_posko)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self._confirm_logout)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        actions = QHBoxLayout()
        for button in (
            self.add_button,
            self.edit_button,
            self.delete_button,
        ):
            actions.addWidget(button)
        footer = QHBoxLayout()
        footer.addWidget(self.status_label, stretch=1)
        footer.addWidget(self.back_button)
        footer.addWidget(self.logout_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Manajemen Posko"))
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(actions)
        layout.addLayout(footer)
        self.refresh()

    def _confirm_logout(self) -> None:
        """Minta konfirmasi sebelum logout dari halaman posko."""
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
            window._end_session("Logout manual dari halaman posko.")

    def refresh(self) -> None:
        """Muattabel posko dan hitung pengguna/korban yang terikat."""
        try:
            rows = db.list_posko(self._conn)
            self.table.setRowCount(0)
            for posko in rows:
                posko_id = int(posko["id"])
                victim_count = self._conn.execute(
                    "SELECT COUNT(*) FROM victims WHERE posko_id = ?",
                    (posko_id,),
                ).fetchone()[0]
                volunteer_count = self._conn.execute(
                    "SELECT COUNT(*) FROM users WHERE posko_id = ? AND role = 'relawan'",
                    (posko_id,),
                ).fetchone()[0]
                row = self.table.rowCount()
                self.table.insertRow(row)
                values = (
                    posko["nama"],
                    posko["lokasi"],
                    posko["kapasitas"],
                    victim_count,
                    volunteer_count,
                    posko_id,
                )
                for column, value in enumerate(values):
                    self.table.setItem(
                        row,
                        column,
                        QTableWidgetItem("" if value is None else str(value)),
                    )
            self.table.resizeColumnsToContents()
            self.status_label.setText(f"{len(rows)} posko terdaftar.")
        except (sqlite3.Error, PermissionError) as exc:
            self.status_label.setText(str(exc))

    def _selected_posko(self) -> sqlite3.Row | None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self,
                "Manajemen Posko",
                "Pilih posko terlebih dahulu.",
            )
            return None
        posko_id = int(self.table.item(row, 5).text())
        return next(
            (item for item in db.list_posko(self._conn) if int(item["id"]) == posko_id),
            None,
        )

    def add_posko(self) -> None:
        """Tambah posko baru dan tampilkan status singkat di footer."""
        try:
            dialog = PoskoFormDialog(parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            db.insert_posko(self._conn, values)
            self.status_label.setText(
                f"Posko '{values['nama']}' berhasil ditambahkan."
            )
            self.refresh()
        except (PermissionError, ValueError, sqlite3.Error, OSError) as exc:
            QMessageBox.critical(self, "Gagal menambah posko", str(exc))

    def edit_posko(self) -> None:
        """Ubah nama, lokasi, dan kapasitas posko yang terpilih."""
        posko = self._selected_posko()
        if posko is None:
            return
        try:
            dialog = PoskoFormDialog(posko=dict(posko), parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            values = dialog.values()
            db.update_posko(
                self._conn,
                int(posko["id"]),
                {
                    "nama": values["nama"],
                    "lokasi": values["lokasi"],
                    "kapasitas": values["kapasitas"],
                },
            )
            self.status_label.setText(
                f"Posko '{values['nama']}' berhasil diperbarui."
            )
            self.refresh()
        except (PermissionError, ValueError, sqlite3.Error, OSError) as exc:
            QMessageBox.critical(self, "Gagal mengedit posko", str(exc))

    def delete_posko(self) -> None:
        """Hapus posko dengan konfirmasi kalau data masih terikat."""
        posko = self._selected_posko()
        if posko is None:
            return
        posko_id = int(posko["id"])
        victim_count = self._conn.execute(
            "SELECT COUNT(*) FROM victims WHERE posko_id = ?",
            (posko_id,),
        ).fetchone()[0]
        volunteer_count = self._conn.execute(
            "SELECT COUNT(*) FROM users WHERE posko_id = ? AND role = 'relawan'",
            (posko_id,),
        ).fetchone()[0]

        if victim_count or volunteer_count:
            answer = QMessageBox.question(
                self,
                "Konfirmasi hapus posko",
                "Posko ini masih dipakai "
                f"{victim_count} korban dan {volunteer_count} relawan, "
                "melanjutkan akan membuat data mereka jadi 'Tidak ditentukan'. "
                "Lanjutkan?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            self._last_deleted_id = posko_id
            db.delete_posko(self._conn, posko_id)
            self.status_label.setText(f"Posko '{posko['nama']}' berhasil dihapus.")
            self.refresh()
        except (PermissionError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal menghapus posko", str(exc))
