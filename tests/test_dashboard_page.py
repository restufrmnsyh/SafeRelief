"""Uji dashboard: data nyata, navigasi per peran, keyboard, dan ukuran jendela."""

import os
import sqlite3
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

import config
from app import _apply_light_theme
from auth import dongle, session
from database import db, secure_store
from ui.dashboard_page import DashboardPage, STATUSES
from ui.main_window import MainWindow


@pytest.fixture(scope="module")
def dashboard_app() -> QApplication:
    """Offscreen Qt memerlukan font terdaftar agar ukuran teks dapat diuji."""
    app = QApplication.instance() or QApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        font_path = Path("C:/Windows/Fonts") / name
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
    _apply_light_theme(app)
    return app


@pytest.fixture
def dashboard_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, dashboard_app):
    """Data berlabel uji disimpan hanya dalam database sementara pytest."""
    path = tmp_path / "dashboard.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    db.init_db(path)
    conn = db.get_connection(path)
    users: dict[str, dict] = {}
    for role in ("admin", "relawan"):
        uid = db.insert_user(conn, {
            "nama_lengkap": f"{role.title()} Uji Visual", "username": role,
            "password_hash": "test-hash", "role": role,
        })
        users[role] = dict(db.get_user_by_id(conn, uid))
    yield conn, users
    session.logout()
    conn.close()
    dashboard_app.processEvents()


def populate_summary(conn: sqlite3.Connection) -> None:
    """Sertakan posko kosong dan korban tanpa posko agar hitungan tidak menyesatkan."""
    north = db.insert_posko(conn, {"nama": "Posko Uji Utara", "lokasi": "Data uji visual", "kapasitas": 80})
    db.insert_posko(conn, {"nama": "Posko Uji Selatan", "lokasi": "Data uji visual", "kapasitas": 40})
    for index, status in enumerate(("selamat", "selamat", "luka ringan", "luka berat", "tidak diketahui")):
        db.insert_victim(conn, {
            "kode_korban": f"VISUAL-{index}", "status": status,
            "posko_id": north if index < 3 else None,
        })


@pytest.mark.parametrize("role", ["admin", "relawan"])
def test_dashboard_numbers_come_from_database(dashboard_context, dashboard_app, role: str) -> None:
    conn, users = dashboard_context
    populate_summary(conn)
    session.login(users[role], os.urandom(32))
    page = DashboardPage(conn)
    try:
        assert page.total_label.text() == "5"
        assert page.posko_count_label.text() == "2"
        assert page.unassigned_label.text() == "2"
        assert page.status_values["selamat"].text() == "2"
        assert page.status_values["meninggal"].text() == "0"
        assert page.posko_table.rowCount() == 2
        assert page.posko_table.item(0, 1).text() == "0"
        assert page.posko_table.item(1, 1).text() == "3"
        assert page.initials_label.text() == ("AU" if role == "admin" else "RU")
    finally:
        page.close()


@pytest.mark.parametrize("role", ["admin", "relawan"])
def test_all_sidebar_destinations_open_existing_pages(
    dashboard_context, dashboard_app, monkeypatch: pytest.MonkeyPatch, role: str,
) -> None:
    conn, users = dashboard_context
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    monkeypatch.setattr(dongle, "verify_dongle", lambda _user: bytes(32))
    window = MainWindow()
    session.login(users[role], os.urandom(32))
    window._show_dashboard(session.get_current_user())
    window.resize(1440, 900)
    window.show()
    dashboard_app.processEvents()
    page = window.dashboard_page
    assert page is not None
    expected = {"victims", "chat", "photos", "files", "aid"}
    if role == "admin":
        expected |= {"volunteers", "posko", "activity", "demo"}
    assert set(page.nav_buttons) == expected
    try:
        for heading in page.group_buttons.values():
            if not heading.isChecked():
                QTest.mouseClick(heading, Qt.MouseButton.LeftButton)
        for name, button in page.nav_buttons.items():
            assert button.isVisible()
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            dashboard_app.processEvents()
            assert window.pages.currentWidget() is not page, name
            window.pages.currentWidget().dashboard_requested.emit()
            assert window.pages.currentWidget() is page
        for button, target in (
            (page.victims_button, "victims_page"),
            (page.chat_button, "chat_page"), (page.aid_button, "aid_page"),
        ):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            assert window.pages.currentWidget() is getattr(window, target)
            window._return_to_dashboard()
        QTest.mouseClick(page.refresh_button, Qt.MouseButton.LeftButton)
        assert page.refresh_button.isEnabled()
        QTest.mouseClick(page.overview_button, Qt.MouseButton.LeftButton)
        assert window.pages.currentWidget() is page
        assert page.overview_button.isChecked()
    finally:
        window.close()
        dashboard_app.processEvents()


