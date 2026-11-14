"""Regresi formulir yang dibuka dari halaman menu, bukan dialog tanpa induk."""

import pytest
from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea

from auth import dongle, session
from database import db
from tests.test_workspace import workspace_app, workspace_context
from ui.main_window import MainWindow
from ui.posko_management_page import PoskoFormDialog
from ui.victims_page import VictimFormDialog
from ui.volunteer_management_page import DongleChangeDialog, VolunteerFormDialog


def rendered_background(dialog: QDialog) -> str:
    """Ambil piksel dari permukaan dialog di luar teks dan kontrol."""
    return dialog.grab().toImage().pixelColor(10, 10).name()


@pytest.mark.parametrize("route,title", [
    ("victims", "Tambah Korban"), ("posko", "Tambah Posko"),
    ("volunteers", "Tambah Relawan"),
])
def test_actual_add_forms_have_white_background_from_menu(
    workspace_context, workspace_app, monkeypatch, route: str, title: str,
) -> None:
    """Klik tombol asli harus membuka formulir terang meskipun induknya memakai tema dashboard."""
    conn, users, master = workspace_context
    monkeypatch.setattr(dongle, "find_removable_drives", lambda: ["Z:\\"])
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page(route)
    window.resize(1440, 900)
    window.show()
    workspace_app.processEvents()
    before = (len(db.list_users(conn)), len(db.list_posko(conn)), len(db.list_victims_plaintext(conn)))
    captured: list[dict] = []

    def inspect_and_cancel() -> None:
        dialog = workspace_app.activeModalWidget()
        if isinstance(dialog, QDialog):
            heading = dialog.findChild(QLabel, "workspaceTitle")
            buttons = dialog.findChild(QDialogButtonBox)
            save = buttons.button(QDialogButtonBox.StandardButton.Save)
            captured.append({
                "title": dialog.windowTitle(), "root": dialog.objectName(),
                "background": rendered_background(dialog),
                "color": heading.palette().color(QPalette.ColorRole.WindowText).name(),
                "save_visible": save.isVisible(), "save_text": save.text(),
                "cancel_text": buttons.button(QDialogButtonBox.StandardButton.Cancel).text(),
                "save_in_dialog": dialog.rect().contains(save.mapTo(dialog, QPoint(0, 0))),
            })
            QTest.keyClick(dialog, Qt.Key.Key_Escape)

    try:
        QTimer.singleShot(80, inspect_and_cancel)
        QTest.mouseClick(window.pages.currentWidget().add_button, Qt.MouseButton.LeftButton)
        assert captured == [{
            "title": title, "root": "formDialog", "background": "#ffffff",
            "color": "#20243c", "save_visible": True, "save_text": "Simpan",
            "cancel_text": "Batal", "save_in_dialog": True,
        }]
        after = (len(db.list_users(conn)), len(db.list_posko(conn)), len(db.list_victims_plaintext(conn)))
        assert after == before
        assert session.is_logged_in()
    finally:
        window.close()
        workspace_app.processEvents()


@pytest.mark.parametrize("kind", ["victim", "posko", "volunteer", "dongle"])
def test_nested_edit_dialogs_and_scroll_surfaces_are_opaque(
    workspace_context, workspace_app, kind: str,
) -> None:
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("volunteers")
    parent = window.pages.currentWidget()
    if kind == "victim":
        dialog = VictimFormDialog([], victim={"kode_korban": "UJI-001"}, parent=parent)
    elif kind == "posko":
        dialog = PoskoFormDialog(posko={"nama": "Posko Uji", "lokasi": "Lokasi uji"}, parent=parent)
    elif kind == "volunteer":
        dialog = VolunteerFormDialog([], volunteer=users["relawan"], parent=parent)
    else:
        dialog = DongleChangeDialog(["Z:\\"], parent=parent)
    try:
        window.show()
        dialog.show()
        for _ in range(4):
            workspace_app.processEvents()
        assert rendered_background(dialog) == "#ffffff"
        viewport = dialog.findChild(QScrollArea).viewport()
        pixel = viewport.grab().toImage().pixelColor(viewport.width() - 8, 8)
        assert pixel.name() == "#ffffff"
        assert pixel.alpha() == 255
        if kind == "victim":
            assert dialog.code_input.text() == "UJI-001"
            assert not dialog.code_input.isEnabled()
        if hasattr(dialog, "password_input"):
            assert dialog.password_input.echoMode() == dialog.password_input.EchoMode.Password
    finally:
        dialog.close()
        window.close()
        workspace_app.processEvents()
