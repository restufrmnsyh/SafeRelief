import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

import config
from auth import session
from database import db, secure_store
from ui.victims_page import VictimsPage


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def victims_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qapp):
    """Siapkan DB sementara untuk menguji admin detail korban tanpa mengganggu data nyata."""
    database_path = tmp_path / "victims.db"
    db.init_db(database_path)
    conn = db.get_connection(database_path)

    admin_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Admin Korban",
            "username": "admin_korban",
            "password_hash": "hash",
            "role": "admin",
            "is_active": 1,
        },
    )
    volunteer_id = db.insert_user(
        conn,
        {
            "nama_lengkap": "Relawan Korban",
            "username": "relawan_korban",
            "password_hash": "hash",
            "role": "relawan",
            "is_active": 1,
        },
    )
    posko_id = db.insert_posko(
        conn,
        {"nama": "Posko Utama", "lokasi": "Lapangan", "kapasitas": 50},
    )
    master_key = os.urandom(config.MASTER_KEY_LENGTH)
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        master_key,
    )
    db_key = session.get_derived_key(config.HKDF_LABEL_DB)
    victim_id = secure_store.add_victim(
        conn,
        db_key,
        {
            "kode_korban": "K-001",
            "nama_panggilan": "Ayu",
            "usia": 29,
            "gender": "P",
            "posko_id": posko_id,
            "status": "selamat",
            "nama_lengkap": "Ayu Wulandari",
            "nik": "1234567890123456",
            "alamat_asal": "Bandung",
            "kondisi_medis": "Sehat",
            "kontak_keluarga": "081234567890",
            "catatan": "Catatan rahasia",
            "created_by": admin_id,
        },
    )
    session.logout()

    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )

    yield conn, admin_id, volunteer_id, posko_id, victim_id, master_key, db_key
    session.logout()
    conn.close()


def test_admin_detail_shows_ciphertext_and_hides_plaintext_until_decrypt(
    victims_context, monkeypatch: pytest.MonkeyPatch, qapp
):
    conn, admin_id, _volunteer_id, _posko_id, victim_id, master_key, _db_key = victims_context
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        master_key,
    )
    page = VictimsPage(conn)
    page.table.selectRow(0)

    original_get_victim = secure_store.get_victim
    calls = {"get_victim": 0}

    def spy_get_victim(*args, **kwargs):
        calls["get_victim"] += 1
        return original_get_victim(*args, **kwargs)

    monkeypatch.setattr(secure_store, "get_victim", spy_get_victim)
    page.show_detail()
    dialog = page._detail_dialog
    assert dialog is not None
    row = next(
        i for i in range(dialog._table.rowCount())
        if dialog._table.item(i, 0).text() == "nik"
    )
    ciphertext = dialog._table.item(row, 1).text()
    assert ciphertext != "-" and ciphertext != ""
    assert dialog._table.item(row, 2).text() == "(terenkripsi)"
    assert "1234567890123456" not in "\n".join(
        dialog._table.item(r, 2).text() for r in range(dialog._table.rowCount())
    )
    assert calls["get_victim"] == 0

    page.clear_sensitive_state()
    page.deleteLater()
    qapp.processEvents()


def test_admin_decrypt_populates_plaintext_and_logs_only_decrypt_event(
    victims_context, qapp
):
    conn, admin_id, _volunteer_id, _posko_id, victim_id, master_key, _db_key = victims_context
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        master_key,
    )
    page = VictimsPage(conn)
    page.table.selectRow(0)
    page.show_detail()
    dialog = page._detail_dialog
    assert dialog is not None

    page._decrypt_victim(victim_id)
    row = next(
        i for i in range(dialog._table.rowCount())
        if dialog._table.item(i, 0).text() == "nik"
    )
    assert dialog._table.item(row, 2).text() == "1234567890123456"
    log_rows = db.list_activity_log(conn, limit=10)
    assert len(log_rows) == 1
    assert log_rows[0]["aksi"] == "VICTIM_DECRYPTED"
    assert "1234567890123456" not in str(log_rows[0]["detail"])

    page.clear_sensitive_state()
    page.deleteLater()
    qapp.processEvents()


