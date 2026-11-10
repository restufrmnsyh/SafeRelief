"""Tes alur halaman chat, dokumentasi foto, dan berkas laporan."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox
from PIL import Image

import config
from auth import session
from database import db, secure_store
from ui.chat_page import ChatPage
from ui.files_page import FilesPage
from ui.photo_page import PhotoPage


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Gunakan satu event loop Qt untuk semua tes widget."""
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def media_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp):
    database_path = tmp_path / "media.db"
    storage_path = tmp_path / "storage"
    monkeypatch.setattr(config, "STORAGE_DIR", storage_path)
    db.init_db(database_path)
    conn = db.get_connection(database_path)
    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin",
            "username": "admin",
            "password_hash": "hash",
            "role": "admin",
        },
    )
    volunteer_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Relawan",
            "username": "relawan",
            "password_hash": "hash",
            "role": "relawan",
        },
    )
    posko_id = db.insert_posko(
        conn, {"nama": "Posko A", "lokasi": "Lapangan", "kapasitas": 10}
    )
    victim_id = db.insert_victim(
        conn,
        {
            "kode_korban": "K-001",
            "nama_panggilan": "Ayu",
            "status": "selamat",
            "posko_id": posko_id,
        },
    )
    session.login(
        {"id": volunteer_id, "username": "relawan", "role": "relawan"},
        os.urandom(config.MASTER_KEY_LENGTH),
    )
    monkeypatch.setattr(
        QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok
    )
    yield conn, admin_id, volunteer_id, victim_id, posko_id, storage_path
    session.logout()
    conn.close()


def _finish_worker(page, qapp) -> None:
    worker = page._worker
    assert worker is not None
    worker.wait()
    qapp.processEvents()
    assert page._worker is None


def test_chat_sends_ciphertext_and_decrypts_only_on_request(media_context, qapp):
    conn, admin_id, volunteer_id, *_ = media_context
    page = ChatPage(conn)
    assert page.contact_input.currentData() == admin_id

    page.message_input.setPlainText("Koordinasi di posko.")
    page.send_message()
    assert page.inbox.count() == 1
    assert page.plaintext_view.toPlainText() == ""

    message = secure_store.get_messages(conn, volunteer_id, admin_id)[0]
    ciphertext = bytes(message["ciphertext"])
    assert b"Koordinasi di posko." not in ciphertext
    page.inbox.setCurrentRow(0)
    assert page.ciphertext_view.toPlainText()
    page.manual_key_input.setText("kunci-manual-salah")
    page.decrypt_button.click()
    assert page.plaintext_view.toPlainText() != "Koordinasi di posko."
    page.manual_key_input.clear()
    page.decrypt_button.click()
    assert page.plaintext_view.toPlainText() == "Koordinasi di posko."

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = ChatPage(conn)
    assert admin_page.contact_input.currentData() == volunteer_id
    admin_page.inbox.setCurrentRow(0)
    admin_page.decrypt_button.click()
    assert admin_page.plaintext_view.toPlainText() == "Koordinasi di posko."
    page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


def test_chat_rejects_utf8_message_over_vernam_byte_limit(
    media_context, monkeypatch: pytest.MonkeyPatch, qapp
):
    conn, _admin_id, volunteer_id, *_ = media_context
    page = ChatPage(conn)
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, text: warnings.append(text),
    )
    oversized_message = "🙂" * 2041
    assert len(oversized_message) < config.VERNAM_MAX_MESSAGE_BYTES
    assert len(oversized_message.encode("utf-8")) > config.VERNAM_MAX_MESSAGE_BYTES
    page.message_input.setPlainText(oversized_message)

    page.send_message()

    assert secure_store.get_messages(conn, volunteer_id, int(page.contact_input.currentData())) == []
    assert warnings and "8160 byte" in warnings[0]
    page.deleteLater()
    qapp.processEvents()


