"""Tes popup sebenarnya agar latar transparan tidak menghasilkan dialog hitam."""

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QComboBox, QLabel, QMessageBox

from auth import session
from tests.test_workspace import workspace_app, workspace_context
from ui.main_window import MainWindow
from ui.popup_theme import COMBO_POPUP_STYLE, MESSAGE_STYLE, install_popup_theme
from ui.workspace import PAGE_INFO


def assert_readable(popup: QMessageBox, app) -> None:
    """Periksa piksel latar hasil render dan warna teks Qt, bukan hanya string QSS."""
    for _ in range(3):
        app.processEvents()
    rendered = popup.grab().toImage()
    background = rendered.pixelColor(rendered.width() - 8, 8)
    assert background.name() == "#ffffff"
    assert background.alpha() == 255
    message = popup.findChild(QLabel, "qt_msgbox_label")
    assert message is not None
    assert message.palette().color(QPalette.ColorRole.WindowText).name() == "#20243c"
    assert popup.styleSheet() == MESSAGE_STYLE
    assert all(button.height() >= 44 for button in popup.buttons())


@pytest.mark.parametrize("route", list(PAGE_INFO))
def test_message_from_every_menu_has_opaque_light_background(
    workspace_context, workspace_app, route: str,
) -> None:
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page(route)
    window.show()
    popup = QMessageBox(
        QMessageBox.Icon.Information, "Data uji", "Pilih data terlebih dahulu.",
        QMessageBox.StandardButton.Ok, window.pages.currentWidget(),
    )
    try:
        popup.show()
        assert_readable(popup, workspace_app)
        QTest.keyClick(popup, Qt.Key.Key_Return)
        assert popup.result() == QMessageBox.StandardButton.Ok
    finally:
        popup.close()
        window.close()
        workspace_app.processEvents()


@pytest.mark.parametrize("icon", [
    QMessageBox.Icon.Information, QMessageBox.Icon.Warning,
    QMessageBox.Icon.Critical, QMessageBox.Icon.Question,
])
def test_all_message_types_remain_readable_from_dialogs(workspace_app, icon) -> None:
    from ui.posko_management_page import PoskoFormDialog

    parent = PoskoFormDialog()
    popup = QMessageBox(icon, "Pesan uji", "Pesan harus tetap terbaca.", QMessageBox.StandardButton.Ok, parent)
    try:
        parent.show()
        popup.show()
        assert_readable(popup, workspace_app)
    finally:
        popup.close()
        parent.close()


def test_actual_victim_selection_message_is_readable(workspace_context, workspace_app) -> None:
    """Reproduksi tombol Detail tanpa baris terpilih seperti laporan pengguna."""
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("victims")
    window.show()
    captures: list[tuple[str, str, str]] = []

    def inspect_and_close() -> None:
        popup = workspace_app.activeModalWidget()
        if isinstance(popup, QMessageBox):
            image = popup.grab().toImage()
            captures.append((popup.text(), image.pixelColor(image.width() - 8, 8).name(), popup.styleSheet()))
            QTest.keyClick(popup, Qt.Key.Key_Return)

    try:
        QTimer.singleShot(50, inspect_and_close)
        QTest.mouseClick(window.victims_page.detail_button, Qt.MouseButton.LeftButton)
        assert captures == [("Pilih korban terlebih dahulu.", "#ffffff", MESSAGE_STYLE)]
    finally:
        window.close()
        workspace_app.processEvents()


def test_popup_theme_preserves_confirmation_default_and_escape(workspace_context, workspace_app) -> None:
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("victims")
    defaults: list[QMessageBox.StandardButton] = []

    def cancel() -> None:
        popup = workspace_app.activeModalWidget()
        if isinstance(popup, QMessageBox):
            defaults.append(popup.standardButton(popup.defaultButton()))
            QTest.keyClick(popup, Qt.Key.Key_Escape)

    try:
        QTimer.singleShot(50, cancel)
        result = QMessageBox.question(
            window.victims_page, "Konfirmasi", "Lanjutkan tindakan ini?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        assert defaults == [QMessageBox.StandardButton.No]
        assert result == QMessageBox.StandardButton.No
        assert session.is_logged_in()
    finally:
        window.close()
        workspace_app.processEvents()


def test_combo_popup_has_its_own_light_theme(workspace_context, workspace_app) -> None:
    _conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("victims")
    window.show()
    combo: QComboBox = window.victims_page.status_filter
    try:
        for _ in range(3):
            workspace_app.processEvents()
        combo.showPopup()
        workspace_app.processEvents()
        assert combo.view().styleSheet() == COMBO_POPUP_STYLE
        assert combo.view().palette().color(QPalette.ColorRole.Base).name() == "#ffffff"
        assert combo.view().palette().color(QPalette.ColorRole.Text).name() == "#20243c"
        QTest.keyClick(combo.view(), Qt.Key.Key_Escape)
        assert not combo.view().isVisible()
    finally:
        combo.hidePopup()
        window.close()


def test_popup_filter_is_installed_only_once(workspace_app) -> None:
    original = workspace_app._saferelief_popup_theme
    install_popup_theme(workspace_app)
    assert workspace_app._saferelief_popup_theme is original
