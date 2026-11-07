"""Halaman admin untuk meninjau dan memfilter log aktivitas terbaru."""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from auth import session
from database import secure_store


class ActivityLogPage(QWidget):
    """Tampilkan audit trail terbaru dengan filter user dan aksi."""

    dashboard_requested = Signal()
    _columns = ("Waktu", "User", "Aksi", "Detail")

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._conn = conn
        user = session.get_current_user()
        if user.get("role") != "admin":
            raise PermissionError("Log aktivitas hanya dapat dilihat admin.")
        self._user_id = int(user["id"])

        self.user_filter = QComboBox()
        self.action_filter = QComboBox()
        self.table = QTableWidget(0, len(self._columns))
        self.table.setHorizontalHeaderLabels(self._columns)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.status_label = QLabel()
        self.back_button = QPushButton("Kembali ke Dashboard")
        self.back_button.clicked.connect(self.dashboard_requested.emit)
        filters = QHBoxLayout()
        filters.addWidget(QLabel("User:"))
        filters.addWidget(self.user_filter)
        filters.addWidget(QLabel("Aksi:"))
        filters.addWidget(self.action_filter)
        filters.addStretch()
        filters.addWidget(self.back_button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Log Aktivitas"))
        layout.addLayout(filters)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status_label)
        self._refresh_filter_options()
        self.user_filter.currentIndexChanged.connect(self.refresh)
        self.action_filter.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def _refresh_filter_options(self) -> None:
        """Perbarui opsi user/aksi saat log baru atau relawan ditambahkan."""
        selected_user = self.user_filter.currentData()
        selected_action = self.action_filter.currentData()
        self.user_filter.blockSignals(True)
        self.action_filter.blockSignals(True)
        self.user_filter.clear()
        self.user_filter.addItem("Semua user", None)
        for user_row in secure_store.list_activity_users(
            self._conn, self._user_id
        ):
            label = str(user_row.get("nama_lengkap") or user_row["username"])
            self.user_filter.addItem(
                f"{label} ({user_row['username']})", int(user_row["id"])
            )
        self.action_filter.clear()
        self.action_filter.addItem("Semua aksi", None)
        for action in secure_store.list_activity_actions(
            self._conn, self._user_id
        ):
            self.action_filter.addItem(action, action)
        if selected_user is not None:
            index = self.user_filter.findData(selected_user)
            if index >= 0:
                self.user_filter.setCurrentIndex(index)
        if selected_action is not None:
            index = self.action_filter.findData(selected_action)
            if index >= 0:
                self.action_filter.setCurrentIndex(index)
        self.user_filter.blockSignals(False)
        self.action_filter.blockSignals(False)

    def refresh(self, *_signal_args: object) -> None:
        """Muat maksimal 500 entri terbaru dengan filter yang dipilih."""
        self._refresh_filter_options()
        selected_user = self.user_filter.currentData()
        selected_action = self.action_filter.currentData()
        rows = secure_store.list_activity_log(
            self._conn,
            self._user_id,
            user_id=int(selected_user) if selected_user is not None else None,
            action=str(selected_action) if selected_action is not None else None,
            limit=500,
        )
        users = {
            int(user["id"]): str(user.get("nama_lengkap") or user["username"])
            for user in secure_store.list_activity_users(
                self._conn, self._user_id
            )
        }
        self.table.setRowCount(0)
        for log in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                log["created_at"],
                users.get(log["user_id"], "Sistem") if log["user_id"] else "Sistem",
                log["aksi"],
                log["detail"] or "",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.status_label.setText(
            f"Menampilkan {len(rows)} entri terbaru."
        )