def test_photo_page_embeds_encrypted_metadata_and_admin_extracts(
    media_context, tmp_path: Path, qapp
):
    conn, admin_id, volunteer_id, victim_id, posko_id, storage_path = media_context
    source_path = tmp_path / "incident.jpg"
    Image.new("RGB", (800, 800), color=(90, 120, 150)).save(source_path)
    page = PhotoPage(conn)
    page.victim_combo.setCurrentIndex(page.victim_combo.findData(victim_id))
    page.posko_combo.setCurrentIndex(page.posko_combo.findData(posko_id))
    page.caption_input.setText("Kondisi posko")
    page.embed_photo(source_path)
    _finish_worker(page, qapp)

    photo_row = db.list_photos(conn, uploaded_by=volunteer_id)[0]
    stego_path = storage_path / photo_row["image_path"]
    assert stego_path.suffix == ".png"
    assert "JPG" in page.status_label.text()

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = PhotoPage(conn)
    admin_page.table.selectRow(0)
    admin_page.extract_selected()
    encrypted = admin_page.metadata_view.text()
    assert '"victim_id":' not in encrypted
    assert '"original_sha256":' not in encrypted
    assert admin_page.image_view.text() != ""
    admin_page.decrypt_selected()
    extracted = admin_page.metadata_view.text()
    assert '"victim_id":' in extracted
    assert '"original_sha256":' in extracted
    assert admin_page.image_view.pixmap() is not None
    assert not admin_page.image_view.pixmap().isNull()
    page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


def test_photo_page_auto_sets_posko_when_victim_selected(media_context, qapp):
    conn, _admin_id, _volunteer_id, victim_id, posko_id, _storage_path = media_context
    page = PhotoPage(conn)
    page.victim_combo.setCurrentIndex(page.victim_combo.findData(victim_id))
    assert page.posko_combo.currentData() == posko_id
    page.deleteLater()
    qapp.processEvents()


def test_photo_preview_stays_hidden_until_admin_decrypts(media_context, tmp_path: Path, qapp):
    conn, admin_id, volunteer_id, victim_id, posko_id, storage_path = media_context
    source_path = tmp_path / "incident.jpg"
    Image.new("RGB", (800, 800), color=(90, 120, 150)).save(source_path)

    volunteer_page = PhotoPage(conn)
    volunteer_page.victim_combo.setCurrentIndex(volunteer_page.victim_combo.findData(victim_id))
    volunteer_page.posko_combo.setCurrentIndex(volunteer_page.posko_combo.findData(posko_id))
    volunteer_page.caption_input.setText("Kondisi posko")
    volunteer_page.embed_photo(source_path)
    _finish_worker(volunteer_page, qapp)

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = PhotoPage(conn)
    admin_page.table.selectRow(0)
    assert "Preview foto akan tampil setelah decrypt" in admin_page.image_view.text()
    assert admin_page.image_view.pixmap() is None or admin_page.image_view.pixmap().isNull()

    admin_page.extract_selected()
    assert "Preview foto akan tampil setelah decrypt" in admin_page.image_view.text()
    admin_page.decrypt_selected()
    assert admin_page.image_view.text() == ""
    assert admin_page.image_view.pixmap() is not None
    assert not admin_page.image_view.pixmap().isNull()

    volunteer_page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


