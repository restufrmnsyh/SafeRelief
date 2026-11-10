"""Jendela utama SafeRelief (Kembali ke alur login asli, Dashboard modern)."""

import sqlite3

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from auth import dongle
from database import db
from database import secure_store
from ui.activity_log_page import ActivityLogPage
from ui.aid_page import AidPage
from ui.chat_page import ChatPage
from ui.dashboard_page import DashboardPage
from ui.demo_panel_page import DemoPanelPage
from ui.files_page import FilesPage
from ui.login_page import LoginPage
from ui.photo_page import PhotoPage
from ui.posko_management_page import PoskoManagementPage
from ui.victims_page import VictimsPage
from ui.volunteer_management_page import VolunteerManagementPage


class MainWindow(QMainWindow):
    """Menahan halaman login sampai dongle valid terdeteksi."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("SafeRelief")
        self.resize(900, 650)
        self._conn = db.get_connection()

        self.pages = QStackedWidget(self)
        self.setCentralWidget(self.pages)

        self.gate_page = QWidget()
        self.gate_page.setObjectName("dongleGatePage")
        gate_layout = QVBoxLayout(self.gate_page)
        self.gate_status = QLabel("Mencari dongle...")
        self.gate_status.setObjectName("dongleStatus")
        gate_layout.addStretch()
        gate_layout.addWidget(self.gate_status)
        gate_layout.addStretch()
        self.gate_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pages.addWidget(self.gate_page)

        self.login_page = LoginPage(self._conn, self)
        self.login_page.authenticated.connect(self._show_dashboard)
        self.pages.addWidget(self.login_page)

        self.dashboard_page: DashboardPage | None = None
        self.victims_page: VictimsPage | None = None
        self.volunteer_page: VolunteerManagementPage | None = None
        self.posko_page: PoskoManagementPage | None = None
        self.chat_page: ChatPage | None = None
        self.photo_page: PhotoPage | None = None
        self.files_page: FilesPage | None = None
        self.aid_page: AidPage | None = None
        self.activity_log_page: ActivityLogPage | None = None
        self.demo_panel_page: DemoPanelPage | None = None
        self._logout_notice: str | None = None

        self.pages.setCurrentWidget(self.gate_page)
        self._dongle_timer = QTimer(self)
        self._dongle_timer.setInterval(2000)
        self._dongle_timer.timeout.connect(self._check_dongle)
        self._check_dongle()
        self._dongle_timer.start()

    def _check_dongle(self) -> None:
        """Periksa dongle akun aktif dan putus sesi bila faktor fisik hilang."""
        from auth import session

        try:
            is_valid = dongle.is_any_valid_dongle_present(self._conn)
        except (OSError, sqlite3.Error) as exc:
            if session.is_logged_in():
                self._end_session(f"Gagal memeriksa dongle: {exc}")
            else:
                self._show_gate(f"Gagal memeriksa dongle: {exc}")
            return

        if session.is_logged_in():
            try:
                user_id = int(session.get_current_user()["id"])
                user = db.get_user_by_id(self._conn, user_id)
                if user is None or not user["is_active"]:
                    self._end_session("Akun dinonaktifkan, sesi diakhiri")
                    return
                dongle.verify_dongle(user)
            except (OSError, ValueError, sqlite3.Error, PermissionError):
                self._end_session("Dongle dicabut, sesi diakhiri")
                return
            return

        if is_valid:
            self.login_page.set_gate_status("Dongle valid terdeteksi")
            if self.pages.currentWidget() is self.gate_page:
                self.pages.setCurrentWidget(self.login_page)
        elif self.pages.currentWidget() is not self.dashboard_page:
            self.login_page.set_gate_status("Mencari dongle...")
            self._show_gate(self._logout_notice or "Mencari dongle...")

        if is_valid and self._logout_notice:
            self.login_page.show_session_ended(self._logout_notice)
            self.pages.setCurrentWidget(self.login_page)
            self._logout_notice = None

    def _end_session(self, message: str) -> None:
        """Buang halaman berkunci dan paksa gerbang sebelum login berikutnya."""
        from auth import session

        session.logout()
        self._discard_authenticated_pages()
        self._logout_notice = message
        self.login_page.set_gate_status("Mencari dongle...")
        try:
            is_valid = dongle.is_any_valid_dongle_present(self._conn)
        except (OSError, sqlite3.Error):
            is_valid = False
        if is_valid:
            self.login_page.show_session_ended(message)
            self.pages.setCurrentWidget(self.login_page)
            self._logout_notice = None
        else:
            self._show_gate(message)

    def _discard_authenticated_pages(self) -> None:
        """Hapus halaman yang menyimpan identitas atau kunci turunan lama."""
        if self.volunteer_page is not None:
            self.volunteer_page.stop_face_capture()
        if self.photo_page is not None:
            self.photo_page.stop_worker(cancel_pending=True)
        if self.files_page is not None:
            self.files_page.stop_worker(cancel_pending=True)

        names = (
            "dashboard_page", "victims_page", "volunteer_page", "posko_page",
            "chat_page", "photo_page", "files_page", "aid_page",
            "activity_log_page", "demo_panel_page",
        )
        for name in names:
            page = getattr(self, name)
            if page is not None:
                clear_state = getattr(page, "clear_sensitive_state", None)
                if callable(clear_state):
                    clear_state()
                self.pages.removeWidget(page)
                page.deleteLater()
                setattr(self, name, None)

    def _show_gate(self, message: str = "Mencari dongle...") -> None:
        self.gate_status.setText(message)
        self.pages.setCurrentWidget(self.gate_page)

    def _show_dashboard(self, user: dict[str, object]) -> None:
        """Tampilkan dashboard yang menyesuaikan role sesi terautentikasi."""
        from auth import session

        if not session.is_logged_in() or user.get("id") != session.get_current_user().get("id"):
            raise RuntimeError("Identitas dashboard tidak cocok dengan sesi aktif.")
        try:
            secure_store.require_active_user(self._conn, int(user["id"]))
        except PermissionError:
            self._end_session("Akun dinonaktifkan, sesi diakhiri")
            return
        if self.dashboard_page is None:
            self.dashboard_page = DashboardPage(self._conn, self)
            self.dashboard_page.page_requested.connect(self._open_page)
            self.pages.addWidget(self.dashboard_page)
        self.dashboard_page.refresh_summary()
        self.pages.setCurrentWidget(self.dashboard_page)

    def _open_page(self, page_name: str) -> None:
        """Navigasi hanya ke halaman yang sudah diimplementasikan pada tahap ini."""
        if self.dashboard_page is None:
            return
        from auth import session

        if not session.is_logged_in():
            return
        role = session.get_current_user().get("role")
        try:
            secure_store.require_active_user(
                self._conn, int(session.get_current_user()["id"]), str(role)
            )
        except PermissionError:
            self._end_session("Akun dinonaktifkan, sesi diakhiri")
            return
        allowed_pages = {
            "admin": {
                "victims", "volunteers", "posko", "chat", "photos", "files",
                "aid", "activity", "demo",
            },
            "relawan": {"victims", "chat", "photos", "files", "aid"},
        }
        if page_name not in allowed_pages.get(str(role), set()):
            return
        if page_name == "victims":
            if self.victims_page is None:
                self.victims_page = VictimsPage(self._conn, self)
                self.victims_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.victims_page)
            self.victims_page.refresh()
            self.pages.setCurrentWidget(self.victims_page)
        elif page_name == "volunteers":
            if self.volunteer_page is None:
                self.volunteer_page = VolunteerManagementPage(
                    self._conn, self
                )
                self.volunteer_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.volunteer_page)
            self.volunteer_page.refresh()
            self.pages.setCurrentWidget(self.volunteer_page)
        elif page_name == "posko":
            if self.posko_page is None:
                self.posko_page = PoskoManagementPage(self._conn, self)
                self.posko_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.posko_page)
            self.posko_page.refresh()
            self.pages.setCurrentWidget(self.posko_page)
        elif page_name == "chat":
            if self.chat_page is None:
                self.chat_page = ChatPage(self._conn, self)
                self.chat_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.chat_page)
            self.chat_page.refresh()
            self.pages.setCurrentWidget(self.chat_page)
        elif page_name == "photos":
            if self.photo_page is None:
                self.photo_page = PhotoPage(self._conn, self)
                self.photo_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.photo_page)
            self.photo_page.refresh()
            self.pages.setCurrentWidget(self.photo_page)
        elif page_name == "files":
            if self.files_page is None:
                self.files_page = FilesPage(self._conn, self)
                self.files_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.files_page)
            self.files_page.refresh()
            self.pages.setCurrentWidget(self.files_page)
        elif page_name == "aid":
            if self.aid_page is None:
                self.aid_page = AidPage(self._conn, self)
                self.aid_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.aid_page)
            self.aid_page.refresh()
            self.pages.setCurrentWidget(self.aid_page)
        elif page_name == "activity":
            if self.activity_log_page is None:
                self.activity_log_page = ActivityLogPage(self._conn, self)
                self.activity_log_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.activity_log_page)
            self.activity_log_page.refresh()
            self.pages.setCurrentWidget(self.activity_log_page)
        elif page_name == "demo":
            if self.demo_panel_page is None:
                self.demo_panel_page = DemoPanelPage(self._conn, self)
                self.demo_panel_page.dashboard_requested.connect(
                    self._return_to_dashboard
                )
                self.pages.addWidget(self.demo_panel_page)
            self.demo_panel_page.refresh_records()
            self.pages.setCurrentWidget(self.demo_panel_page)

    def closeEvent(self, event) -> None:
        """Bersihkan timer, session, halaman sensitif, dan koneksi DB saat jendela ditutup."""
        from auth import session

        try:
            if hasattr(self, "_dongle_timer"):
                self._dongle_timer.stop()
            self._discard_authenticated_pages()
            if session.is_logged_in():
                session.logout()
            if getattr(self, "_conn", None) is not None:
                self._conn.close()
                self._conn = None
        finally:
            super().closeEvent(event)

    def _return_to_dashboard(self) -> None:
        from auth import session

        if not session.is_logged_in():
            return
        try:
            secure_store.require_active_user(
                self._conn,
                int(session.get_current_user()["id"]),
                str(session.get_current_user()["role"]),
            )
        except PermissionError:
            self._end_session("Akun dinonaktifkan, sesi diakhiri")
            return
        if self.dashboard_page is not None:
            self.dashboard_page.refresh_summary()
            self.pages.setCurrentWidget(self.dashboard_page)