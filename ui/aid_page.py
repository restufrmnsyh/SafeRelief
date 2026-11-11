"""Riwayat dan pencatatan distribusi bantuan berbasis blockchain lokal."""

import sqlite3
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
from database import secure_store


class AidPage(QWidget):
    """Admin mencatat bantuan dan demo tampering; relawan melihat riwayat."""

    dashboard_requested = Signal()
    _columns = ("Index", "Waktu", "Jenis", "Jumlah", "Dari", "Ke", "Petugas", "Hash")

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        self._user = session.get_current_user()
        self._user_id = int(self._user["id"])
        self._role = str(self._user["role"])
        if self._role not in ("admin", "relawan"):
            raise PermissionError("Peran ini tidak diizinkan melihat riwayat bantuan.")

        self.setStyleSheet(
            "QWidget { background: #edf5fb; color: #1E2A39; }"
            "QLabel { color: #1E2A39; }"
            "QTableWidget, QLineEdit, QSpinBox, QComboBox { background: #f9fcff; border: 1px solid #dfeaf5; border-radius: 10px; }"
            "QPushButton { background-color: #ffffff; color: #1E2A39; border: 1px solid #dfeaf5; border-radius: 12px; padding: 8px 12px; font-weight: 700; }"
            "QPushButton:hover { background-color: #eef7ff; border-color: #bfdcf0; }"
        )

        self.table = QTableWidget(0, len(self._columns))
        self.table.setHorizontalHeaderLabels(self._columns)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.type_input = QLineEdit()
        self.type_input.setPlaceholderText("Contoh: beras")
        self.amount_input = QSpinBox()
        self.amount_input.setRange(1, 1_000_000_000)
        self.amount_input.setValue(1)
        self.from_input = QLineEdit()
        self.to_input = QLineEdit()
        self.officer_input = QLineEdit(
            str(self._user.get("nama_lengkap") or self._user.get("username") or "")
        )
        self.officer_input.setReadOnly(True)
        self.record_button = QPushButton("Catat Bantuan")
        self.record_button.clicked.connect(self.record_distribution)
        self.validate_button = QPushButton("Validasi Chain")
        self.validate_button.clicked.connect(self.validate_chain)
        self.tamper_button = QPushButton("DEMO — Simulasi Tampering")
        self.tamper_button.setToolTip(
            "Mengubah jumlah satu block di database untuk memperlihatkan validasi gagal."
        )
        self.tamper_button.clicked.connect(self.simulate_tampering)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        self.logout_button = QPushButton("Logout")
        self.logout_button.clicked.connect(self._confirm_logout)

        self.form = QWidget()
        form_layout = QFormLayout(self.form)
        form_layout.addRow("Jenis bantuan", self.type_input)
        form_layout.addRow("Jumlah", self.amount_input)
        form_layout.addRow("Dari", self.from_input)
        form_layout.addRow("Ke", self.to_input)
        form_layout.addRow("Petugas", self.officer_input)
        form_layout.addRow(self.record_button)
        self.form.setVisible(self._role == "admin")
        self.tamper_button.setVisible(self._role == "admin")

        actions = QHBoxLayout()
        actions.addWidget(self.validate_button)
        actions.addWidget(self.tamper_button)
        actions.addStretch()
        actions.addWidget(self.back_button)
        actions.addWidget(self.logout_button)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Distribusi Bantuan — Blockchain"))
        if self._role == "relawan":
            layout.addWidget(QLabel("Riwayat bantuan (hanya baca)"))
        layout.addWidget(self.form)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        self.refresh()

    def _confirm_logout(self) -> None:
        """Minta konfirmasi sebelum logout dari halaman bantuan."""
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
            window._end_session("Logout manual dari halaman distribusi bantuan.")

    def refresh(self) -> None:
        """Tampilkan chain tersimpan; muat ulang dari DB setelah setiap aksi."""
        chain = secure_store.get_aid_chain(
            self._conn, self._user_id, self._role
        )
        self.table.setRowCount(0)
        for block in chain.chain:
            data = block.data
            row = self.table.rowCount()
            self.table.insertRow(row)
            timestamp = datetime.fromtimestamp(
                block.timestamp / 1000
            ).astimezone().isoformat(timespec="seconds")
            values = (
                block.index,
                timestamp,
                data.get("jenis", ""),
                data.get("jumlah", ""),
                data.get("dari", ""),
                data.get("ke", ""),
                data.get("petugas", ""),
                block.hash,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, block.index)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def record_distribution(self) -> None:
        """Validasi form lalu append block hanya melalui secure_store."""
        if self._role != "admin":
            raise PermissionError("Hanya admin yang dapat mencatat distribusi.")
        data = {
            "jenis": self.type_input.text().strip(),
            "jumlah": self.amount_input.value(),
            "dari": self.from_input.text().strip(),
            "ke": self.to_input.text().strip(),
            "petugas": self.officer_input.text().strip(),
        }
        if not data["jenis"] or not data["dari"] or not data["ke"]:
            QMessageBox.warning(
                self, "Data belum lengkap", "Jenis, Dari, dan Ke wajib diisi."
            )
            return
        try:
            secure_store.append_aid_block(
                self._conn, self._user_id, data
            )
        except (PermissionError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Gagal mencatat bantuan", str(exc))
            return
        self.type_input.clear()
        self.from_input.clear()
        self.to_input.clear()
        self.refresh()
        valid, broken_index = self.validate_chain()
        if valid:
            self.status_label.setText(
                "Distribusi tercatat. Validasi chain berhasil."
            )
        else:
            self.status_label.setText(
                f"Distribusi tercatat, tetapi block index {broken_index} rusak."
            )

    def validate_chain(self) -> tuple[bool, int | None]:
        """Tampilkan hasil pemeriksaan integritas seluruh chain."""
        chain = secure_store.get_aid_chain(
            self._conn, self._user_id, self._role
        )
        valid, broken_index = chain.is_valid()
        if valid:
            message = "Validasi berhasil: chain valid."
        else:
            message = f"Validasi gagal: block index {broken_index} rusak."
        self.status_label.setText(message)
        return valid, broken_index

    def simulate_tampering(self) -> None:
        """Minta konfirmasi eksplisit sebelum mengubah block untuk demo."""
        if self._role != "admin":
            raise PermissionError("Simulasi tampering hanya tersedia untuk admin.")
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(
                self, "Simulasi Tampering", "Pilih block distribusi terlebih dahulu."
            )
            return
        block_index = int(
            self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        )
        if block_index == 0:
            QMessageBox.warning(
                self,
                "Simulasi Tampering",
                "Genesis block tidak dapat dipilih untuk demo.",
            )
            return
        answer = QMessageBox.question(
            self,
            "DEMO — Simulasi Tampering",
            f"Ubah jumlah pada block {block_index} di database? "
            "Chain akan menjadi tidak valid.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            secure_store.simulate_aid_tampering(
                self._conn, self._user_id, block_index
            )
        except (PermissionError, ValueError, sqlite3.Error) as exc:
            QMessageBox.critical(self, "Simulasi gagal", str(exc))
            return
        self.refresh()
        self.validate_chain()
