"""Dashboard operasional SafeRelief dengan navigasi sesuai peran sesi."""

import sqlite3

from PySide6.QtCore import QDate, QLocale, QTimer, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from auth import session
from database import secure_store
from ui.dashboard_style import DASHBOARD_STYLE, MENU_STYLE


NAVIGATION = (
    ("Data lapangan", (
        ("victims", "Data Korban"), ("aid", "Distribusi Bantuan"),
    )),
    ("Koordinasi", (
        ("chat", "Chat Koordinasi"), ("photos", "Dokumentasi Foto"),
        ("files", "Berkas Laporan"),
    )),
    ("Administrasi", (
        ("volunteers", "Manajemen Relawan"), ("posko", "Manajemen Posko"),
        ("activity", "Log Aktivitas"), ("demo", "Panel Demo"),
    )),
)

STATUSES = (
    ("selamat", "Selamat"), ("luka ringan", "Luka ringan"),
    ("luka berat", "Luka berat"), ("meninggal", "Meninggal"),
    ("tidak diketahui", "Belum diketahui"),
)


def _label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    """Nilai DB memakai teks biasa agar nama pengguna tidak menjadi markup."""
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    label.setMinimumWidth(0)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


def _button(text: str) -> QPushButton:
    """Samakan target klik dan akses keyboard untuk tindakan dashboard."""
    button = QPushButton(text)
    button.setMinimumHeight(44)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return button


