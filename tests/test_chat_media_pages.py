"""Tes alur halaman chat, dokumentasi foto, dan berkas laporan."""

import base64
import json
import os
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import cv2
import numpy as np
import pytest
from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPdfWriter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QGraphicsView, QMessageBox, QPlainTextEdit, QPushButton
from PIL import Image, UnidentifiedImageError

import config
from auth import session
from crypto import aes_module, chacha_module, stego_lsb
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
        conn, {"nama": "Posko A", "lokasi": "Lapangan"}
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
    # Di tes, halaman berdiri sendiri tanpa MainWindow yang biasanya membuangnya.
    for page in qapp.topLevelWidgets():
        if isinstance(page, (FilesPage, PhotoPage, ChatPage)):
            page.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    session.logout()
    conn.close()


def _finish_worker(page, qapp) -> None:
    worker = page._worker
    assert worker is not None
    worker.wait()
    qapp.processEvents()
    assert page._worker is None


def _finish_transfer(page, qapp) -> None:
    worker = page.downloads.worker
    assert worker is not None
    worker.wait()
    qapp.processEvents()
    assert page.downloads.worker is None


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
    assert page.plaintext_view.toPlainText() == ""
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
    media_context, tmp_path: Path, qapp, monkeypatch: pytest.MonkeyPatch
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
    encrypted = tmp_path / f"foto-{photo_row['id']}.png.enc"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(encrypted), ""))
    admin_page.download_button.click()
    _finish_transfer(admin_page, qapp)
    with pytest.raises(UnidentifiedImageError):
        Image.open(encrypted)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(encrypted), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: pytest.fail("Pratinjau meminta lokasi simpan"))
    admin_page.open_button.click()
    _finish_transfer(admin_page, qapp)
    preview = admin_page.downloads.preview
    assert preview is not None and preview.isVisible()
    pixmap = preview.findChild(QGraphicsView).scene().items()[0].pixmap()
    assert pixmap.toImage().convertToFormat(QImage.Format.Format_RGB32) == QImage(str(stego_path)).convertToFormat(QImage.Format.Format_RGB32)
    preview.reject()
    assert admin_page.downloads.preview is None
    assert chacha_module.decrypt(encrypted.read_bytes(), session.get_derived_key(config.HKDF_LABEL_FILE)) == stego_path.read_bytes()
    restored_metadata = aes_module.decrypt(
        stego_lsb.extract(str(stego_path)), session.get_derived_key(config.HKDF_LABEL_STEGO)
    )
    assert json.loads(restored_metadata)["original_sha256"] == photo_row["original_hash"]
    admin_page.extract_selected()
    metadata = admin_page.metadata_view
    assert metadata.state_label.text() == "Ciphertext metadata (hex)"
    assert metadata.payload_view.toPlainText() == stego_lsb.extract(str(stego_path)).hex()
    assert metadata.details.isHidden()
    assert all(value.text() == "" for value in metadata.values.values())
    assert admin_page.image_view.text() != ""
    admin_page.decrypt_selected()
    assert metadata.state_label.text() == "Metadata terverifikasi"
    assert "Ayu" in metadata.values["victim_id"].text()
    assert "Posko A" in metadata.values["posko_id"].text()
    assert "Relawan" in metadata.values["officer_id"].text()
    assert metadata.values["keterangan"].text() == "Kondisi posko"
    assert metadata.hash_view.toPlainText() == photo_row["original_hash"]
    assert metadata.payload_view.toPlainText() == ""
    assert admin_page.image_view.pixmap() is not None
    assert not admin_page.image_view.pixmap().isNull()
    admin_page.clear_sensitive_state()
    assert all(value.text() == "" for value in metadata.values.values())
    assert metadata.hash_view.toPlainText() == ""
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
    assert admin_page.metadata_view.details.isHidden()
    assert all(value.text() == "" for value in admin_page.metadata_view.values.values())
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


def test_file_page_rejects_unsupported_extension_before_encryption(
    media_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp
):
    conn, _admin_id, _volunteer_id, *_rest = media_context
    unsupported = tmp_path / "laporan.EXE"
    unsupported.write_bytes(b"bukan dokumen")
    page = FilesPage(conn)
    captured = {"text": ""}

    def fake_critical(parent, title, text):
        captured["text"] = text
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "critical", fake_critical)
    page.upload_file(unsupported)

    assert "Format berkas tidak didukung" in captured["text"]
    assert page._worker is None
    assert not any((tmp_path / "storage").glob("*.enc"))
    page.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("suffix", [".pdf", ".MP4", ".mov", ".mkv", ".avi", ".webm"])