def test_photo_preview_unlocks_per_row_only(media_context, tmp_path: Path, qapp):
    conn, admin_id, volunteer_id, victim_id, posko_id, _storage_path = media_context

    first_source = tmp_path / "first.jpg"
    second_source = tmp_path / "second.jpg"
    Image.new("RGB", (800, 800), color=(90, 120, 150)).save(first_source)
    Image.new("RGB", (900, 900), color=(25, 80, 130)).save(second_source)

    volunteer_page = PhotoPage(conn)
    volunteer_page.victim_combo.setCurrentIndex(volunteer_page.victim_combo.findData(victim_id))
    volunteer_page.posko_combo.setCurrentIndex(volunteer_page.posko_combo.findData(posko_id))
    volunteer_page.caption_input.setText("Foto pertama")
    volunteer_page.embed_photo(first_source)
    _finish_worker(volunteer_page, qapp)
    volunteer_page.caption_input.clear()
    volunteer_page.caption_input.setText("Foto kedua")
    volunteer_page.embed_photo(second_source)
    _finish_worker(volunteer_page, qapp)

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = PhotoPage(conn)
    assert admin_page.table.rowCount() == 2

    admin_page.table.selectRow(0)
    admin_page.extract_selected()
    admin_page.decrypt_selected()
    assert admin_page.image_view.text() == ""
    assert admin_page.image_view.pixmap() is not None
    assert not admin_page.image_view.pixmap().isNull()

    admin_page.table.selectRow(1)
    assert admin_page.image_view.text() == "Preview foto akan tampil setelah decrypt."
    assert admin_page.image_view.pixmap() is None or admin_page.image_view.pixmap().isNull()

    admin_page.extract_selected()
    admin_page.decrypt_selected()
    assert admin_page.image_view.text() == ""
    assert admin_page.image_view.pixmap() is not None
    assert not admin_page.image_view.pixmap().isNull()

    volunteer_page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


def test_file_page_masks_admin_row_until_decrypt_then_allows_download(
    media_context, tmp_path: Path, qapp, monkeypatch: pytest.MonkeyPatch
):
    conn, admin_id, volunteer_id, *_rest, storage_path = media_context
    source_path = tmp_path / "laporan.txt"
    source_path.write_bytes(b"Laporan rahasia untuk admin.")
    volunteer_page = FilesPage(conn)
    volunteer_page.upload_file(source_path)
    _finish_worker(volunteer_page, qapp)

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = FilesPage(conn)
    monkeypatch.setattr(
        "ui.files_page.QFileDialog.getSaveFileName",
        lambda *args, **kwargs: (str(tmp_path / "decrypted_laporan.txt"), ""),
    )
    assert admin_page.table.item(0, 1).text() == "[terenkripsi]"
    action_button = admin_page.table.cellWidget(0, 5)
    assert getattr(action_button, "text", lambda: "")() == "Decrypt"
    action_button.click()
    _finish_worker(admin_page, qapp)
    assert admin_page.table.item(0, 1).text() == source_path.name
    assert admin_page.table.cellWidget(0, 5).text() == "Unduh"

    volunteer_page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


def test_file_page_encrypts_for_volunteer_and_admin_decrypts_and_logs_tampering(
    media_context, tmp_path: Path, qapp
):
    conn, admin_id, volunteer_id, *_rest, storage_path = media_context
    source_path = tmp_path / "laporan.txt"
    source_path.write_bytes(b"Laporan rahasia untuk admin.")
    volunteer_page = FilesPage(conn)
    volunteer_page.upload_file(source_path)
    _finish_worker(volunteer_page, qapp)

    file_row = secure_store.list_files(conn, volunteer_id, "relawan")[0]
    encrypted_path = storage_path / file_row["path_enc"]
    assert encrypted_path.name != source_path.name
    assert encrypted_path.read_bytes() != source_path.read_bytes()

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = FilesPage(conn)
    destination = tmp_path / "hasil.txt"
    admin_page.decrypt_file(int(file_row["id"]), destination)
    _finish_worker(admin_page, qapp)
    assert destination.read_bytes() == source_path.read_bytes()

    encrypted = bytearray(encrypted_path.read_bytes())
    encrypted[-1] ^= 1
    encrypted_path.write_bytes(encrypted)
    tampered_destination = tmp_path / "tampered.txt"
    admin_page.decrypt_file(int(file_row["id"]), tampered_destination)
    _finish_worker(admin_page, qapp)
    assert not tampered_destination.exists()
    assert "File rusak atau telah diubah" in admin_page.status_label.text()
    activity = db.list_activity_log(conn)
    assert any(row["aksi"] == "FILE_DECRYPT_FAILED" for row in activity)
    volunteer_page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()