def test_empty_error_and_retry_states(dashboard_context, dashboard_app, monkeypatch) -> None:
    conn, users = dashboard_context
    session.login(users["admin"], os.urandom(32))
    page = DashboardPage(conn)
    try:
        assert "Belum ada data korban" in page.data_message.text()
        assert "Belum ada posko" in page.posko_summary_label.text()
        assert page.total_label.text() == "0"
        read_summary = secure_store.get_dashboard_summary

        def fail_read(_conn: sqlite3.Connection) -> dict:
            assert "Memuat" in page.data_message.text()
            assert not page.refresh_button.isEnabled()
            raise sqlite3.OperationalError("simulated read failure")

        monkeypatch.setattr(secure_store, "get_dashboard_summary", fail_read)
        page.refresh_summary()
        assert "gagal dimuat" in page.data_message.text()
        assert page.total_label.text() == ""
        assert page.posko_table.rowCount() == 0
        monkeypatch.setattr(secure_store, "get_dashboard_summary", read_summary)
        page.refresh_summary()
        assert page.total_label.text() == "0"
        assert page.refresh_button.isEnabled()
    finally:
        page.close()


@pytest.mark.parametrize("width", [360, 480, 640, 720, 800, 980, 1050, 1180, 1280, 1440])
def test_dashboard_reflows_without_horizontal_clipping(
    dashboard_context, dashboard_app, width: int,
) -> None:
    conn, users = dashboard_context
    populate_summary(conn)
    session.login(users["admin"], os.urandom(32))
    page = DashboardPage(conn)
    try:
        page.resize(width, 900)
        page.show()
        for _ in range(4):
            dashboard_app.processEvents()
        assert page.width() == width
        assert page.work.width() <= page.work_scroll.viewport().width()
        assert page.work_scroll.horizontalScrollBar().maximum() == 0
        assert page.menu_button.isVisible() == (width < 720)
        assert page.sidebar_scroll.isVisible() == (width >= 720)
        for card in page.status_cards:
            assert page.work.rect().contains(card.mapTo(page.work, QPoint(0, 0)))
            assert card.width() > 80
        assert page.victims_button.height() >= 44
        if width >= 1180:
            assert page.body.getItemPosition(page.body.indexOf(page.context_panel))[0:2] == (0, 1)
        else:
            assert page.body.getItemPosition(page.body.indexOf(page.context_panel))[0:2] == (1, 0)
        initials_end = page.initials_label.mapTo(page.context_panel, QPoint(48, 0)).x()
        name_start = page.identity_label.mapTo(page.context_panel, QPoint(0, 0)).x()
        assert initials_end < name_start
    finally:
        page.close()


def test_narrow_menu_opens_and_returns_focus_with_escape(dashboard_context, dashboard_app) -> None:
    conn, users = dashboard_context
    session.login(users["relawan"], os.urandom(32))
    page = DashboardPage(conn)
    page.resize(480, 800)
    page.show()
    dashboard_app.processEvents()
    opened: list[bool] = []

    def close_popup() -> None:
        opened.append(page.menu.isVisible())
        QTest.keyClick(page.menu, Qt.Key.Key_Escape)

    try:
        page.menu_button.setFocus()
        QTimer.singleShot(50, close_popup)
        QTest.keyClick(page.menu_button, Qt.Key.Key_Space)
        QTest.qWait(80)
        dashboard_app.processEvents()
        assert opened == [True]
        assert not page.menu.isVisible()
        assert page.menu_button.hasFocus()
        action_names = {action.text() for action in page.menu.actions()}
        assert "Manajemen Relawan" not in action_names
        targets: list[str] = []
        page.page_requested.connect(targets.append)
        coordination = next(a.menu() for a in page.menu.actions() if a.text() == "Koordinasi")
        chat_action = next(a for a in coordination.actions() if a.text() == "Chat Koordinasi")
        chat_action.trigger()
        assert targets == ["chat"]
        page.menu_button.setFocus()
        QTest.keyClick(page.menu_button, Qt.Key.Key_Tab)
        assert page.refresh_button.hasFocus()
    finally:
        page.close()