def test_file_download_is_ciphertext_and_admin_can_preview_downloaded_copy(
    media_context, tmp_path: Path, qapp, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    """Uji unggah, unduh lalu render PDF atau dekode frame dari unduhan admin."""
    conn, admin_id, _volunteer_id, *_rest = media_context
    source_path = tmp_path / f"laporan{suffix}"
    if suffix == ".pdf":
        writer = QPdfWriter(str(source_path))
        writer.setResolution(72)
        painter = QPainter(writer)
        painter.fillRect(40, 40, 160, 120, Qt.GlobalColor.red)
        painter.drawText(40, 200, "Laporan posko")
        painter.end()
        del writer
    else:
        codecs = {".MP4": "mp4v", ".mov": "mp4v", ".mkv": "MJPG", ".avi": "MJPG", ".webm": "VP80"}
        video = cv2.VideoWriter(str(source_path), cv2.VideoWriter_fourcc(*codecs[suffix]), 5, (64, 48))
        assert video.isOpened()
        for shade in (32, 64, 128, 255):
            video.write(np.full((48, 64, 3), shade, dtype=np.uint8))
        video.release()

    def choose_source(_parent: FilesPage, _title: str, _directory: str, filters: str) -> tuple[str, str]:
        assert f"*{suffix.lower()}" in filters
        return str(source_path), filters

    monkeypatch.setattr("ui.files_page.QFileDialog.getOpenFileName", choose_source)
    volunteer_page = FilesPage(conn)
    volunteer_page.upload_button.click()
    _finish_worker(volunteer_page, qapp)
    assert volunteer_page.table.item(0, 1).text() == source_path.name

    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        session.get_master_key(),
    )
    admin_page = FilesPage(conn)
    encrypted = tmp_path / (source_path.name + ".enc")
    if suffix == ".pdf":
        admin_page.table.selectRow(0)
        admin_page.preview_button.click()
        _finish_transfer(admin_page, qapp)
        assert admin_page.downloads.preview.document.pageCount() == 1
        admin_page.downloads.preview.reject()

    def save_download(_parent, _title, suggested_name, _filter):
        assert suggested_name == encrypted.name
        return str(encrypted), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", save_download)
    stored = next(config.STORAGE_DIR.glob("*.enc"))
    body = stored.read_bytes()[config.CHACHA20_NONCE_LENGTH:-16]
    assert admin_page.table.horizontalHeaderItem(1).text() == "Ciphertext berkas (Base64)"
    assert admin_page.table.item(0, 1).text() == base64.b64encode(body[:48]).decode("ascii") + "…"
    download_button = admin_page.table.cellWidget(0, 5)
    assert download_button.text() == "Unduh"
    download_button.click()
    _finish_transfer(admin_page, qapp)
    assert encrypted.read_bytes() == stored.read_bytes()
    assert encrypted.read_bytes() != source_path.read_bytes()
    stored.unlink()

    before = set(tmp_path.iterdir())
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(encrypted), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: pytest.fail("Pratinjau meminta lokasi simpan"))
    admin_page.open_button.click()
    _finish_transfer(admin_page, qapp)
    preview = admin_page.downloads.preview
    assert preview is not None and preview.isVisible()
    if suffix == ".pdf":
        assert preview.document.pageCount() == 1
        page_image = preview.document.render(0, QSize(595, 842))
        color = page_image.pixelColor(120, 100)
        assert color.red() > 220 and color.green() < 35
    else:
        frames = []
        preview.player.videoSink().videoFrameChanged.connect(lambda frame: frames.append(frame.isValid()))
        next(button for button in preview.findChildren(QPushButton) if button.text() == "Putar").click()
        for _ in range(100):
            QTest.qWait(50)
            if any(frames):
                break
        assert any(frames), preview.player.errorString()
    admin_page.stop_worker(cancel_pending=True)
    assert admin_page.downloads.preview is None
    assert set(tmp_path.iterdir()) == before

    volunteer_page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


def test_admin_file_list_handles_missing_storage_next_to_small_ciphertext(media_context) -> None:
    conn, admin_id, volunteer_id, _, _, storage = media_context
    storage.mkdir()
    ciphertext = chacha_module.encrypt(b"PDF", session.get_derived_key(config.HKDF_LABEL_FILE))
    (storage / "kecil.enc").write_bytes(ciphertext)
    for name in ("kecil.enc", "hilang.enc"):
        db.insert_file(conn, {"nama_asli": "contoh.pdf", "path_enc": name, "uploader_id": volunteer_id,
                              "ukuran": 3, "file_hash": "uji"})
    session.login({"id": admin_id, "role": "admin"}, session.get_master_key())
    page = FilesPage(conn)
    assert page.table.item(0, 1).text() == "Berkas tidak tersedia"
    assert base64.b64decode(page.table.item(1, 1).text(), validate=True) == ciphertext[12:-16]