def test_admin_detail_handles_null_sensitive_fields_and_wrong_db_key(
    victims_context, monkeypatch: pytest.MonkeyPatch, qapp
):
    conn, admin_id, _volunteer_id, posko_id, _victim_id, master_key, db_key = victims_context
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        master_key,
    )
    null_id = secure_store.add_victim(
        conn,
        db_key,
        {
            "kode_korban": "K-NULL",
            "nama_panggilan": "Budi",
            "usia": 20,
            "gender": "L",
            "posko_id": posko_id,
            "status": "selamat",
            "nama_lengkap": "Budi Santoso",
            "nik": "999888777666",
            "alamat_asal": None,
            "kondisi_medis": None,
            "kontak_keluarga": None,
            "catatan": None,
            "created_by": admin_id,
        },
    )
    page = VictimsPage(conn)
    page.table.selectRow(1)
    page.show_detail()
    dialog = page._detail_dialog
    assert dialog is not None
    row = next(
        i for i in range(dialog._table.rowCount())
        if dialog._table.item(i, 0).text() == "nik"
    )
    assert dialog._table.item(row, 1).text() != "-"
    page.clear_sensitive_state()

    wrong_master_key = os.urandom(config.MASTER_KEY_LENGTH)
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        wrong_master_key,
    )
    page = VictimsPage(conn)
    page.table.selectRow(1)
    calls = []
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: calls.append(str(args[2])),
    )
    page.show_detail()
    page._decrypt_victim(null_id)
    assert calls and "Pesan tidak dapat dibuka" in calls[0]
    row = next(
        i for i in range(page._detail_dialog._table.rowCount())
        if page._detail_dialog._table.item(i, 0).text() == "nik"
    )
    assert page._detail_dialog._table.item(row, 2).text() == "(terenkripsi)"

    page.clear_sensitive_state()
    page.deleteLater()
    qapp.processEvents()


def test_get_victim_ciphertext_and_decrypt_victim_reject_relawan_and_inactive(
    victims_context, qapp
):
    conn, admin_id, volunteer_id, _posko_id, victim_id, _master_key, db_key = victims_context
    with pytest.raises(PermissionError):
        secure_store.get_victim_ciphertext(conn, volunteer_id, victim_id)
    with pytest.raises(PermissionError):
        secure_store.decrypt_victim(conn, db_key, volunteer_id, victim_id)

    db.update_user_active(conn, admin_id, 0)
    with pytest.raises(PermissionError):
        secure_store.get_victim_ciphertext(conn, admin_id, victim_id)
    with pytest.raises(PermissionError):
        secure_store.decrypt_victim(conn, db_key, admin_id, victim_id)


def test_clear_sensitive_state_closes_dialog_and_clears_plaintext(victims_context, qapp):
    conn, admin_id, _volunteer_id, _posko_id, victim_id, master_key, _db_key = victims_context
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        master_key,
    )
    page = VictimsPage(conn)
    page.table.selectRow(0)
    page.show_detail()
    dialog = page._detail_dialog
    assert dialog is not None
    page._decrypt_victim(victim_id)
    assert dialog._table.item(0, 2).text() != "(terenkripsi)"
    page.clear_sensitive_state()
    assert page._detail_dialog is None
    assert page.table.rowCount() == 0
    qapp.processEvents()


def test_decrypt_state_survives_detail_dialog_close_for_edit_access(victims_context, qapp):
    conn, admin_id, _volunteer_id, _posko_id, victim_id, master_key, _db_key = victims_context
    session.login(
        {"id": admin_id, "username": "admin_korban", "role": "admin"},
        master_key,
    )
    page = VictimsPage(conn)
    page.table.selectRow(0)
    page.show_detail()
    page._decrypt_victim(victim_id)
    assert page._decrypted_victim_id == victim_id
    assert page.edit_button.isEnabled() is True

    page._detail_dialog.reject()
    page._reset_detail_dialog()

    page.table.selectRow(0)
    assert page._decrypted_victim_id == victim_id
    assert page.edit_button.isEnabled() is True

    page.clear_sensitive_state()
    page.deleteLater()
    qapp.processEvents()


def test_relawan_keeps_legacy_detail_flow(victims_context, monkeypatch: pytest.MonkeyPatch, qapp):
    conn, _admin_id, volunteer_id, _posko_id, _victim_id, master_key, _db_key = victims_context
    session.login(
        {"id": volunteer_id, "username": "relawan_korban", "role": "relawan"},
        master_key,
    )
    page = VictimsPage(conn)
    page.table.selectRow(0)
    captured = {"text": ""}

    def fake_information(parent, title, text):
        captured["text"] = text
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "information", fake_information)
    page.show_detail()
    assert "NIK" in captured["text"]
    assert "Bandung" in captured["text"]
    page.deleteLater()
    qapp.processEvents()
