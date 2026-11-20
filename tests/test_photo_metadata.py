"""Tes keterbacaan rincian foto dan pemisahan keadaan hasil ekstraksi."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QLabel

from auth import session
from tests.test_workspace import workspace_app, workspace_context
from ui.main_window import MainWindow
from ui.photo_metadata import PhotoMetadataPanel


def test_metadata_formats_missing_values_time_and_literal_text(workspace_app) -> None:
    """Tidak ada JSON, null, atau markup aktif pada rincian yang telah dibuka."""
    panel = PhotoMetadataPanel()
    panel.show_verified({
        "victim_id": 1, "posko_id": None, "officer_id": 2,
        "timestamp": "2026-11-16T09:56:09+07:00",
        "keterangan": '<b>Foto korban</b> & "keterangan"', "original_sha256": "a" * 64,
    }, {"victim_id": "K-001 · Ayu (ID 1)", "officer_id": "Relawan (ID 2)"})
    try:
        assert panel.values["posko_id"].text() == "Tidak dicantumkan"
        assert panel.values["timestamp"].text() == "16 Nov 2026, 09:56:09 UTC+07:00"
        assert panel.values["keterangan"].text() == '<b>Foto korban</b> & "keterangan"'
        assert panel.values["keterangan"].textFormat() == Qt.TextFormat.PlainText
        assert panel.hash_view.toPlainText() == "a" * 64
        assert panel.hash_view.isReadOnly()
        panel.show_encrypted(b"ciphertext")
        assert all(value.text() == "" for value in panel.values.values())
        assert panel.payload_view.toPlainText() == b"ciphertext".hex()
        panel.show_error("Foto rusak atau telah diubah.")
        assert panel.details.isHidden()
        assert panel.payload_view.toPlainText() == ""
        assert panel.hash_view.toPlainText() == ""
        assert panel.state_label.text() == "Metadata tidak dapat dibuka"
        panel.clear()
        assert panel.description.text() == ""
    finally:
        panel.deleteLater()
        workspace_app.processEvents()


def test_volunteer_photo_workspace_only_shows_upload_and_preview(workspace_context, workspace_app) -> None:
    _, users, master = workspace_context
    window = MainWindow()
    session.login(users["relawan"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("photos")
    window.show()
    try:
        workspace_app.processEvents()
        page = window.photo_page
        assert page.findChild(PhotoMetadataPanel) is None
        assert all(label.text() != "Metadata foto" for label in page.findChildren(QLabel))
        assert page.upload_button.isVisible() and page.caption_input.isVisible()
        assert page.image_view.isVisible()
        window._end_session("Logout uji relawan.")
    finally:
        window.close()
        workspace_app.processEvents()


@pytest.mark.parametrize("width", [480, 980, 1440])
def test_verified_metadata_stays_inside_photo_workspace(
    workspace_context, workspace_app, width: int,
) -> None:
    """Hash panjang dan keterangan multiline harus membungkus di panel preview."""
    conn, users, master = workspace_context
    window = MainWindow()
    session.login(users["admin"], master)
    window._show_dashboard(session.get_current_user())
    window._open_page("photos")
    window.resize(width, 900)
    window.show()
    page = window.photo_page
    panel = page.metadata_view
    panel.show_verified({
        "timestamp": "2026-11-16T09:56:09+07:00", "posko_id": None,
        "keterangan": "Dokumentasi lapangan dengan keterangan panjang.\n" * 4,
        "original_sha256": "8092b4fd" * 8,
    }, {})
    try:
        for _ in range(6):
            workspace_app.processEvents()
        assert page.workspace.scroll.horizontalScrollBar().maximum() == 0
        for value in panel.values.values():
            corner = value.mapTo(panel, QPoint(0, 0))
            assert corner.x() >= 0
            assert corner.x() + value.width() <= panel.width()
            assert value.height() >= value.heightForWidth(value.width())
        captions = panel.findChildren(QLabel, "photoMetadataCaption")
        assert len(captions) == 6
        assert all(caption.isVisible() and caption.width() > 0 for caption in captions)
        window._end_session("Sesi berakhir saat pengujian metadata.")
        assert all(value.text() == "" for value in panel.values.values())
    finally:
        window.close()
        workspace_app.processEvents()
