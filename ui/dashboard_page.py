"""Dashboard SafeRelief dengan Role Badge Soft Red dan Full Pastel Metric Cards."""

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from auth import session
from database import secure_store


class DashboardPage(QWidget):
    """Dashboard modern bertema Soft Pastel & Role Red Badge."""

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

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(20)

        # Hero Banner Header
        hero_card = QFrame()
        hero_card.setStyleSheet(
            "background-color: #FFFFFF; "
            "border: 1px solid #E2E8F0; "
            "border-radius: 12px; padding: 20px;"
        )
        hero_layout = QHBoxLayout(hero_card)

        hero_text_layout = QVBoxLayout()
        self.welcome_label = QLabel(
            f"Selamat Datang, <b>{user.get('nama_lengkap') or user.get('username')}</b>"
        )
        self.welcome_label.setStyleSheet("font-size: 20px; color: #0F172A;")
        
        sub_hero = QLabel("Sistem Operasional Tanggap Bencana & Kriptografi Data Terdekripsi.")
        sub_hero.setStyleSheet("font-size: 12px; color: #64748B; margin-top: 2px;")

        hero_text_layout.addWidget(self.welcome_label)
        hero_text_layout.addWidget(sub_hero)

        # Role Badge Merah Soft
        self.role_badge = QLabel("ROLE: ADMIN" if role == "admin" else "ROLE: RELAWAN")
        self.role_badge.setStyleSheet(
            "background-color: #FEF2F2; color: #EF4444; font-weight: 800; "
            "font-size: 11px; padding: 6px 14px; border-radius: 20px; border: 1px solid #FCA5A5;"
        )
        self.logout_button = QPushButton("Logout")
        self.logout_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_button.setStyleSheet(
            "QPushButton {"
            "background-color: #111827; color: #F9FAFB; border: none; border-radius: 10px; "
            "padding: 8px 14px; font-weight: 700; font-size: 11px; }"
            "QPushButton:hover { background-color: #1F2937; }"
        )
        self.logout_button.clicked.connect(self._confirm_logout)

        hero_layout.addLayout(hero_text_layout)
        hero_layout.addStretch()
        hero_layout.addWidget(self.role_badge, alignment=Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(self.logout_button, alignment=Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(hero_card)

        # Section Title
        lbl_sec1 = QLabel("Ringkasan Status Korban Bencana")
        lbl_sec1.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        main_layout.addWidget(lbl_sec1)

        # Full Pastel Metric Cards Layout
        self.status_container = QWidget()
        self.status_layout = QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(10)
        main_layout.addWidget(self.status_container)

        # Posko Details Card
        self.posko_card = QFrame()
        self.posko_card.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 12px; padding: 16px;"
        )
        posko_layout = QVBoxLayout(self.posko_card)
        
        lbl_posko_title = QLabel("Sebaran Korban per Posko")
        lbl_posko_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A; margin-bottom: 4px;")
        
        self.posko_summary_label = QLabel()
        self.posko_summary_label.setStyleSheet("font-size: 13px; color: #475569; line-height: 1.5;")
        self.posko_summary_label.setWordWrap(True)

        posko_layout.addWidget(lbl_posko_title)
        posko_layout.addWidget(self.posko_summary_label)

        main_layout.addWidget(self.posko_card)

        nav_card = QFrame()
        nav_card.setStyleSheet(
            "background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 12px; padding: 16px;"
        )
        nav_layout = QVBoxLayout(nav_card)
        nav_title = QLabel("Navigasi Akses Cepat")
        nav_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        nav_layout.addWidget(nav_title)

        navigation_map = {
            "admin": [
                ("victims", "Data Korban"),
                ("volunteers", "Manajemen Relawan"),
                ("posko", "Manajemen Posko"),
                ("chat", "Chat Koordinasi"),
                ("photos", "Dokumentasi Foto"),
                ("files", "Berkas Laporan"),
                ("aid", "Distribusi Bantuan"),
                ("activity", "Log Aktivitas"),
                ("demo", "Panel Demo"),
            ],
            "relawan": [
                ("victims", "Data Korban"),
                ("chat", "Chat Koordinasi"),
                ("photos", "Dokumentasi Foto"),
                ("files", "Berkas Laporan"),
                ("aid", "Distribusi Bantuan"),
            ],
        }

        button_grid = QGridLayout()
        button_grid.setHorizontalSpacing(12)
        button_grid.setVerticalSpacing(12)
        for index, (page_name, label) in enumerate(navigation_map.get(role, [])):
            button = QPushButton(label)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(
                "QPushButton {"
                "background-color: #FFFFFF;"
                "color: #0F172A;"
                "border: 1px solid #E2E8F0;"
                "border-radius: 10px;"
                "padding: 12px 14px;"
                "text-align: left;"
                "font-weight: 600;"
                "font-size: 12px;"
                "}"
                "QPushButton:hover {"
                "background-color: #F8FAFC;"
                "border: 1px solid #CBD5E1;"
                "}"
            )
            button.clicked.connect(lambda checked=False, page=page_name: self.page_requested.emit(page))
            row, col = divmod(index, 2)
            button_grid.addWidget(button, row, col)

        nav_layout.addLayout(button_grid)
        main_layout.addWidget(nav_card)
        main_layout.addStretch()

        self.refresh_summary()

    def refresh_summary(self) -> None:
        user = session.get_current_user()
        try:
            secure_store.require_active_user(
                self._conn, int(user["id"]), str(user["role"])
            )
        except PermissionError as exc:
            QMessageBox.warning(self, "Akses ditolak", str(exc))
            return
        
        summary = secure_store.get_dashboard_summary(self._conn)
        by_status = summary["by_status"]
        
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Konfigurasi Full Pastel (Background Soft & Teks Kontras Terbaca)
        status_config = [
            ("selamat", "Selamat", "#065F46", "#D1FAE5", "#A7F3D0"),
            ("luka ringan", "Luka Ringan", "#92400E", "#FEF3C7", "#FDE68A"),
            ("luka berat", "Luka Berat", "#991B1B", "#FEE2E2", "#FCA5A5"),
            ("meninggal", "Meninggal", "#334155", "#F1F5F9", "#E2E8F0"),
            ("tidak diketahui", "Tidak Diketahui", "#5B21B6", "#EDE9FE", "#DDD6FE"),
        ]

        for key, label, text_color, bg_pastel, border_color in status_config:
            count = by_status.get(key, 0)
            card = QFrame()
            card.setStyleSheet(
                f"background-color: {bg_pastel}; "
                f"border: 1px solid {border_color}; "
                f"border-radius: 10px; "
                f"padding: 12px;"
            )
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(2)

            lbl_num = QLabel(str(count))
            lbl_num.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {text_color};")
            
            lbl_name = QLabel(label.upper())
            lbl_name.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {text_color};")

            c_layout.addWidget(lbl_num)
            c_layout.addWidget(lbl_name)

            self.status_layout.addWidget(card)

        posko_lines = [
            f"<b>{row['nama_posko']}</b>: {row['total']} Korban"
            for row in summary["by_posko"]
        ]
        self.posko_summary_label.setText(
            " • ".join(posko_lines) if posko_lines else "Belum ada posko terdaftar."
        )

    def _confirm_logout(self) -> None:
        """Konfirmasi logout manual dan delegasikan seluruh flow ke MainWindow."""
        parent = self.parent()
        window = self.window()
        dialog_parent = parent if parent is not None else window
        if dialog_parent is None:
            return
        reply = QMessageBox.question(
            dialog_parent,
            "Logout",
            "Yakin ingin logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if hasattr(window, "_end_session"):
                window._end_session("Logout manual dari dashboard.")

    def clear_sensitive_state(self) -> None:
        self.welcome_label.clear()
        self.posko_summary_label.clear()