def test_file_page_encrypts_for_volunteer_and_admin_decrypts_and_logs_tampering(
    media_context, tmp_path: Path, qapp
):
    conn, admin_id, volunteer_id, *_rest, storage_path = media_context
    source_path = tmp_path / "laporan.pdf"
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
    destination = tmp_path / "hasil.pdf"
    admin_page.decrypt_file(int(file_row["id"]), destination)
    _finish_transfer(admin_page, qapp)
    assert destination.read_bytes() == source_path.read_bytes()

    encrypted = bytearray(encrypted_path.read_bytes())
    encrypted[-1] ^= 1
    encrypted_path.write_bytes(encrypted)
    tampered_destination = tmp_path / "tampered.pdf"
    admin_page.decrypt_file(int(file_row["id"]), tampered_destination)
    _finish_transfer(admin_page, qapp)
    assert not tampered_destination.exists()
    assert "File rusak atau telah diubah" in admin_page.status_label.text()
    activity = db.list_activity_log(conn)
    assert any(row["aksi"] == "FILE_DECRYPT_FAILED" for row in activity)
    volunteer_page.deleteLater()
    admin_page.deleteLater()
    qapp.processEvents()


@pytest.mark.parametrize("failure", ["wrong_key", "truncated", "logout"])
def test_restore_failure_preserves_existing_destination(
    media_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp, failure: str
) -> None:
    conn, admin_id, *_rest = media_context
    source = tmp_path / "laporan.pdf.enc"
    destination = tmp_path / "salinan.pdf"
    destination.write_bytes(b"Salinan sebelumnya")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
    page = FilesPage(conn)
    page.downloads.choose_and_decrypt()
    assert page.downloads.worker is None
    session.login({"id": admin_id, "role": "admin"}, session.get_master_key())
    admin_page = FilesPage(conn)
    key = os.urandom(32) if failure == "wrong_key" else session.get_derived_key(config.HKDF_LABEL_FILE)
    source.write_bytes(b"abc" if failure == "truncated" else chacha_module.encrypt(b"isi laporan", key))
    before = set(tmp_path.iterdir())
    admin_page.open_button.click()
    if failure == "logout":
        session.logout()
        admin_page.stop_worker(cancel_pending=True)
        qapp.processEvents()
    else:
        _finish_transfer(admin_page, qapp)
        assert "File rusak atau telah diubah" in admin_page.status_label.text()
        assert any(row["aksi"] == "FILE_DECRYPT_FAILED" for row in db.list_activity_log(conn))
    assert destination.read_bytes() == b"Salinan sebelumnya"
    assert admin_page.downloads.preview is None
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("format_name", ["docx", "pptx", "xlsx"])
def test_admin_previews_office_content_after_renaming_download(
    media_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp, format_name: str
) -> None:
    conn, admin_id, *_ = media_context
    package = BytesIO()
    with ZipFile(package, "w") as archive:
        if format_name == "docx":
            archive.writestr("word/document.xml", "<document><body><p><r><t>Laporan posko</t></r></p></body></document>")
            expected = "Laporan posko"
        elif format_name == "pptx":
            archive.writestr("ppt/presentation.xml", '<presentation xmlns:r="urn:r"><sldIdLst><sldId r:id="s"/></sldIdLst></presentation>')
            archive.writestr("ppt/_rels/presentation.xml.rels", '<Relationships><Relationship Id="s" Target="slides/slide4.xml"/></Relationships>')
            archive.writestr("ppt/slides/slide4.xml", "<sld><p><r><t>Evakuasi</t></r></p></sld>")
            expected = "Slide 1\nEvakuasi"
        else:
            archive.writestr("xl/workbook.xml", '<workbook xmlns:r="urn:r"><sheets><sheet name="Stok" r:id="s"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships><Relationship Id="s" Target="worksheets/sheet2.xml"/></Relationships>')
            archive.writestr("xl/sharedStrings.xml", "<sst><si><t>Beras</t></si></sst>")
            archive.writestr("xl/worksheets/sheet2.xml", '<worksheet><sheetData><row><c r="A1" t="s"><v>0</v></c><c r="C1"><v>12</v></c></row></sheetData></worksheet>')
            expected = "Lembar Stok\nA1  Beras    |    C1  12"
    encrypted = tmp_path / "unduhan.enc"
    encrypted.write_bytes(chacha_module.encrypt(package.getvalue(), session.get_derived_key(config.HKDF_LABEL_FILE)))
    session.login({"id": admin_id, "role": "admin"}, session.get_master_key())
    page = FilesPage(conn)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(encrypted), ""))
    page.open_button.click()
    _finish_transfer(page, qapp)
    view = page.downloads.preview.findChild(QPlainTextEdit)
    assert view.isReadOnly() and view.toPlainText() == expected
    page.downloads.preview.reject()
