"""Dashboard SafeRelief dengan menu yang mengikuti peran sesi aktif."""

import sqlite3

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auth import session
from database import secure_store


class DashboardPage(QWidget):
    """Tampilkan ringkasan korban dan pintasan sesuai role."""

    page_requested = Signal(str)

    def __init__(
        self, conn: sqlite3.Connection, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        user = session.get_current_user()
        role = user.get("role")
        if role not in ("admin", "relawan"):
            raise PermissionError("Peran sesi tidak dikenal.")
        self._conn = conn

        self.welcome_label = QLabel(
            f"Selamat datang, {user.get('nama_lengkap') or user.get('username')}"
        )
        self.role_label = QLabel(
            "Admin" if role == "admin" else "Relawan"
        )
        self.status_summary = QLabel()
        self.post_summary = QLabel()
        self.status_summary.setWordWrap(True)
        self.post_summary.setWordWrap(True)

        summary_layout = QGridLayout()
        summary_layout.addWidget(QLabel("Jumlah korban per status"), 0, 0)
        summary_layout.addWidget(self.status_summary, 1, 0)
        summary_layout.addWidget(QLabel("Jumlah korban per posko"), 0, 1)
        summary_layout.addWidget(self.post_summary, 1, 1)
        summary_group = QGroupBox("Ringkasan")
        summary_group.setLayout(summary_layout)

        self.menu_layout = QVBoxLayout()
        self.menu_buttons: dict[str, QPushButton] = {}
        self._add_menu("Data Korban", "victims")
        if role == "admin":
            self._add_menu("Manajemen Relawan", "volunteers")
            self._add_menu("Chat Koordinasi", "chat")
            self._add_menu("Dokumentasi Foto", "photos")
            self._add_menu("Berkas Laporan", "files")
            self._add_menu("Log Aktivitas", None)
            self._add_menu("Distribusi Bantuan", None)
        else:
            self._add_menu("Chat Koordinasi", "chat")
            self._add_menu("Dokumentasi Foto", "photos")
            self._add_menu("Berkas Laporan", "files")
            self._add_menu("Riwayat Bantuan", None)

        layout = QVBoxLayout(self)
        layout.addWidget(self.welcome_label)
        layout.addWidget(self.role_label)
        layout.addWidget(summary_group)
        layout.addWidget(QLabel("Menu"))
        layout.addLayout(self.menu_layout)
        layout.addStretch()
        self.refresh_summary()

    def _add_menu(self, title: str, page_name: str | None) -> None:
        button = QPushButton(title)
        button.setObjectName(f"menu_{page_name or 'coming_soon'}")
        if page_name is None:
            button.setEnabled(False)
            button.setToolTip("Halaman ini dikerjakan pada sub-tahap berikutnya.")
        else:
            button.clicked.connect(lambda: self.page_requested.emit(page_name))
        self.menu_layout.addWidget(button)
        self.menu_buttons[title] = button

    def refresh_summary(self) -> None:
        """Muat ulang jumlah menggunakan secure_store, bukan SQL di UI."""
        summary = secure_store.get_dashboard_summary(self._conn)
        by_status = summary["by_status"]
        statuses = (
            "selamat",
            "luka ringan",
            "luka berat",
            "meninggal",
            "tidak diketahui",
        )
        self.status_summary.setText(
            "\n".join(f"{status}: {by_status.get(status, 0)}" for status in statuses)
        )
        posko_lines = [
            f"{row['nama_posko']}: {row['total']}"
            for row in summary["by_posko"]
        ]
        self.post_summary.setText(
            "\n".join(posko_lines) if posko_lines else "Belum ada posko."
        )