@pytest.mark.parametrize("role", ["admin", "relawan"])
def test_group_dropdowns_toggle_with_mouse_and_keyboard(
    dashboard_context, dashboard_app, role: str,
) -> None:
    """Kelompok tertutup tidak menampilkan tujuan; buka-tutup tetap dapat memakai Space."""
    conn, users = dashboard_context
    session.login(users[role], os.urandom(32))
    page = DashboardPage(conn)
    page.resize(1440, 900)
    page.show()
    dashboard_app.processEvents()
    requested: list[str] = []
    page.page_requested.connect(requested.append)
    try:
        assert page.group_buttons["Data lapangan"].isChecked()
        assert not page.group_panels["Koordinasi"].isVisible()
        assert not page.nav_buttons["chat"].isVisible()
        assert ("Administrasi" in page.group_buttons) == (role == "admin")
        menu_groups = {a.text(): a.menu() for a in page.menu.actions() if a.menu()}
        assert set(menu_groups) == set(page.group_buttons)
        for group, heading in page.group_buttons.items():
            if heading.isChecked():
                QTest.mouseClick(heading, Qt.MouseButton.LeftButton)
            assert not page.group_panels[group].isVisible()
            assert heading.arrowType() == Qt.ArrowType.RightArrow
            heading.setFocus()
            QTest.keyClick(heading, Qt.Key.Key_Space)
            assert page.group_panels[group].isVisible()
            assert heading.arrowType() == Qt.ArrowType.DownArrow
            QTest.keyClick(heading, Qt.Key.Key_Tab)
            assert page.group_panels[group].isAncestorOf(dashboard_app.focusWidget())
            QTest.mouseClick(heading, Qt.MouseButton.LeftButton)
            assert not page.group_panels[group].isVisible()
        assert requested == []
    finally:
        page.close()


def test_names_are_plain_text_and_logout_clears_dashboard(dashboard_context, dashboard_app) -> None:
    conn, users = dashboard_context
    user = dict(users["admin"])
    user["nama_lengkap"] = "<b>Nama Uji</b>"
    session.login(user, os.urandom(32))
    page = DashboardPage(conn)
    try:
        assert "<b>Nama Uji</b>" in page.welcome_label.text()
        assert page.welcome_label.textFormat() == Qt.TextFormat.PlainText
        page.clear_sensitive_state()
        assert page.welcome_label.text() == ""
        assert page.identity_label.text() == ""
        assert page.total_label.text() == ""
        assert page.posko_table.rowCount() == 0
        assert all(page.status_values[key].text() == "" for key, _ in STATUSES)
    finally:
        page.close()


def test_logout_escape_cancels_and_yes_ends_session(
    dashboard_context, dashboard_app, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uji dialog logout asli melalui event keyboard dan tombol Qt."""
    _conn, users = dashboard_context
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    window = MainWindow()
    session.login(users["admin"], os.urandom(32))
    window._show_dashboard(session.get_current_user())
    window.resize(1440, 900)
    window.show()
    dashboard_app.processEvents()
    page = window.dashboard_page
    assert page is not None
    opened: list[str] = []

    def answer(confirm: bool) -> None:
        dialog = dashboard_app.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        opened.append(dialog.windowTitle())
        if confirm:
            QTest.mouseClick(dialog.button(QMessageBox.StandardButton.Yes), Qt.MouseButton.LeftButton)
        else:
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

    try:
        QTimer.singleShot(50, lambda: answer(False))
        QTest.mouseClick(page.logout_button, Qt.MouseButton.LeftButton)
        assert session.is_logged_in()
        assert window.pages.currentWidget() is page
        QTimer.singleShot(50, lambda: answer(True))
        QTest.mouseClick(page.logout_button, Qt.MouseButton.LeftButton)
        assert not session.is_logged_in()
        assert window.pages.currentWidget() is window.login_page
        assert opened == ["Logout", "Logout"]
    finally:
        window.close()
        dashboard_app.processEvents()


def test_blocked_or_stale_dashboard_cannot_navigate(
    dashboard_context, dashboard_app,
) -> None:
    conn, users = dashboard_context
    session.login(users["admin"], os.urandom(32))
    page = DashboardPage(conn)
    requested: list[str] = []
    page.page_requested.connect(requested.append)
    try:
        db.update_user_active(conn, users["admin"]["id"], 0)
        page.nav_buttons["victims"].click()
        assert requested == []
        assert "Akses ditolak" in page.data_message.text()
        session.login(users["relawan"], os.urandom(32))
        page.chat_button.click()
        page.refresh_summary()
        assert requested == []
        assert page.total_label.text() == ""
    finally:
        page.close()
