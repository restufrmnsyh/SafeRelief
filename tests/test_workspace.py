"""Tes bingkai menu bersama dan dialog tanpa kamera atau dongle fisik."""

import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

import config
from app import _apply_light_theme
from auth import dongle, session
from crypto import keys
from database import db, secure_store
from ui.main_window import MainWindow
from ui.workspace import PAGE_INFO
from ui.victims_page import VictimFormDialog
from ui.posko_management_page import PoskoFormDialog
from ui.volunteer_management_page import VolunteerFormDialog, DongleChangeDialog


@pytest.fixture(scope="module")
def workspace_app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    _apply_light_theme(app)
    return app


@pytest.fixture
def workspace_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace_app):
    """Data uji sepenuhnya terpisah dari database organisasi."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "workspace.db")
    db.init_db()
    conn = db.get_connection()
    users = {}
    for role in ("admin", "relawan"):
        uid = db.insert_user(conn, {
            "nama_lengkap": f"{role.title()} Uji Visual", "username": role,
            "role": role, "password_hash": "test-hash",
        })
        users[role] = dict(db.get_user_by_id(conn, uid))
    post = db.insert_posko(conn, {"nama": "Posko Uji", "lokasi": "Lokasi uji", "kapasitas": 40})
    master = os.urandom(32)
    secure_store.add_victim(conn, keys.derive_key(master, b"db"), {
        "kode_korban": "UJI-001", "nama_panggilan": "Korban Uji", "status": "selamat",
        "nama_lengkap": "Nama Sensitif Uji", "nik": "NIK-UJI", "posko_id": post,
    })
    monkeypatch.setattr(dongle, "is_any_valid_dongle_present", lambda _conn: True)
    monkeypatch.setattr(dongle, "verify_dongle", lambda _user: bytes(32))
    yield conn, users, master
    session.logout()
    conn.close()
    workspace_app.processEvents()


@pytest.mark.parametrize("role", ["admin", "relawan"])
def test_feature_sidebar_routes_and_cleanup(workspace_context, workspace_app, monkeypatch, role: str) -> None:
    """Semua rute memakai halaman asli dan dapat berpindah tanpa melewati dashboard."""
    conn, users, master = workspace_context
    window = MainWindow()
    session.login(users[role], master)
    window._show_dashboard(session.get_current_user())
    window.resize(1440, 900)
    window.show()
    pages = list(PAGE_INFO) if role == "admin" else ["victims", "chat", "photos", "files", "aid"]
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text: warnings.append(text))
    try:
        for route in pages:
            window._open_page(route)
            for _ in range(5):
                workspace_app.processEvents()
            page = window.pages.currentWidget()
            shell = page.workspace
            assert shell.title == PAGE_INFO[route][0]
            assert set(shell.navigation.buttons) == set(pages)
            assert shell.navigation.buttons[route].isChecked()
            assert page.back_button.parent() is shell.navigation
            assert page.logout_button.parent() is shell.navigation
            assert shell.work.width() <= shell.scroll.viewport().width()
            old_shell = shell
            window._open_page(route)
            assert window.pages.currentWidget().workspace is old_shell
            for group in shell.navigation.groups.values():
                if not group.isChecked():
                    QTest.mouseClick(group, Qt.MouseButton.LeftButton)
            target = "files" if route != "files" else "victims"
            QTest.mouseClick(shell.navigation.buttons[target], Qt.MouseButton.LeftButton)
            assert window.pages.currentWidget().workspace.current == target
        window._open_page("demo" if role == "admin" else "victims")
        if role == "admin":
            assert window.demo_panel_page.record_input.count() == 1
        window._end_session("Logout uji")
        assert not session.is_logged_in()
        assert window.pages.currentWidget() is window.login_page
        assert shell.identity.text() == ""
        assert warnings == []
    finally:
        window.close()
        workspace_app.processEvents()


@pytest.mark.parametrize("route", list(PAGE_INFO))
@pytest.mark.parametrize("width", [480, 980, 1440])
def test_feature_layout_keeps_content_inside_scroll_view(
    workspace_context, workspace_app, route: str, width: int,
) -> None:
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page(route)
    page = window.pages.currentWidget()
    page.setParent(None)
    page.resize(width, 900)
    page.show()
    try:
        for _ in range(5):
            workspace_app.processEvents()
        shell = page.workspace
        assert shell.work.width() <= shell.scroll.viewport().width(), route
        assert shell.menu_button.isVisible() == (width < 720)
        assert shell.sidebar_scroll.isVisible() == (width >= 720)
        assert page.logout_button.height() >= 44
    finally:
        page.close()
        window.close()
        workspace_app.processEvents()


@pytest.mark.parametrize("kind", ["victim", "posko", "volunteer", "dongle"])
def test_dialog_theme_preserves_validation_and_password_masking(
    workspace_app, kind: str,
) -> None:
    if kind == "victim":
        dialog = VictimFormDialog([])
    elif kind == "posko":
        dialog = PoskoFormDialog()
    elif kind == "volunteer":
        dialog = VolunteerFormDialog([], drives=["Z:\\"])
    else:
        dialog = DongleChangeDialog(["Z:\\"])
    try:
        assert dialog.objectName() == "formDialog"
        with pytest.raises(ValueError):
            dialog.values()
        if hasattr(dialog, "password_input"):
            assert dialog.password_input.echoMode() == dialog.password_input.EchoMode.Password
        dialog.show()
        workspace_app.processEvents()
        QTest.keyClick(dialog, Qt.Key.Key_Escape)
        assert not dialog.isVisible()
    finally:
        dialog.close()


def test_wrapped_victims_keeps_explicit_decryption(workspace_context, workspace_app) -> None:
    """Perubahan visual tidak membuka kolom sebelum pengguna menekan Decrypt."""
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("victims")
    window.resize(1440, 900)
    window.show()
    workspace_app.processEvents()
    page = window.victims_page
    try:
        assert page.table.item(0, 0).text() == "[terenkripsi]"
        decrypt = page.table.cellWidget(0, 5)
        QTest.mouseClick(decrypt, Qt.MouseButton.LeftButton)
        assert page.table.item(0, 0).text() == "UJI-001"
        assert page.edit_button.isEnabled()
    finally:
        window.close()
        workspace_app.processEvents()


def test_wrapped_chat_encrypts_before_displaying_plaintext(workspace_context, workspace_app, monkeypatch) -> None:
    """Widget asli masih mengirim ciphertext dan membuka pesan hanya lewat Decrypt."""
    conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("chat")
    window.resize(1440, 900)
    window.show()
    workspace_app.processEvents()
    page = window.chat_page
    text = "Pesan koordinasi untuk pengujian UI"
    dialogs: list[str] = []
    for method in ("warning", "critical", "information"):
        monkeypatch.setattr(QMessageBox, method, lambda _p, _t, message: dialogs.append(message))
    try:
        page.message_input.setPlainText(text)
        QTest.mouseClick(page.send_button, Qt.MouseButton.LeftButton)
        assert dialogs == []
        stored = db.get_messages_between(conn, users["admin"]["id"], users["relawan"]["id"])
        assert len(stored) == 1
        assert text.encode() not in bytes(stored[0]["ciphertext"])
        page.inbox.setCurrentRow(0)
        assert page.plaintext_view.toPlainText() == ""
        QTest.mouseClick(page.decrypt_button, Qt.MouseButton.LeftButton)
        assert dialogs == []
        assert page.plaintext_view.toPlainText() == text
    finally:
        window.close()
        workspace_app.processEvents()
    assert dialogs == []