class DashboardPage(QWidget):
    """Ringkasan korban dan pintu masuk fitur tanpa mengubah autentikasi."""

    page_requested = Signal(str)

    def __init__(self, conn: sqlite3.Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        user = session.get_current_user()
        self._role = str(user.get("role"))
        if self._role not in ("admin", "relawan"):
            raise PermissionError("Peran sesi tidak dikenal.")
        self._user_id = int(user["id"])
        self._conn = conn
        self._layout_mode = ""
        self._summary: dict | None = None
        self.setObjectName("dashboardPage")
        self.setStyleSheet(DASHBOARD_STYLE)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._build_navigation(outer)

        self.work_scroll = QScrollArea()
        self.work_scroll.setWidgetResizable(True)
        self.work_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.work = QWidget()
        self.work_layout = QVBoxLayout(self.work)
        self.work_layout.setSpacing(24)
        self.work_scroll.setWidget(self.work)
        outer.addWidget(self.work_scroll, 1)
        self._build_header()
        self.data_message = _label("Memuat ringkasan korban...", "muted", True)
        self.data_message.setAccessibleName("Status pemuatan dashboard")
        self.work_layout.addWidget(self.data_message)
        self.body = QGridLayout()
        self.body.setSpacing(24)
        self.work_layout.addLayout(self.body)
        self._build_main_content()
        self._build_context()
        self.body.addWidget(self.main_content, 0, 0)
        self.body.addWidget(self.context_panel, 0, 1)
        self.body.setColumnStretch(0, 1)
        self.work_layout.addStretch()
        self._adapt_layout()
        self.refresh_summary()

    def _build_navigation(self, outer: QHBoxLayout) -> None:
        """Pertahankan tujuan navigasi dan pembatasan peran yang sudah ada."""
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 28, 16, 20)
        side.setSpacing(5)
        side.addWidget(_label("SafeRelief", "brand"))
        side.addWidget(_label("Koordinasi tanggap bencana", "muted"))
        side.addSpacing(24)
        self.overview_button = _button("Dashboard")
        self.overview_button.setProperty("nav", True)
        self.overview_button.setCheckable(True)
        self.overview_button.setChecked(True)
        self.overview_button.clicked.connect(self.refresh_summary)
        side.addWidget(self.overview_button)
        self.nav_buttons: dict[str, QPushButton] = {}
        self.group_buttons: dict[str, QToolButton] = {}
        self.group_panels: dict[str, QWidget] = {}
        self.menu = QMenu(self)
        self.menu.setStyleSheet(MENU_STYLE)
        overview = self.menu.addAction("Dashboard", self.refresh_summary)
        overview.setCheckable(True)
        overview.setChecked(True)
        overview.triggered.connect(lambda: overview.setChecked(True))
        for group, items in NAVIGATION:
            if self._role != "admin" and group == "Administrasi":
                continue
            heading = QToolButton()
            heading.setText(group)
            heading.setProperty("groupToggle", True)
            heading.setCheckable(True)
            heading.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            heading.setMinimumHeight(44)
            heading.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            heading.setCursor(Qt.CursorShape.PointingHandCursor)
            heading.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            panel = QWidget()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(14, 0, 0, 6)
            panel_layout.setSpacing(4)
            self.group_buttons[group] = heading
            self.group_panels[group] = panel
            heading.toggled.connect(
                lambda expanded, name=group: self._set_group_expanded(name, expanded)
            )
            side.addSpacing(8)
            side.addWidget(heading)
            side.addWidget(panel)
            submenu = self.menu.addMenu(group)
            for page, title in items:
                button = _button(title)
                button.setProperty("nav", True)
                button.clicked.connect(lambda _checked=False, target=page: self._navigate(target))
                self.nav_buttons[page] = button
                panel_layout.addWidget(button)
                submenu.addAction(title, lambda target=page: self._navigate(target))
            heading.setChecked(group == "Data lapangan")
            self._set_group_expanded(group, heading.isChecked())
        side.addStretch()
        self.logout_button = _button("Logout")
        self.logout_button.setProperty("nav", True)
        self.logout_button.clicked.connect(self._confirm_logout)
        side.addWidget(self.logout_button)
        self.menu.addSeparator()
        self.menu.addAction("Logout", self._confirm_logout)
        self.menu.aboutToHide.connect(self._restore_menu_focus)
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFixedWidth(218)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.sidebar)
        outer.addWidget(self.sidebar_scroll)

    def _set_group_expanded(self, group: str, expanded: bool) -> None:
        """Panah dan status tombol selalu mengikuti visibilitas submenu."""
        heading = self.group_buttons[group]
        heading.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        heading.setAccessibleDescription("Kelompok terbuka" if expanded else "Kelompok tertutup")
        self.group_panels[group].setVisible(expanded)

    def _build_header(self) -> None:
        """Menu berlabel menggantikan sidebar saat jendela sempit."""
        header = QHBoxLayout()
        self.menu_button = QToolButton()
        self.menu_button.setText("Menu")
        self.menu_button.setAccessibleName("Buka menu navigasi")
        self.menu_button.setMinimumSize(70, 44)
        self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu_button.setMenu(self.menu)
        header.addWidget(self.menu_button)
        titles = QVBoxLayout()
        titles.setSpacing(3)
        titles.addWidget(_label("Ruang koordinasi", "muted"))
        titles.addWidget(_label("Dashboard", "pageTitle"))
        header.addLayout(titles, 1)
        self.refresh_button = _button("Perbarui")
        self.refresh_button.clicked.connect(self.refresh_summary)
        header.addWidget(self.refresh_button)
        self.work_layout.addLayout(header)

    def _build_main_content(self) -> None:
        """Status dan sebaran memakai data ringkasan yang sudah tersedia."""
        self.main_content = QWidget()
        main = QVBoxLayout(self.main_content)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(24)
        welcome = QFrame()
        welcome.setObjectName("welcomePanel")
        banner = QHBoxLayout(welcome)
        banner.setContentsMargins(26, 24, 26, 24)
        banner.setSpacing(16)
        text = QVBoxLayout()
        self.welcome_label = _label("", "welcomeTitle", True)
        text.addWidget(self.welcome_label)
        text.addWidget(_label("Pantau data korban dan koordinasikan bantuan dari sini.", "", True))
        text.addSpacing(10)
        self.victims_button = _button("Buka data korban")
        self.victims_button.clicked.connect(lambda: self._navigate("victims"))
        text.addWidget(self.victims_button, alignment=Qt.AlignmentFlag.AlignLeft)
        banner.addLayout(text, 1)
        self.hero_numbers = QWidget()
        total = QVBoxLayout(self.hero_numbers)
        total.setContentsMargins(0, 0, 0, 0)
        self.total_label = _label("", "heroTotal")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        total.addWidget(self.total_label)
        caption = _label("korban tercatat", "", True)
        caption.setAlignment(Qt.AlignmentFlag.AlignRight)
        total.addWidget(caption)
        self.hero_numbers.setFixedWidth(118)
        banner.addWidget(self.hero_numbers)
        main.addWidget(welcome)
        main.addWidget(_label("Kondisi korban", "sectionTitle"))
        self.status_container = QWidget()
        self.status_layout = QGridLayout(self.status_container)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(10)
        self.status_cards: list[QFrame] = []
        self.status_values: dict[str, QLabel] = {}
        for key, title in STATUSES:
            card = QFrame()
            card.setObjectName("metricCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 18, 12, 18)
            layout.setSpacing(8)
            value = _label("", "metricValue")
            layout.addWidget(value)
            layout.addWidget(_label(title, "metricLabel", True))
            self.status_cards.append(card)
            self.status_values[key] = value
        main.addWidget(self.status_container)
        self.posko_card = QFrame()
        self.posko_card.setObjectName("tablePanel")
        panel = QVBoxLayout(self.posko_card)
        panel.setContentsMargins(20, 20, 20, 18)
        panel.setSpacing(12)
        panel.addWidget(_label("Sebaran korban per posko", "sectionTitle"))
        self.posko_summary_label = _label("", "muted", True)
        panel.addWidget(self.posko_summary_label)
        self.posko_table = QTableWidget(0, 2)
        self.posko_table.setHorizontalHeaderLabels(("Posko", "Korban"))
        self.posko_table.verticalHeader().hide()
        self.posko_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.posko_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.posko_table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.posko_table.setColumnWidth(1, 84)
        self.posko_table.verticalHeader().setDefaultSectionSize(50)
        self.posko_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.posko_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.posko_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.posko_table.setShowGrid(False)
        self.posko_table.setAlternatingRowColors(True)
        self.posko_table.setMinimumHeight(200)
        self.posko_table.setAccessibleName("Jumlah korban di setiap posko")
        self.posko_table.setWordWrap(True)
        panel.addWidget(self.posko_table)
        main.addWidget(self.posko_card)
        main.addStretch()

    def _build_context(self) -> None:
        """Panel samping memakai identitas sesi dan jumlah posko, bukan aktivitas rekaan."""
        self.context_panel = QFrame()
        self.context_panel.setObjectName("contextPanel")
        context = QVBoxLayout(self.context_panel)
        context.setContentsMargins(24, 24, 24, 24)
        context.setSpacing(20)
        identity = QHBoxLayout()
        self.initials_label = _label("", "initials")
        self.initials_label.setFixedSize(48, 48)
        self.initials_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.initials_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity.addWidget(self.initials_label)
        details = QVBoxLayout()
        self.identity_label = _label("", "identityName", True)
        self.role_badge = _label("Admin" if self._role == "admin" else "Relawan", "muted")
        details.addWidget(self.identity_label)
        details.addWidget(self.role_badge)
        identity.addLayout(details, 1)
        context.addLayout(identity)
        self.date_label = _label("", "muted", True)
        context.addWidget(self.date_label)
        context.addWidget(_label("Ringkasan lapangan", "sectionTitle"))
        stats_panel = QFrame()
        stats_panel.setObjectName("contextStats")
        stats = QVBoxLayout(stats_panel)
        stats.setContentsMargins(18, 18, 18, 18)
        stats.setSpacing(6)
        self.posko_count_label = _label("", "contextValue")
        stats.addWidget(self.posko_count_label)
        stats.addWidget(_label("posko terdaftar", "muted"))
        stats.addSpacing(12)
        self.unassigned_label = _label("", "contextValue")
        stats.addWidget(self.unassigned_label)
        stats.addWidget(_label("korban belum terkait posko", "muted", True))
        context.addWidget(stats_panel)
        context.addWidget(_label("Akses cepat", "sectionTitle"))
        self.chat_button = _button("Buka chat koordinasi")
        self.chat_button.clicked.connect(lambda: self._navigate("chat"))
        self.aid_button = _button("Lihat distribusi bantuan")
        self.aid_button.clicked.connect(lambda: self._navigate("aid"))
        context.addWidget(self.chat_button)
        context.addWidget(self.aid_button)
        notice = QFrame()
        notice.setObjectName("noticePanel")
        note = QVBoxLayout(notice)
        note.setContentsMargins(16, 16, 16, 16)
        note.addWidget(_label("Selama bertugas", "sectionTitle"))
        note.addWidget(_label("Biarkan dongle tetap terpasang. Sesi berakhir otomatis saat dongle dicabut.", "muted", True))
        context.addWidget(notice)
        context.addStretch()

    def _show_identity(self, user: dict) -> None:
        """Inisial berasal dari akun aktif, tanpa foto profil rekaan."""
        name = str(user.get("nama_lengkap") or user.get("username") or "")
        self.welcome_label.setText(f"Selamat datang, {name}")
        self.identity_label.setText(name)
        self.initials_label.setText("".join(word[0] for word in name.split()[:2]).upper())

    def _require_active_session(self) -> dict:
        """Widget sesi lama tidak boleh menavigasi atas nama sesi berbeda."""
        user = session.get_current_user()
        if int(user["id"]) != self._user_id or user.get("role") != self._role:
            raise PermissionError("Sesi pengguna telah berubah.")
        secure_store.require_active_user(self._conn, self._user_id, self._role)
        return user

    def _navigate(self, target: str) -> None:
        """Pertahankan sinyal navigasi yang digunakan MainWindow."""
        if target not in self.nav_buttons:
            return
        try:
            self._require_active_session()
        except (PermissionError, RuntimeError, sqlite3.Error) as exc:
            self.data_message.setText(f"Akses ditolak: {exc}")
            return
        self.page_requested.emit(target)

    def refresh_summary(self) -> None:
        """Tampilkan data, keadaan kosong, atau kegagalan tanpa angka lama."""
        self.overview_button.setChecked(True)
        self.data_message.setText("Memuat ringkasan korban...")
        self.refresh_button.setEnabled(False)
        self.refresh_button.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.data_message.repaint()
        try:
            user = self._require_active_session()
            summary = secure_store.get_dashboard_summary(self._conn)
            self._show_identity(user)
            self.date_label.setText(QLocale("id_ID").toString(QDate.currentDate(), "dddd, d MMMM yyyy"))
            self._summary = summary
            by_status = summary["by_status"]
            total = sum(by_status.values())
            self.total_label.setText(str(total))
            for key, _title in STATUSES:
                self.status_values[key].setText(str(by_status.get(key, 0)))
            rows = summary["by_posko"]
            self.posko_count_label.setText(str(len(rows)))
            self.unassigned_label.setText(str(max(0, total - sum(row["total"] for row in rows))))
            self.posko_table.setRowCount(len(rows))
            for index, row in enumerate(rows):
                self.posko_table.setItem(index, 0, QTableWidgetItem(str(row["nama_posko"])))
                count = QTableWidgetItem(str(row["total"]))
                count.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.posko_table.setItem(index, 1, count)
            self.posko_table.resizeRowsToContents()
            self.posko_table.setVisible(bool(rows))
            self.posko_summary_label.setText(
                "Jumlah korban tercatat di setiap posko." if rows
                else "Belum ada posko terdaftar. " + (
                    "Tambahkan melalui Manajemen Posko." if self._role == "admin"
                    else "Hubungi admin untuk pendaftaran posko."
                )
            )
            self.data_message.setText(
                "Belum ada data korban. Buka Data Korban untuk mulai mendata."
                if not total else f"{total} korban tercatat. Ringkasan berdasarkan data yang tersimpan."
            )
        except (PermissionError, RuntimeError, sqlite3.Error) as exc:
            self._clear_summary()
            self.data_message.setText(f"Ringkasan gagal dimuat: {exc}. Klik Perbarui untuk mencoba lagi.")
        finally:
            self.refresh_button.setEnabled(True)
            self.refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)

    def _clear_summary(self) -> None:
        """Kosongkan data lama ketika pembacaan gagal atau sesi berakhir."""
        self._summary = None
        self.total_label.clear()
        self.posko_count_label.clear()
        self.unassigned_label.clear()
        self.posko_summary_label.clear()
        self.posko_table.setRowCount(0)
        self.posko_table.hide()
        for value in self.status_values.values():
            value.clear()

    def _adapt_layout(self) -> None:
        """Pindahkan panel konteks dan susun ulang kartu sesuai ruang baca."""
        width = self.width()
        mode = "wide" if width >= 1180 else "medium" if width >= 720 else "compact"
        self.sidebar_scroll.setVisible(mode != "compact")
        self.menu_button.setVisible(mode == "compact")
        self.hero_numbers.setVisible(width >= 520)
        margin = 16 if mode == "compact" else 28
        self.work_layout.setContentsMargins(margin, 24, margin, 24)
        columns = 5 if width >= 1050 else 3 if width >= 720 else 2
        for index, card in enumerate(self.status_cards):
            self.status_layout.addWidget(card, index // columns, index % columns)
        if mode == self._layout_mode:
            return
        self._layout_mode = mode
        if mode == "wide":
            self.context_panel.setFixedWidth(268)
            self.body.addWidget(self.context_panel, 0, 1)
        else:
            self.context_panel.setMinimumWidth(0)
            self.context_panel.setMaximumWidth(16777215)
            self.body.addWidget(self.context_panel, 1, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._adapt_layout()

    def _restore_menu_focus(self) -> None:
        """Kembalikan fokus ke pemicu setelah Escape atau pemilihan menu."""
        if self.menu_button.isVisible():
            QTimer.singleShot(0, self.menu_button.setFocus)

    def _confirm_logout(self) -> None:
        """Gunakan konfirmasi dan pembersihan sesi terpusat di MainWindow."""
        reply = QMessageBox.question(
            self, "Logout", "Yakin ingin logout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes and hasattr(self.window(), "_end_session"):
            self.window()._end_session("Logout manual dari dashboard.")

    def clear_sensitive_state(self) -> None:
        """Hapus identitas dan ringkasan ketika sesi berakhir."""
        self.menu.close()
        self._clear_summary()
        self.welcome_label.clear()
        self.identity_label.clear()
        self.initials_label.clear()
        self.date_label.clear()
        self.data_message.clear()
