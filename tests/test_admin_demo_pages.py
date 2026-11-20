"""Tes UI blockchain bantuan, audit log, dan panel demonstrasi."""

import base64
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import config
from auth import session
from crypto import keys, super_encrypt
from database import db, secure_store
from ui.activity_log_page import ActivityLogPage
from ui.aid_page import AidPage
from ui.demo_panel_page import DemoPanelPage


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Gunakan satu QApplication untuk tes widget."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def admin_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp):
    database_path = tmp_path / "admin-pages.db"
    monkeypatch.setattr(config, "DB_PATH", database_path)
    db.init_db(database_path)
    conn = db.get_connection(database_path)
    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin Utama",
            "username": "admin",
            "password_hash": "hash",
            "role": "admin",
        },
    )
    volunteer_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Relawan Satu",
            "username": "relawan1",
            "password_hash": "hash",
            "role": "relawan",
        },
    )
    master_key = os.urandom(config.MASTER_KEY_LENGTH)
    derived_db_key = keys.derive_key(master_key, config.HKDF_LABEL_DB)
    victim_id = secure_store.add_victim(
        conn,
        derived_db_key,
        {
            "kode_korban": "K-900",
            "nama_panggilan": "Mawar",
            "nama_lengkap": "Mawar Contoh",
            "nik": "123456789",
            "created_by": volunteer_id,
        },
    )
    session.login(
        {"id": admin_id, "username": "admin", "role": "admin"},
        master_key,
    )
    db.log_activity(conn, "LOGIN_SUCCESS", user_id=admin_id)
    db.log_activity(conn, "VICTIM_CREATED", user_id=volunteer_id)
    db.log_activity(conn, "LOGIN_FAILED", user_id=volunteer_id)
    message_blob = super_encrypt.encrypt(
        "Koordinasi rahasia",
        session.get_vigenere_key(),
        session.get_derived_key(config.HKDF_LABEL_CHAT_ENC),
        session.get_derived_key(config.HKDF_LABEL_CHAT_MAC),
    )
    message_id = secure_store.save_message(
        conn, volunteer_id, admin_id, message_blob
    )
    yield conn, admin_id, volunteer_id, victim_id, message_id
    session.logout()
    conn.close()


def test_aid_admin_records_validates_and_tampers_only_with_confirmation(
    admin_context, monkeypatch: pytest.MonkeyPatch, qapp
):
    conn, admin_id, volunteer_id, *_ = admin_context
    page = AidPage(conn)
    page.type_input.setText("beras")
    page.amount_input.setValue(25)
    page.from_input.setText("Gudang A")
    page.to_input.setText("Posko B")
    page.record_distribution()

    assert page.table.rowCount() == 2
    assert page.validate_chain() == (True, None)
    page.table.selectRow(1)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    page.simulate_tampering()
    assert page.validate_chain() == (True, None)

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    page.simulate_tampering()
    assert page.validate_chain() == (False, 1)
    assert "block index 1 rusak" in page.status_label.text()
    assert any(
        row["aksi"] == "DEMO_AID_TAMPERING"
        for row in db.list_activity_log(conn)
    )

    session.login(
        {"id": volunteer_id, "username": "relawan1", "role": "relawan"},
        session.get_master_key(),
    )
    readonly_page = AidPage(conn)
    assert readonly_page.table.rowCount() == 2
    assert not readonly_page.form.isVisible()
    with pytest.raises(PermissionError, match="Hanya admin"):
        readonly_page.record_distribution()
    page.deleteLater()
    readonly_page.deleteLater()
    qapp.processEvents()


def test_activity_log_admin_filters_by_user_and_action(admin_context, qapp):
    conn, _admin_id, volunteer_id, *_ = admin_context
    page = ActivityLogPage(conn)
    assert page.table.rowCount() >= 3

    page.user_filter.setCurrentIndex(
        page.user_filter.findData(volunteer_id)
    )
    assert page.table.rowCount() == 2
    page.action_filter.setCurrentIndex(
        page.action_filter.findData("VICTIM_CREATED")
    )
    assert page.table.rowCount() == 1
    assert page.table.item(0, 2).text() == "VICTIM_CREATED"

    session.login(
        {"id": volunteer_id, "username": "relawan1", "role": "relawan"},
        session.get_master_key(),
    )
    with pytest.raises(PermissionError, match="hanya dapat dilihat admin"):
        ActivityLogPage(conn)
    page.deleteLater()
    qapp.processEvents()


def test_demo_panel_shows_raw_encrypted_bytes_and_decrypted_values(
    admin_context, qapp
):
    conn, _admin_id, _volunteer_id, victim_id, message_id = admin_context
    page = DemoPanelPage(conn)
    assert page.record_input.currentData() == victim_id
    table = page.comparison
    victim = db.get_victim_by_id(conn, victim_id)
    pairs = {
        table.item(row, 0).text(): (table.item(row, 1).text(), table.item(row, 2).text())
        for row in range(table.rowCount())
    }
    assert len(pairs) == 6
    for caption, key, value in (("Nama lengkap", "nama_lengkap", "Mawar Contoh"), ("NIK", "nik", "123456789")):
        encrypted, decrypted = pairs[caption]
        assert base64.b64decode(encrypted, validate=True) == victim[f"{key}_enc"]
        assert decrypted == value
    assert pairs["Catatan"] == ("—", "—")
    assert page.details.isHidden()
    page.details_button.click()
    assert not page.details.isHidden() and "Kode korban: K-900" in page.details.text()

    page.record_type.setCurrentIndex(page.record_type.findData("messages"))
    assert page.record_input.currentData() == message_id
    assert table.rowCount() == 1 and table.item(0, 0).text() == "Isi pesan"
    assert base64.b64decode(table.item(0, 1).text()) == db.get_message_by_id(conn, message_id)["ciphertext"]
    assert table.item(0, 2).text() == "Koordinasi rahasia"
    assert page.details.isHidden() and "K-900" not in page.details.text()
    page.clear_sensitive_state()
    assert table.rowCount() == 0 and page.details.text() == ""

    session.login(
        {"id": _volunteer_id, "username": "relawan1", "role": "relawan"},
        session.get_master_key(),
    )
    with pytest.raises(PermissionError, match="Panel demo hanya"):
        DemoPanelPage(conn)
    page.deleteLater()
    qapp.processEvents()
